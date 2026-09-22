"""Read-only UIA adapter. Child process bounds COM hangs; no chat data is logged.

The current provider exposes bubble text but no verified sender attribute. All
rows deliberately remain unassigned until the user reviews them.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from desktop.service import ServiceError


CAUSES = {
    "window closed": "window_closed", "window replaced": "window_changed",
    "chat changed": "window_changed", "unknown row": "unknown_row",
    "unsupported row": "invalid_text", "empty or large snapshot": "invalid_text",
    "message list unavailable": "missing_list", "only independent single chats": "unsupported_chat",
    "invalid tree": "unstable_tree", "tree budget": "unstable_tree", "child budget": "unstable_tree",
}
ERRORS = {
    "window_closed": "原微信窗口已关闭或不可见，请重新打开并选择单聊。",
    "window_changed": "原微信窗口身份已变化，请重新读取并绑定；没有继续使用旧聊天。",
    "unknown_row": "消息列表出现尚不支持的项目，已暂停；请反馈此提示，不需要重新配置 API。",
    "invalid_text": "当前列表文字为空、不可读取或过长，请调整可见聊天区域后重试。",
    "missing_list": "未找到消息列表；请确认独立单聊窗口已加载，必要时使用兼容启动。",
    "unsupported_chat": "当前窗口不是支持的独立单聊，请重新选择。",
    "unstable_tree": "微信控件正在变化或超出读取范围，请稍后重新读取。",
    "uia_failure": "微信无障碍接口查询失败，请稍后重试；未读取或提交新的聊天结果。",
    "timeout": "微信直读超过 12 秒，已停止本次读取；请稍后重试。",
    "worker_failure": "直读子进程未正常返回，请重启助手后重试。",
}


def walk(root, walker, limit=1024):
    pending, seen = [root], set()
    while pending:
        element = pending.pop()
        identity = tuple(element.GetRuntimeId())
        if not identity or identity in seen:
            raise ValueError("invalid tree")
        seen.add(identity)
        if len(seen) > limit:
            raise ValueError("tree budget")
        yield element
        children, sibling_ids = [], set()
        child = walker.GetFirstChildElement(element)
        while child:
            child_id = tuple(child.GetRuntimeId())
            if child_id in sibling_ids or len(children) + len(pending) + len(seen) >= limit:
                raise ValueError("child budget")
            sibling_ids.add(child_id)
            children.append(child)
            child = walker.GetNextSiblingElement(child)
        pending.extend(reversed(children))


def collect(root, walker):
    identity = root.CurrentAutomationId
    if not identity.startswith("ChatSingleWindow") or "@chatroom" in identity:
        raise ValueError("only independent single chats")
    lists = [e for e in walk(root, walker)
             if e.CurrentAutomationId == "chat_message_list" and e.CurrentControlType == 50008]
    if len(lists) != 1:
        raise ValueError("message list unavailable")
    rows = []
    for element in walk(lists[0], walker):
        if element.CurrentControlType == 50007:
            aid = element.CurrentAutomationId
            text = element.CurrentName
            # Observed Weixin time separator: ListItem, empty AutomationId, HH:MM.
            # A genuine bubble containing a time is still a message.
            if not aid and isinstance(text, str) and re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d", text.strip()):
                continue
            if aid != "chat_message_list.qt_scrollarea_viewport.chat_bubble_item_view":
                raise ValueError("unknown row")
            if not isinstance(text, str) or not text.strip() or len(text) > 20000:
                raise ValueError("unsupported row")
            rows.append(text)
    if not rows or sum(map(len, rows[-30:])) > 19000:
        raise ValueError("empty or large snapshot")
    if root.CurrentAutomationId != identity:
        raise ValueError("chat changed")
    result = {"identity": identity, "rows": rows[-30:]}
    # Optional layout for the explicit calibrated OCR mode, never capture here.
    try:
        def box(element):
            r = element.CurrentBoundingRectangle
            return [int(r.left), int(r.top), int(r.right), int(r.bottom)]
        titles = [e for e in walk(root, walker)
                  if e.CurrentAutomationId.endswith(".current_chat_name_label")]
        if len(titles) == 1:
            result["message_box"] = box(lists[0])
            result["title_box"] = box(titles[0])
    except (AttributeError, TypeError):
        pass
    return result


def preview(rows):
    # Flatten embedded line breaks so a message cannot inject a speaker prefix.
    return "\n".join("待确认：" + " ".join(text.splitlines()) for text in rows)


def request(action, binding=None):
    """Run in a background thread. stdout is an in-memory private protocol only."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "desktop.direct_reader", action],
            input=json.dumps(binding), capture_output=True, encoding="utf-8",
            timeout=12, cwd=Path(__file__).resolve().parent.parent,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        payload = json.loads(result.stdout)
        if result.returncode:
            code = payload.get("error_code") if isinstance(payload, dict) else None
            raise ServiceError(ERRORS.get(code, ERRORS["worker_failure"]))
        return payload
    except ServiceError:
        raise
    except subprocess.TimeoutExpired:
        raise ServiceError(ERRORS["timeout"]) from None
    except Exception:
        raise ServiceError(ERRORS["worker_failure"]) from None


def native(action, binding):
    from desktop.accessibility_probe import Uia, weixin_windows
    backend = Uia()
    handles = weixin_windows()
    if action == "list":
        choices = []
        for hwnd in handles[:16]:
            root = backend.api.ElementFromHandle(hwnd)
            identity = root.CurrentAutomationId
            if identity.startswith("ChatSingleWindow") and "@chatroom" not in identity:
                choices.append({"hwnd": hwnd, "identity": identity,
                                "runtime": list(root.GetRuntimeId()), "name": root.CurrentName})
        return choices
    if action != "read" or binding["hwnd"] not in handles:
        raise ValueError("window closed")
    root = backend.api.ElementFromHandle(binding["hwnd"])
    if root.CurrentAutomationId != binding["identity"] or list(root.GetRuntimeId()) != binding["runtime"]:
        raise ValueError("window replaced")
    return collect(root, backend.api.ControlViewWalker)


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        payload = native(sys.argv[1], json.loads(sys.stdin.read()))
        sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    except Exception as exc:
        # Only allowlisted codes cross the process boundary, never exception text.
        if sys.stdout is not None:
            sys.stdout.write(json.dumps({"error_code": CAUSES.get(str(exc), "uia_failure")}))
        sys.exit(1)
