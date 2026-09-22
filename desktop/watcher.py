"""Opt-in visible-window watcher. Independent implementation; no wxauto dependency."""
from __future__ import annotations

import ctypes
import hashlib
from ctypes import wintypes

from PIL import ImageGrab

from desktop.service import ServiceError


def signature(image):
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def header_matches(reference, current):
    # Require exact title pixels. False pauses are preferable to cross-chat capture.
    return reference.size == current.size and signature(reference) == signature(current)


class SettledFrames:
    def __init__(self, settle=1.5, cooldown=5):
        self.settle, self.cooldown = settle, cooldown
        self.pending = None
        self.since = 0
        self.processed = None
        self.last_submit = float("-inf")

    def observe(self, frame, now):
        if frame != self.pending:
            self.pending, self.since = frame, now
        return (frame != self.processed and now - self.since >= self.settle
                and now - self.last_submit >= self.cooldown)

    def submitted(self, frame, now):
        self.processed, self.last_submit = frame, now


class WindowBinding:
    """Only the selected, unchanged, foreground Weixin window may be captured."""
    def __init__(self, message_box, title_box):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u, k = self.user32, self.kernel32
        u.WindowFromPoint.argtypes, u.WindowFromPoint.restype = [wintypes.POINT], wintypes.HWND
        u.GetAncestor.argtypes, u.GetAncestor.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        k.OpenProcess.argtypes, k.OpenProcess.restype = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.message_box, self.title_box = tuple(message_box), tuple(title_box)
        if title_box[3] > message_box[1]:
            raise ServiceError("请框选消息区上方的联系人标题，不能与消息区域重叠。")
        x0, y0, x1, y1 = message_box
        self.hwnd = self.at((x0 + x1) // 2, (y0 + y1) // 2)
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(self.hwnd, ctypes.byref(pid))
        self.pid = pid.value
        process = k.OpenProcess(0x1000, False, pid)
        if not process:
            raise ServiceError("无法确认所选窗口属于微信，请重新框选。")
        try:
            size, name = wintypes.DWORD(32768), ctypes.create_unicode_buffer(32768)
            if not k.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size)) or not name.value.lower().endswith("\\weixin.exe"):
                raise ServiceError("自动采集只支持已登录的 Windows 微信窗口。")
        finally:
            k.CloseHandle(process)
        self.rect = self.window_rect()
        for box in (self.message_box, self.title_box):
            if not (self.rect[0] <= box[0] < box[2] <= self.rect[2] and self.rect[1] <= box[1] < box[3] <= self.rect[3]):
                raise ServiceError("消息区和标题区必须位于同一个微信窗口内。")
        if not self.uncovered():
            raise ServiceError("微信被其他窗口遮挡，请重新框选。")

    def at(self, x, y):
        return self.user32.GetAncestor(self.user32.WindowFromPoint(wintypes.POINT(x, y)), 2)

    def window_rect(self):
        rect = wintypes.RECT()
        if not self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            raise ServiceError("微信窗口已关闭，请重新绑定。")
        return rect.left, rect.top, rect.right, rect.bottom

    def uncovered(self):
        for x0, y0, x1, y1 in (self.message_box, self.title_box):
            for x in (x0 + 1, (x0 + x1) // 2, x1 - 1):
                for y in (y0 + 1, (y0 + y1) // 2, y1 - 1):
                    if self.at(x, y) != self.hwnd:
                        return False
        return True

    def ready(self):
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(self.hwnd, ctypes.byref(pid))
        if pid.value != self.pid:
            raise ServiceError("微信进程已改变，请重新绑定。")
        if self.window_rect() != self.rect:
            raise ServiceError("微信窗口移动或缩放，自动采集已停止，请重新框选。")
        return self.user32.GetForegroundWindow() == self.hwnd and self.uncovered()

    def grab(self, box):
        return ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")

    def capture(self, reference):
        if not self.ready():
            return None
        if not header_matches(reference, self.grab(self.title_box)):
            raise ServiceError("聊天标题发生变化，自动采集已停止。请确认好友后重新绑定。")
        image = self.grab(self.message_box)
        # Recheck immediately after capture; do not submit a frame across a switch.
        if not self.ready() or not header_matches(reference, self.grab(self.title_box)):
            raise ServiceError("采集时窗口或标题改变，已停止自动更新。")
        return image
