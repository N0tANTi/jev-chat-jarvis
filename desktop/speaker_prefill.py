"""Suggest speakers from a guarded screenshot, preserving the original UIA text."""
from collections import Counter
import re

from desktop.service import ServiceError, check_cancel, recognize, to_transcript
from desktop.direct_reader import request


def match_speakers(rows, transcript):
    normalize = lambda value: "".join(value.split())
    native = [normalize(row) for row in rows]
    observed = []
    for line in transcript.splitlines():
        match = re.fullmatch(r"(我|对方|待确认)[:：]\s*(.+)", line.strip())
        if match:
            observed.append((normalize(match[2]), match[1]))
    native_counts = Counter(native)
    ocr_counts = Counter(text for text, _ in observed)
    lookup = {text: (i, side) for i, (text, side) in enumerate(observed)}
    matches = []
    result = ["待确认"] * len(rows)
    for i, text in enumerate(native):
        # Duplicated text might belong to either person. Do not match by text alone.
        if text and native_counts[text] == 1 and ocr_counts[text] == 1:
            position, side = lookup[text]
            matches.append((i, position, side))
    positions = [p for _, p, _ in matches]
    if positions != sorted(positions):
        return result
    for i, _, side in matches:
        result[i] = side
    return result


def same_snapshot(expected, current):
    return all(expected.get(k) == current.get(k) and expected.get(k) is not None
               for k in ("identity", "rows", "message_box", "title_box"))


def predict(binding, snapshot, image, key, cancel, progress=lambda _: None):
    check_cancel(cancel)
    if not same_snapshot(snapshot, request("read", binding)):
        raise ServiceError("聊天内容或窗口位置已变化，请关闭面板，重新读取后再识别发言人。")
    check_cancel(cancel)
    transcript = to_transcript(recognize(image, key, cancel, progress), image)
    check_cancel(cancel)
    if not same_snapshot(snapshot, request("read", binding)):
        raise ServiceError("识别期间聊天已变化，本次预选已丢弃；请重新读取。")
    check_cancel(cancel)
    return match_speakers(snapshot["rows"], transcript)


def attach_prefill(app, dialog, binding, snapshot, choices, notes, epoch):
    """Tk owns capture/widgets; worker owns network/native reads, queue-only updates."""
    import queue
    import threading
    from tkinter import ttk
    from desktop.watcher import WindowBinding, foreground_weixin

    events = queue.Queue()
    cancel = threading.Event()
    state = {"busy": False, "closed": False}
    button = ttk.Button(dialog, text="自动识别发言人（MinerU）")
    button.pack(anchor="w", padx=12, pady=5)

    def current():
        return not state["closed"] and not app.closed and app.direct_epoch == epoch

    def restore():
        if not app.closed:
            app.root.deiconify()
        if not state["closed"]:
            dialog.deiconify()

    def fail(message):
        state["busy"] = False
        if current():
            button.configure(state="normal")
            notes.set(message + " 仍可手动点选。")

    def start():
        if not current() or state["busy"]:
            return
        if not all(snapshot.get(k) for k in ("message_box", "title_box")):
            fail("微信未提供消息区域位置，无法自动识别。")
            return
        if not app.keys.get("MINERU_API_TOKEN"):
            fail("缺少 MinerU 配置。")
            return
        state["busy"] = True
        button.configure(state="disabled")
        notes.set("正在置前并截取本次单聊消息区，随后上传 MinerU 自动识别发言人；原文字保持不变。")
        dialog.withdraw()
        app.root.withdraw()
        app.root.after(350, activate)

    def activate():
        if not current():
            restore()
            return
        try:
            foreground_weixin(binding["hwnd"])
        except Exception as exc:
            restore()
            fail(str(exc) if isinstance(exc, ServiceError) else "无法置前微信，未截图或上传。")
            return
        app.root.after(250, capture)

    def capture():
        if not current():
            restore()
            return
        try:
            source = WindowBinding(snapshot["message_box"], snapshot["title_box"])
            if source.hwnd != binding["hwnd"] or not source.ready():
                raise ServiceError("请将原微信单聊放在助手后方且保持可见，再点击自动识别。")
            title = source.grab(source.title_box)
            image = source.capture(title)
            if image is None:
                raise ServiceError("微信被遮挡，未截取或上传。")
        except Exception as exc:
            restore()
            fail(str(exc) if isinstance(exc, ServiceError) else "截图失败，未上传。")
            return
        restore()

        def worker():
            try:
                value = predict(binding, snapshot, image, app.keys["MINERU_API_TOKEN"], cancel,
                                lambda text: events.put(("progress", text)))
                events.put(("result", value))
            except Exception as exc:
                events.put(("error", str(exc) if isinstance(exc, ServiceError) else "发言人识别失败。"))

        threading.Thread(target=worker, daemon=True).start()

    def poll():
        if not current():
            cancel.set()
            return
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "progress":
                    notes.set(value)
                elif kind == "error":
                    fail(value)
                else:
                    state["busy"] = False
                    button.configure(state="normal")
                    applied = 0
                    for choice, side in zip(choices, value):
                        if choice.get() == "待确认" and side in ("我", "对方"):
                            choice.set(side)
                            applied += 1
                    unknown = sum(c.get() == "待确认" for c in choices)
                    notes.set(f"已自动预选 {applied} 条，剩余 {unknown} 条待确认。请检查后保存或自动运行；图片、语音等请选忽略。")
        except queue.Empty:
            pass
        dialog.after(100, poll)

    def destroyed(event):
        if event.widget == dialog:
            state["closed"] = True
            cancel.set()

    dialog.bind("<Destroy>", destroyed, add="+")
    button.configure(command=start)
    dialog.after(100, poll)
    dialog.after(200, start)
    return state
