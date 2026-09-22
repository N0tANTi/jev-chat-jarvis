"""User-run MSAA/UIA structural diagnostic. Never reads names, values or chat text.

Independent implementation of documented Microsoft APIs. No wxauto import,
process-memory access, screenshots, input simulation, or network requests.
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
from collections import Counter
from ctypes import wintypes
from pathlib import Path


def summarize_uia(root, walker, limit=256, max_depth=12):
    pending = [(root, 0)]
    visited, retained = set(), []
    types = Counter()
    count = errors = 0
    truncated = False
    while pending and count < limit:
        element, depth = pending.pop()
        try:
            identity = tuple(element.GetRuntimeId())
            if not identity:
                raise ValueError("missing runtime id")
        except Exception:
            # Retain wrappers so fallback pointer identities cannot be reused.
            identity = ("pointer", ctypes.cast(element, ctypes.c_void_p).value)
        if identity in visited:
            continue
        visited.add(identity)
        retained.append(element)
        count += 1
        try:
            control_type = element.CurrentControlType
            types[str(control_type) if type(control_type) is int else "custom"] += 1
            child = walker.GetFirstChildElement(element)
            if depth >= max_depth:
                truncated |= bool(child)
                continue
            siblings = set()
            while child:
                if count + len(pending) >= limit:
                    truncated = True
                    break
                child_id = tuple(child.GetRuntimeId())
                if not child_id or child_id in siblings:
                    errors += 1
                    break
                siblings.add(child_id)
                pending.append((child, depth + 1))
                child = walker.GetNextSiblingElement(child)
        except Exception:
            errors += 1
    return {"nodes": count, "control_types": dict(types), "errors": errors,
            "truncated": bool(truncated or pending)}


class Uia:
    def __init__(self):
        import comtypes.client
        module = comtypes.client.GetModule("UIAutomationCore.dll")
        self.api = comtypes.client.CreateObject(module.CUIAutomation, interface=module.IUIAutomation)

    def measure(self, hwnd, view):
        root = self.api.ElementFromHandle(hwnd)
        if not root:
            raise OSError("UIA root unavailable")
        walker = getattr(self.api, {"raw": "RawViewWalker", "control": "ControlViewWalker",
                                    "content": "ContentViewWalker"}[view])
        return summarize_uia(root, walker)


def child_windows(parent, limit=16):
    """Native descendants in the same process, including hidden child windows."""
    u = ctypes.WinDLL("user32")
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    parent_pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(parent, ctypes.byref(parent_pid))
    result = []
    truncated = False

    def visit(hwnd, _):
        nonlocal truncated
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != parent_pid.value:
            return True
        if len(result) >= limit:
            truncated = True
            return False
        result.append((hwnd, bool(u.IsWindowVisible(hwnd))))
        return True

    u.EnumChildWindows(parent, callback_type(visit), 0)
    return result, truncated


def summarize(root, backend, limit=256, max_depth=8):
    pending = [(root, 0, 0)]
    roles = Counter()
    visited = set()
    count = errors = 0
    truncated = False
    while pending and count < limit:
        obj, child, depth = pending.pop()
        identity = (backend.identity(obj), child)
        if identity in visited:
            continue
        visited.add(identity)
        count += 1
        try:
            role = backend.role(obj, child)
            roles[str(role) if type(role) is int else "custom"] += 1
            if child == 0:
                total = backend.child_count(obj)
                if depth >= max_depth:
                    truncated |= total > 0
                else:
                    available = max(0, limit - count - len(pending))
                    truncated |= total > available
                    for item in backend.children(obj, min(total, available)):
                        pending.append((obj, item, depth + 1) if type(item) is int
                                       else (backend.accessible(item), 0, depth + 1))
        except Exception:
            errors += 1
    return {"nodes": count, "roles": dict(roles), "errors": errors,
            "truncated": bool(truncated or pending)}


class Msaa:
    def __init__(self):
        import comtypes.client
        from comtypes.automation import VARIANT
        module = comtypes.client.GetModule("oleacc.dll")
        self.interface, self.variant = module.IAccessible, VARIANT
        self.dll = ctypes.WinDLL("oleacc")
        self.dll.AccessibleObjectFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD,
                                                       ctypes.c_void_p, ctypes.c_void_p]
        self.dll.AccessibleObjectFromWindow.restype = ctypes.c_long
        self.dll.AccessibleChildren.argtypes = [ctypes.POINTER(self.interface), ctypes.c_long,
                                               ctypes.c_long, ctypes.POINTER(VARIANT),
                                               ctypes.POINTER(ctypes.c_long)]
        self.dll.AccessibleChildren.restype = ctypes.c_long

    def root(self, hwnd, object_id):
        result = ctypes.POINTER(self.interface)()
        hr = self.dll.AccessibleObjectFromWindow(hwnd, object_id,
            ctypes.byref(self.interface._iid_), ctypes.byref(result))
        if hr < 0 or not result:
            raise OSError("MSAA object unavailable")
        return result

    def identity(self, obj):
        return ctypes.cast(obj, ctypes.c_void_p).value

    def role(self, obj, child):
        return obj.accRole[child]

    def child_count(self, obj):
        return max(0, int(obj.accChildCount))

    def accessible(self, obj):
        return obj.QueryInterface(self.interface)

    def children(self, obj, count):
        if not count:
            return []
        values = (self.variant * count)()
        obtained = ctypes.c_long()
        hr = self.dll.AccessibleChildren(obj, 0, count, values, ctypes.byref(obtained))
        if hr < 0:
            raise OSError("MSAA children unavailable")
        return [values[i].value for i in range(max(0, min(count, obtained.value)))]


def weixin_windows():
    """Find visible Weixin windows by process image, without reading window titles."""
    u, k = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                          ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    result = []

    def visit(hwnd, _):
        if not u.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process = k.OpenProcess(0x1000, False, pid.value)
        if not process:
            return True
        try:
            size, path = wintypes.DWORD(32768), ctypes.create_unicode_buffer(32768)
            if k.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
                if path.value.lower().endswith("\\weixin.exe"):
                    result.append(hwnd)
        finally:
            k.CloseHandle(process)
        return True

    u.EnumWindows(callback_type(visit), 0)
    return result


def probe(emit=lambda _: None):
    backend = Msaa()
    try:
        uia = Uia()
    except Exception:
        uia = None
    windows = weixin_windows()
    samples = []
    emit({"event": "inventory", "visible_windows": len(windows), "schema_version": 2})
    # Probe every top-level window before spending the remaining budget on children.
    targets, descendants = [], []
    for index, hwnd in enumerate(windows[:8]):
        children, truncated = child_windows(hwnd)
        targets.append((hwnd, {"window_index": index, "target": "top",
                               "child_windows": len(children), "children_truncated": truncated}))
        descendants.extend((child, {"window_index": index, "target": "child",
                                    "child_index": n, "visible": visible})
                           for n, (child, visible) in enumerate(children))
    selected = (targets + descendants)[:24]
    emit({"event": "targets", "selected_targets": len(selected),
          "target_limit_reached": len(targets) + len(descendants) > 24})
    for hwnd, metadata in selected:
        for view in ("raw", "control", "content"):
            emit({"event": "attempt", "target": {**metadata, "api": "uia", "view": view}})
            try:
                if uia is None:
                    raise OSError("UIA initialization failed")
                sample = uia.measure(hwnd, view)
            except Exception:
                sample = {"unavailable": True}
            item = {**metadata, "api": "uia", "view": view, **sample}
            samples.append(item)
            emit({"event": "sample", "sample": item})
        for label, object_id in (("client", 0xFFFFFFFC), ("window", 0)):
            emit({"event": "attempt", "target": {**metadata, "api": "msaa", "object": label}})
            try:
                sample = summarize(backend.root(hwnd, object_id), backend)
            except Exception:
                sample = {"unavailable": True}
            item = {**metadata, "api": "msaa", "object": label, **sample}
            samples.append(item)
            emit({"event": "sample", "sample": item})
    return {"schema_version": 2, "status": "measured", "visible_windows": len(windows),
            "samples": samples, "target_limit_reached": len(targets) + len(descendants) > 24,
            "uia_initialized": uia is not None,
            "window_limit_reached": len(windows) > 8, "message_reading_verified": False}


def partial_report(output):
    result = {"schema_version": 2, "status": "partial_timeout", "samples": [],
              "message_reading_verified": False}
    for line in (output or b"").splitlines():
        try:
            event = json.loads(line)
            if event.get("event") == "sample":
                result["samples"].append(event["sample"])
                result.pop("pending_target", None)
            elif event.get("event") == "attempt":
                result["pending_target"] = event["target"]
            elif event.get("event") in ("inventory", "targets"):
                result.update({k: v for k, v in event.items() if k != "event"})
        except (ValueError, TypeError, AttributeError, KeyError):
            continue
    return result


def run_bounded():
    try:
        result = subprocess.run([sys.executable, "-m", "desktop.accessibility_probe", "--worker"],
                                cwd=Path(__file__).resolve().parent.parent, capture_output=True,
                                timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            return {"status": "probe_failed"}
        return json.loads(result.stdout.splitlines()[-1])
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            return partial_report(exc.stdout)
        return {"status": "timeout", "message_reading_verified": False}
    except Exception:
        return {"status": "probe_failed"}


def main():
    if "--worker" in sys.argv:
        try:
            result = probe(lambda event: print(json.dumps(event), flush=True))
        except ImportError:
            result = {"status": "missing_dependency"}
        except Exception:
            result = {"status": "probe_failed"}
    else:
        result = run_bounded()
        destination = Path(__file__).resolve().parent.parent / "_reports" / "wechat-msaa-summary.json"
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=None if "--worker" in sys.argv else 2))


if __name__ == "__main__":
    main()
