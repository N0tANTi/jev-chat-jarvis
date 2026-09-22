"""Run with python -m desktop.app --env-file PATH. All cloud actions are explicit."""
from __future__ import annotations

import argparse
import ctypes
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageGrab, ImageTk

from desktop.service import (Generation, KEY_NAMES, MAX_IMAGE_PIXELS, ServiceError,
                             analyze, load_keys, parse_transcript, recognize, to_transcript)
from desktop.memory import ProfileStore, analyze_profile

BG = "#f4f5f2"
INK = "#182d2a"
MUTED = "#64736f"
TEAL = "#146b58"


class App:
    def __init__(self, root, keys):
        self.root, self.keys = root, keys
        self.generation = Generation()
        self.events = queue.Queue()
        self.worker = None
        self.picture = None
        self.replies = []
        self.suppress_edit = False
        self.closed = False
        self.store = ProfileStore()
        self.contact_id = None
        self.contact_choices = {}
        root.title("Jev 桌面助手 · 试用版")
        root.geometry("1100x820")
        root.minsize(960, 730)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 9))
        style.configure("Accent.TButton", background=TEAL, foreground="white")
        style.map("Accent.TButton", background=[("active", "#205d50"), ("disabled", "#b8c7c0")])
        style.configure("TCheckbutton", background=BG, font=("Microsoft YaHei UI", 10))
        shell = ttk.Frame(root, padding=24)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Jev / 对话副驾", font=("Microsoft YaHei UI", 21, "bold")).pack(anchor="w")
        ttk.Label(shell, text="从当前聊天出发，给下一句多几个选择。", foreground=MUTED).pack(anchor="w", pady=(4, 15))
        missing = [n for n in KEY_NAMES if not keys.get(n)]
        self.config_label = ttk.Label(shell, text="配置已就绪 · MinerU / DeepSeek Flash / Jev" if not missing else "缺少配置：" + " / ".join(missing), foreground=TEAL if not missing else "#a64429")
        self.config_label.pack(anchor="w")
        ttk.Label(shell, text="点击识别：所选图片上传 MinerU。点击生成：核对后的文字发送 DeepSeek 和 TypeSafe。", foreground=MUTED).pack(anchor="w", pady=(5, 12))

        toolbar = ttk.Frame(shell)
        toolbar.pack(fill="x")
        self.capture_btn = ttk.Button(toolbar, text="1  截取聊天", command=self.capture)
        self.capture_btn.pack(side="left")
        self.open_btn = ttk.Button(toolbar, text="导入截图", command=self.open_image)
        self.open_btn.pack(side="left", padx=6)
        self.ocr_btn = ttk.Button(toolbar, text="2  识别聊天", command=self.ocr, state="disabled")
        self.ocr_btn.pack(side="left")
        self.analyze_btn = ttk.Button(toolbar, text="3  生成回复", style="Accent.TButton", command=self.generate)
        self.analyze_btn.pack(side="left", padx=6)
        ttk.Button(toolbar, text="清空 / 取消", command=self.clear).pack(side="right")

        self.status = tk.StringVar(value="先截取单聊消息区域，排除标题、时间、联系人列表和输入框。也可以直接粘贴聊天文字。")
        ttk.Label(shell, textvariable=self.status, wraplength=1010, foreground=TEAL).pack(anchor="w", pady=12)
        middle = ttk.Frame(shell)
        middle.pack(fill="both", expand=True)
        left = ttk.Frame(middle)
        left.pack(side="left", fill="both", expand=True, padx=(0, 16))
        ttk.Label(left, text="聊天快照", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        self.preview = tk.Label(left, text="截图只在内存中保留\n不会自动读取微信或上传", bg="#e6ebe5", fg=MUTED,
                                font=("Microsoft YaHei UI", 10), width=34, height=10)
        self.preview.pack(fill="both", expand=True, pady=(8, 5))
        ttk.Label(left, text="切换聊天或出现新消息后，请重新截图。\n本版面向微信单聊；群聊和深色气泡请手动核对。", foreground=MUTED).pack(anchor="w")
        right = ttk.Frame(middle)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="核对识别内容", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ttk.Label(right, text="每条一行：我：… / 对方：…；删除非消息文字。", foreground=MUTED).pack(anchor="w", pady=(4, 6))
        self.transcript = tk.Text(right, height=10, width=51, wrap="word", font=("Microsoft YaHei UI", 11),
                                  relief="flat", padx=12, pady=10, undo=True, bg="white", fg=INK)
        self.transcript.pack(fill="both", expand=True)
        self.transcript.bind("<<Modified>>", self.on_edit)
        self.reviewed = tk.BooleanVar(value=False)
        ttk.Checkbutton(right, text="已核对发言人、顺序，并删除标题和系统提示", variable=self.reviewed).pack(anchor="w", pady=(8, 0))

        context = ttk.Frame(shell)
        context.pack(fill="x", pady=12)
        ttk.Label(context, text="关系 / 回复偏好（可选）").pack(side="left", padx=(0, 12))
        self.relationship = tk.StringVar(value="")
        ttk.Entry(context, textvariable=self.relationship, font=("Microsoft YaHei UI", 10)).pack(side="left", fill="x", expand=True)
        self.relationship.trace_add("write", lambda *_: self.invalidate())
        friend_row = ttk.Frame(shell)
        friend_row.pack(fill="x", pady=(0, 8))
        ttk.Label(friend_row, text="当前好友档案").pack(side="left", padx=(0, 12))
        self.contact_label = tk.StringVar(value="不使用好友记忆")
        self.contact_combo = ttk.Combobox(friend_row, textvariable=self.contact_label, state="readonly", width=35)
        self.contact_combo.pack(side="left", fill="x", expand=True)
        self.contact_combo.bind("<<ComboboxSelected>>", lambda _: self.select_contact(self.contact_choices.get(self.contact_label.get())))
        from desktop.profile_ui import open_profiles
        ttk.Button(friend_row, text="角色 / 好友记忆", command=lambda: open_profiles(self)).pack(side="left", padx=8)
        self.refresh_contacts()
        self.insight = tk.StringVar(value="回复建议将显示在下方；这些是模型推测，请结合实际语境判断。")
        ttk.Label(shell, textvariable=self.insight, foreground=MUTED, wraplength=1000).pack(anchor="w", pady=(0, 6))
        self.cards = []
        for i in range(3):
            frame = tk.Frame(shell, bg="white", padx=12, pady=9)
            frame.pack(fill="x", pady=3)
            label = tk.Label(frame, text=f"0{i + 1}  等待生成", bg="white", fg=INK,
                             font=("Microsoft YaHei UI", 10), wraplength=830, justify="left", anchor="w")
            label.pack(side="left", fill="x", expand=True)
            button = ttk.Button(frame, text="复制", command=lambda n=i: self.copy_reply(n), state="disabled")
            button.pack(side="right", padx=(12, 0))
            self.cards.append((label, button))
        ttk.Label(shell, text="不自动发送 · 不读取微信数据库 · 好友档案仅在你保存或开启学习后落盘", foreground=MUTED).pack(anchor="w", pady=(10, 0))
        root.after(100, self.poll)

    def invalidate(self):
        self.generation.invalidate()
        self.replies = []
        if hasattr(self, "cards"):
            for i, (label, button) in enumerate(self.cards):
                label.configure(text=f"0{i + 1}  等待生成")
                button.configure(state="disabled")
            self.insight.set("回复建议将显示在下方；这些是模型推测，请结合实际语境判断。")

    def on_edit(self, _=None):
        if self.transcript.edit_modified():
            if not self.suppress_edit:
                self.invalidate()
                self.reviewed.set(False)
            self.transcript.edit_modified(False)

    def set_transcript(self, text):
        self.suppress_edit = True
        self.transcript.delete("1.0", "end")
        self.transcript.insert("1.0", text)
        self.transcript.edit_modified(False)
        self.suppress_edit = False
        self.reviewed.set(False)

    def set_picture(self, picture):
        self.invalidate()
        self.picture = picture.convert("RGB")
        self.set_transcript("")
        thumb = self.picture.copy()
        thumb.thumbnail((380, 245))
        self.preview_image = ImageTk.PhotoImage(thumb)
        self.preview.configure(image=self.preview_image, text="", width=380, height=245)
        self.status.set("截图已就绪，尚未上传。确认左侧只有本次聊天消息后，点击「识别聊天」。")
        self.update_buttons()

    def open_image(self):
        filename = filedialog.askopenfilename(title="选择聊天截图", filetypes=[("聊天截图", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if not filename:
            return
        try:
            with Image.open(filename) as picture:
                if picture.width * picture.height > MAX_IMAGE_PIXELS:
                    raise ValueError()
                self.set_picture(picture.copy())
        except Exception:
            self.status.set("无法读取图片或尺寸过大，请选择不超过 1600 万像素的图片。")

    def capture(self):
        # The user starts capture. No screen access on launch or in background workers.
        self.invalidate()
        self.root.withdraw()
        self.root.after(300, self.select_region)

    def select_region(self):
        try:
            screen = ImageGrab.grab(all_screens=True)
            x = ctypes.windll.user32.GetSystemMetrics(76)
            y = ctypes.windll.user32.GetSystemMetrics(77)
            overlay = tk.Toplevel(self.root)
            overlay.overrideredirect(True)
            overlay.geometry(f"{screen.width}x{screen.height}+0+0")
            overlay.attributes("-topmost", True)
            canvas = tk.Canvas(overlay, width=screen.width, height=screen.height, highlightthickness=0, cursor="crosshair")
            canvas.pack()
            # Tk negative geometry means distance from the right edge, not a virtual
            # desktop coordinate. Position our own overlay using absolute pixels.
            overlay.update_idletasks()
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            hwnd = user32.GetParent(overlay.winfo_id()) or overlay.winfo_id()
            user32.SetWindowPos(hwnd, None, x, y, screen.width, screen.height, 0x0014)
            photo = ImageTk.PhotoImage(screen)
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.photo = photo
            canvas.create_rectangle(12, 12, 680, 60, fill=INK, outline=INK)
            canvas.create_text(28, 36, text="拖动框选消息气泡（不含标题 / 输入框） · Esc 取消 · 此时不会上传", fill="white", anchor="w", font=("Microsoft YaHei UI", 11))
            state = {}

            def finish(picture=None):
                overlay.destroy()
                self.root.deiconify()
                if picture is not None:
                    self.set_picture(picture)

            def start(event):
                state["start"] = (event.x, event.y)
                if state.get("rect"):
                    canvas.delete(state["rect"])
                state["rect"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#23bb91", width=3)

            def move(event):
                if "start" in state:
                    canvas.coords(state["rect"], *state["start"], event.x, event.y)

            def end(event):
                if "start" not in state:
                    return
                a, b = state["start"]
                box = (max(0, min(a, event.x)), max(0, min(b, event.y)),
                       min(screen.width, max(a, event.x)), min(screen.height, max(b, event.y)))
                if box[2] - box[0] >= 60 and box[3] - box[1] >= 40:
                    finish(screen.crop(box))

            canvas.bind("<ButtonPress-1>", start)
            canvas.bind("<B1-Motion>", move)
            canvas.bind("<ButtonRelease-1>", end)
            overlay.bind("<Escape>", lambda _: finish())
            overlay.focus_force()
        except Exception:
            self.root.deiconify()
            self.status.set("截屏失败。请改用「导入截图」，或直接粘贴聊天文字。")

    def update_buttons(self):
        busy = self.worker is not None and self.worker.is_alive()
        for button in (self.capture_btn, self.open_btn, self.analyze_btn):
            button.configure(state="disabled" if busy else "normal")
        self.ocr_btn.configure(state="normal" if self.picture is not None and not busy else "disabled")

    def start_job(self, kind, operation, *, preserve_replies=False):
        if self.worker is not None and self.worker.is_alive():
            self.status.set("上个请求还在收尾，请稍候。")
            return
        if preserve_replies:
            self.generation.invalidate()
        else:
            self.invalidate()
        revision, cancel = self.generation.revision, self.generation.cancel

        def progress(text):
            self.events.put((revision, "progress", text))

        def run():
            try:
                result = operation(cancel, progress)
                self.events.put((revision, kind, result))
            except ServiceError as exc:
                self.events.put((revision, "error", str(exc)))
            except Exception:
                self.events.put((revision, "error", "处理失败，请稍后重试。没有将错误详情或聊天内容写入日志。"))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()
        self.update_buttons()

    def ocr(self):
        if self.picture is None:
            return
        picture = self.picture.copy()
        self.set_transcript("")
        self.start_job("ocr", lambda cancel, progress: to_transcript(
            recognize(picture, self.keys["MINERU_API_TOKEN"], cancel, progress), picture))

    def generate(self):
        try:
            messages = parse_transcript(self.transcript.get("1.0", "end"))
            if not self.reviewed.get():
                raise ServiceError("请先核对文字与发言人，再勾选核对完成。")
            relationship = self.relationship.get().strip()[:500] or "unspecified"
            cid = self.contact_id
            background = self.store.context(cid)
            profile = self.store.get(cid) if cid else None
            should_learn = False
            if profile and profile["learn"]:
                should_learn = self.store.append(cid, messages)
                profile = self.store.get(cid)
            def operation(cancel, progress):
                result = analyze(messages, relationship, self.keys, cancel, progress, memory=background)
                result["learn_contact"] = (cid, profile["version"]) if should_learn else None
                return result
            self.start_job("analysis", operation)
        except ServiceError as exc:
            self.status.set(str(exc))

    def refresh_contacts(self):
        self.contact_choices = {"不使用好友记忆": None}
        for cid, p in self.store.data["contacts"].items():
            self.contact_choices[f"{p['name']} · {cid[:6]}"] = cid
        self.contact_combo.configure(values=list(self.contact_choices))
        self.contact_label.set(next((name for name, cid in self.contact_choices.items() if cid == self.contact_id), "不使用好友记忆"))

    def select_contact(self, cid):
        # OCR carries no stable contact identity; switching always clears the snapshot.
        self.clear()
        self.relationship.set("")
        self.contact_id = cid
        self.refresh_contacts()
        self.status.set("已切换档案并清空旧聊天，请为当前好友重新截图或粘贴消息。")

    def learn_profile(self, cid, notes=None, *, expected=None):
        if self.worker is not None and self.worker.is_alive():
            if notes:
                notes.set("上个请求还在收尾，请稍后再分析。")
            return
        profile = self.store.get(cid)
        if expected is not None and profile["version"] != expected:
            return
        version = profile["version"]
        if notes:
            notes.set("正在分析已保存的历史；完成后点击「刷新观察」。")
        # Memory jobs must not erase the reply cards that just arrived.
        self.start_job("memory", lambda cancel, progress: (cid, version, analyze_profile(
            profile, self.keys["DEEPSEEK_API_KEY"], cancel, progress)), preserve_replies=True)

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                revision, kind, value = self.events.get_nowait()
                if not self.generation.current(revision):
                    continue
                if kind in ("progress", "error"):
                    self.status.set(value)
                elif kind == "ocr":
                    self.set_transcript(value)
                    self.status.set("识别完成。请核对发言人，删除标题 / 时间 / 系统提示，然后生成回复。")
                elif kind == "analysis":
                    self.replies = value["candidates"]
                    best = value["best_index"]
                    for i, (label, button) in enumerate(self.cards):
                        label.configure(text=("推荐  " if i == best else f"0{i + 1}  ") + self.replies[i])
                        button.configure(state="normal")
                    intent = (value["answers"].get("true_intent") or {}).get("choice")
                    names = {"confirm_you_care": "希望被重视", "vent_anger": "表达不满", "request_action": "希望采取行动", "seek_explanation": "想了解原因", "casual_chat": "日常聊天", "close_topic": "准备结束话题"}
                    self.insight.set("Jev 推测：" + names.get(intent, "请结合语境判断") + "。推荐仅供参考，不代表对方的真实心理。")
                    self.status.set(f"{time.strftime('%H:%M:%S')} 已生成 · 基于本次快照。聊天有变化时请重新识别；复制后由你粘贴发送。")
                    followup = value.get("learn_contact")
                    if followup:
                        rev = self.generation.revision
                        self.root.after(150, lambda r=rev, pair=followup: self.learn_profile(pair[0], expected=pair[1]) if self.generation.current(r) else None)
                elif kind == "memory":
                    cid, version, observation = value
                    try:
                        applied = self.store.apply(cid, version, observation)
                        self.status.set("好友观察已更新（模型推测）。在「角色 / 好友记忆」中刷新查看依据。" if applied else "档案已修改，本次旧分析未写入。")
                    except (ServiceError, OSError):
                        self.status.set("档案更新未保存，请检查是否有其他程序窗口同时修改。")
        except queue.Empty:
            pass
        self.update_buttons()
        self.root.after(100, self.poll)

    def copy_reply(self, index):
        if index < len(self.replies):
            self.root.clipboard_clear()
            self.root.clipboard_append(self.replies[index])
            self.status.set("已复制。请确认微信当前联系人，再自行粘贴和发送。")

    def clear(self):
        self.invalidate()
        self.picture = None
        self.preview_image = None
        self.preview.configure(image="", text="截图只在内存中保留\n不会自动读取微信或上传", width=34, height=10)
        self.set_transcript("")
        self.status.set("已清空本次内容。已提交的云端请求无法撤回；其返回结果会被忽略。")
        self.update_buttons()

    def close(self):
        self.closed = True
        self.generation.invalidate()
        self.picture = None
        self.replies = []
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--demo", action="store_true", help="Load synthetic content without capture or API calls")
    args = parser.parse_args()
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    keys = load_keys(args.env_file or Path(__file__).parent / ".env")
    try:
        app = App(root, keys)
    except ServiceError as exc:
        messagebox.showerror("无法加载好友档案", str(exc), parent=root)
        root.destroy()
        return
    if args.demo:
        from desktop.smoke import synthetic_image
        app.set_picture(synthetic_image())
        app.set_transcript("对方：你今天怎么都不理我？\n我：刚才在开会，现在忙完了。\n对方：那晚上一起吃饭吗？")
        app.status.set("演示数据 · 尚未调用 API。勾选核对后可用本机配置测试生成回复。")
    root.mainloop()


if __name__ == "__main__":
    main()
