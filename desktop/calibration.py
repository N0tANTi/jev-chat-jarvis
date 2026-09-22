"""Explicit first-frame review; no learned guesses about unseen speakers."""
from desktop.service import ServiceError, parse_transcript


def reviewed_rows(rows, choices):
    if len(rows) != len(choices) or any(c not in ("我", "对方", "忽略") for c in choices):
        raise ServiceError("请为每条选择「我 / 对方 / 忽略」。图片、语音和系统提示请选择忽略。")
    text = "\n".join(f"{c}：{' '.join(row.splitlines())}" for row, c in zip(rows, choices) if c != "忽略")
    messages = parse_transcript(text)
    return text, messages


def validate_first_frame(reference, observed, ignored):
    def clean(text):
        return "".join(text.split())
    ignored = {clean(s) for s in ignored}
    if {m["from"] for m in reference} != {"me", "other"}:
        raise ServiceError("首次校准需要至少一条「我」和一条「对方」的文字消息。")
    if any(clean(m["text"]) in ignored for m in reference):
        raise ServiceError("忽略项与保留的正文重复，无法可靠校准，请换一段文字聊天。")
    actual = [(m["from"], clean(m["text"])) for m in observed if clean(m["text"]) not in ignored]
    expected = [(m["from"], clean(m["text"])) for m in reference]
    if actual != expected:
        raise ServiceError("首次自动识别与校对不一致，未开启连续生成。请保持原聊天画面，重新校对；也可以手动生成。")


def remove_ignored_first_frame(text, ignored):
    ignored = {"".join(s.split()) for s in ignored}
    return "\n".join(line for line in text.splitlines()
                     if "".join(line.replace(":", "：", 1).partition("：")[2].split()) not in ignored)


def open_review(app):
    import tkinter as tk
    from tkinter import ttk
    rows = getattr(app, "direct_rows", None)
    snapshot = getattr(app, "direct_snapshot", None)
    binding = getattr(app, "direct", None)
    if not rows or not binding or not snapshot:
        app.status.set("请先点击「直接读取微信」，选择独立单聊，再进行一次校对。")
        return
    rows = list(rows)
    binding = dict(binding)
    app.stop_watch()
    epoch = app.direct_epoch
    dialog = tk.Toplevel(app.root)
    dialog.title("校对一次 · 自动更新建议")
    dialog.geometry("760x600")
    ttk.Label(dialog, text="自动识别会上传本次消息区到 MinerU，预选我 / 对方；请检查，未确认项再点选。", padding=12).pack(anchor="w")
    area = ttk.Frame(dialog)
    area.pack(fill="both", expand=True)
    canvas = tk.Canvas(area, highlightthickness=0)
    scroll = ttk.Scrollbar(area, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    content = ttk.Frame(canvas)
    canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
    choices = []
    for i, row in enumerate(rows):
        line = ttk.Frame(content, padding=8)
        line.pack(fill="x")
        ttk.Label(line, text=f"{i+1}. {row}", wraplength=410, width=48).pack(side="left")
        choice = tk.StringVar(value="待确认")
        choices.append(choice)
        for label in ("我", "对方", "忽略"):
            ttk.Radiobutton(line, text=label, value=label, variable=choice).pack(side="left", padx=5)
        ttk.Label(line, textvariable=choice, width=6).pack(side="left", padx=3)
    notes = tk.StringVar(value="自动运行会将消息截图发送 MinerU，将文字发送 DeepSeek / TypeSafe。\n保持微信前台可见；生成建议后由你复制发送。自动内容不写入好友记忆。")
    ttk.Label(dialog, textvariable=notes, wraplength=710, padding=12).pack(anchor="w")
    from desktop.speaker_prefill import attach_prefill
    attach_prefill(app, dialog, binding, snapshot, choices, notes, epoch)

    def finish(automatic):
        if app.direct_epoch != epoch:
            notes.set("来源已清空或档案已切换，请关闭面板重新读取。")
            return
        try:
            selected = [v.get() for v in choices]
            text, messages = reviewed_rows(rows, selected)
            if automatic and {m["from"] for m in messages} != {"me", "other"}:
                raise ServiceError("校准至少需要双方各一条文字消息；也可先选择仅保存校对。")
            if automatic and not all(snapshot.get(k) for k in ("message_box", "title_box")):
                raise ServiceError("当前窗口未提供截图区域，暂不能自动校准；可保存校对后手动生成。")
            app.set_transcript(text)
            app.reviewed.set(True)
            dialog.destroy()
            if automatic:
                app.start_calibrated(binding, snapshot, messages,
                                     [r for r, c in zip(rows, selected) if c == "忽略"])
            else:
                app.status.set("校对已保存，可直接生成回复。")
        except ServiceError as exc:
            notes.set(str(exc))

    buttons = ttk.Frame(dialog, padding=12)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="仅保存校对", command=lambda: finish(False)).pack(side="left")
    ttk.Button(buttons, text="校对完成，自动运行（云端）", command=lambda: finish(True)).pack(side="right")
