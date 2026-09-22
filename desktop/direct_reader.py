"""Read-only UIA adapter. Child process bounds COM hangs; no chat data is logged.

The current provider exposes bubble text but no verified sender attribute. All
rows deliberately remain unassigned until the user reviews them.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from desktop.service import ServiceError


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
            if element.CurrentAutomationId != "chat_message_list.qt_scrollarea_viewport.chat_bubble_item_view":
                raise ValueError("unknown row")
            text = element.CurrentName
            if not isinstance(text, str) or not text.strip() or len(text) > 20000:
                raise ValueError("unsupported row")
            rows.append(text)
    if not rows or sum(map(len, rows[-30:])) > 19000:
        raise ValueError("empty or large snapshot")
    if root.CurrentAutomationId != identity:
        raise ValueError("chat changed")
    return {"identity": identity, "rows": rows[-30:]}


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
        if result.returncode:
            raise ValueError("reader failed")
        return json.loads(result.stdout)
    except Exception:
        raise ServiceError("直接读取未完成：请保持独立单聊窗口打开；确认已使用兼容启动，或改用截图。") from None


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
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        payload = native(sys.argv[1], json.loads(sys.stdin.read()))
        sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    except Exception:
        sys.exit(1)
