"""Session-only message tracking. UIA RuntimeIds are not durable message IDs."""
import threading

from desktop.direct_reader import request
from desktop.service import ServiceError, analyze, check_cancel, recognize, to_transcript
from desktop.speaker_prefill import match_speakers
from desktop.watcher import header_matches


def entries(snapshot):
    items = snapshot.get("items", [])
    ids = [tuple(i["id"]) for i in items]
    if not items or len(set(ids)) != len(ids) or any(not i for i in ids):
        raise ServiceError("微信未提供可区分的消息控件标识，增量模式已暂停，请重新读取。")
    return items


def stamp(snapshot):
    return snapshot["identity"], tuple((tuple(i["id"]), i["text"]) for i in entries(snapshot))


def crop_new(image, message_box, items):
    left, top, right, bottom = message_box
    boxes = [item.get("box") for item in items]
    if not boxes or any(not b or not (left <= b[0] < b[2] <= right and top <= b[1] < b[3] <= bottom) for b in boxes):
        raise ServiceError("新增消息区域不完整或缺少位置，已暂停；请回到聊天底部重新读取。")
    if image.size != (right - left, bottom - top):
        raise ServiceError("消息截图尺寸变化，已暂停，请重新读取。")
    # Preserve horizontal coordinates and bubble colours; upload only new rows' band.
    return image.crop((0, min(b[1] for b in boxes) - top, image.width, max(b[3] for b in boxes) - top))


class MessageState:
    def __init__(self, snapshot, choices):
        items = entries(snapshot)
        if len(items) != len(choices) or any(c not in ("我", "对方", "忽略") for c in choices):
            raise ServiceError("请先完成本次消息的发言人确认。")
        self.identity = snapshot["identity"]
        self.known = {tuple(i["id"]): (i["text"], c) for i, c in zip(items, choices)}
        self.tail = tuple(items[-1]["id"])

    def pending(self, snapshot):
        if snapshot["identity"] != self.identity:
            raise ServiceError("聊天身份已变化，增量模式已停止。")
        items = entries(snapshot)
        for item in items:
            prior = self.known.get(tuple(item["id"]))
            if prior and prior[0] != item["text"]:
                raise ServiceError("微信复用了消息控件或修改了正文，请重新读取校对。")
        ids = [tuple(i["id"]) for i in items]
        new = [i for i in items if tuple(i["id"]) not in self.known]
        if not new:
            return [] if self.tail in ids else None  # Scrolled into known history.
        if self.tail not in ids or any(tuple(i["id"]) not in self.known for i in items[:ids.index(self.tail)]):
            raise ServiceError("无法区分新增消息与滚动历史，已暂停；请回到底部重新读取。")
        if len(self.known) + len(new) > 500:
            raise ServiceError("本次会话已达到 500 条缓存上限，请重新读取以继续。")
        return new

    def accept(self, snapshot, pending, sides):
        if len(sides) != len(pending) or any(s not in ("我", "对方") for s in sides):
            raise ServiceError("新增消息发言人仍不明确，已暂停；请重新读取并确认待确认项。")
        for item, side in zip(pending, sides):
            self.known[tuple(item["id"])] = (item["text"], side)
        self.tail = tuple(entries(snapshot)[-1]["id"])

    def messages(self, snapshot):
        result = []
        for item in entries(snapshot):
            text, side = self.known[tuple(item["id"])]
            if side != "忽略":
                result.append({"from": "me" if side == "我" else "other", "text": " ".join(text.splitlines())})
        return result


class IncrementalWorker:
    def __init__(self, native, snapshot, choices, binding, title, keys, relationship, memory, emit):
        self.native, self.seed = native, snapshot
        self.state = MessageState(snapshot, choices)
        self.binding, self.title = binding, title
        self.keys, self.relationship, self.memory = keys, relationship, memory
        self.emit = emit
        self.cancel = threading.Event()
        self.last_output = None
        self.latest = None

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def current(self, snapshot, layout=False):
        check_cancel(self.cancel)
        fresh = request("read", self.native)
        return (stamp(fresh) == stamp(snapshot)
                and (not layout or (fresh.get("items") == snapshot.get("items") and fresh.get("message_box") == snapshot.get("message_box"))))

    def step(self):
        if not self.binding.ready():
            self.emit("paused", "微信不在前台或被遮挡，已暂停；回到原聊天后继续，不重复 OCR 已确认消息。")
            return
        if not header_matches(self.title, self.binding.grab(self.binding.title_box)):
            raise ServiceError("聊天标题变化，增量模式已停止，请重新读取。")
        snapshot = request("read", self.native)
        token = stamp(snapshot)
        if token != self.latest:
            self.latest = token
            self.emit("changed", "检测到消息列表变化，正在核对新增消息。")
            return  # Require the same message list on two consecutive polls.
        new = self.state.pending(snapshot)
        if new is None:
            self.emit("paused", "当前显示的是旧消息，未调用 OCR；回到聊天底部后继续。")
            return
        if token == self.last_output:
            return  # No screenshot, OCR or model call for unchanged messages.
        if new:
            picture = self.binding.capture(self.title)
            if picture is None:
                return
            cropped = crop_new(picture, self.binding.message_box, new)
            first_new_y = min(i["box"][1] for i in new)
            old_boxes = [i.get("box") for i in entries(snapshot) if tuple(i["id"]) in self.state.known]
            if any(b and b[1] < self.binding.message_box[3] and b[3] > first_new_y for b in old_boxes):
                raise ServiceError("消息控件区域重叠，无法只截取新增内容；已暂停，未上传整屏。")
            if not self.current(snapshot, layout=True):
                return
            check_cancel(self.cancel)
            self.emit("status", f"仅识别 {len(new)} 条新增消息的区域；已有发言人直接复用。")
            content = recognize(cropped, self.keys["MINERU_API_TOKEN"], self.cancel)
            sides = match_speakers([i["text"] for i in new], to_transcript(content, cropped))
            if not self.current(snapshot):
                return
            self.state.accept(snapshot, new, sides)
        messages = self.state.messages(snapshot)
        if not messages:
            self.last_output = token
            return
        text = "\n".join(("我：" if m["from"] == "me" else "对方：") + m["text"] for m in messages)
        self.emit("text", text)
        # Ignoring a last media row does not make an older message a new reply trigger.
        last_side = self.state.known[tuple(entries(snapshot)[-1]["id"])][1]
        if last_side != "对方":
            self.last_output = token
            self.emit("status", "最后一条不是对方文字消息，继续等待；不会重复识别旧消息。")
            return
        if not self.current(snapshot) or not self.binding.ready():
            return
        result = analyze(messages, self.relationship, self.keys, self.cancel,
                         lambda text: self.emit("status", text), memory=self.memory)
        if not self.current(snapshot) or not self.binding.ready():
            self.emit("changed", "生成时聊天已变化，旧建议已丢弃，正在等待最新消息。")
            return
        self.last_output = token
        self.emit("result", result)

    def run(self):
        try:
            while not self.cancel.is_set():
                self.step()
                self.cancel.wait(1.5)
        except Exception as exc:
            if not self.cancel.is_set():
                self.emit("error", str(exc) if isinstance(exc, ServiceError) else "增量读取失败，已暂停；请重新读取。")
