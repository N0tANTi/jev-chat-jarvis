"""User-controlled editor for local persona, facts, history and model observations."""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from desktop.memory import history_messages
from desktop.service import ServiceError


def open_profiles(app):
    if getattr(app, "profile_window", None) and app.profile_window.winfo_exists():
        app.profile_window.lift()
        return
    window = tk.Toplevel(app.root)
    app.profile_window = window
    window.title("角色与好友记忆")
    window.geometry("960x740")
    window.minsize(880, 600)
    shell = ttk.Frame(window, padding=18)
    shell.pack(fill="both", expand=True)
    ttk.Label(shell, text="角色与好友记忆", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
    ttk.Label(shell, text="档案只存本机。生成回复会使用当前好友的背景；分析历史会把该好友历史发送给 DeepSeek。", wraplength=800).pack(anchor="w", pady=8)
    row = ttk.Frame(shell)
    row.pack(fill="x")
    choices = tk.StringVar()
    combo = ttk.Combobox(row, textvariable=choices, state="readonly", width=48)
    combo.pack(side="left", fill="x", expand=True)
    mapping = {}
    selected = {"id": None}
    notebook = ttk.Notebook(shell)
    notebook.pack(fill="both", expand=True, pady=12)

    def text_tab(title, hint):
        tab = ttk.Frame(notebook, padding=12)
        notebook.add(tab, text=title)
        ttk.Label(tab, text=hint, wraplength=750).pack(anchor="w", pady=(0, 8))
        text = tk.Text(tab, wrap="word", font=("Microsoft YaHei UI", 11), undo=True)
        text.pack(fill="both", expand=True)
        return text, tab

    persona, _ = text_tab("我的角色", "所有好友共用。例如：像平时的我，简短直接，温和但不讨好；少用表情，不替我许诺。")
    facts, facts_tab = text_tab("已确认背景", "只属于选中好友。例如：同事；合作项目；明确表达过的偏好。模型不会改写这里。")
    learn = tk.BooleanVar(value=False)
    ttk.Checkbutton(facts_tab, text="生成回复后保存核对的聊天，并在有新内容时更新模型观察", variable=learn).pack(anchor="w", pady=8)
    history, history_tab = text_tab("导入历史", "每条一行「我：…」或「对方：…」。点击导入保存到本机，不会立即上传。每好友最多保留最近 500 条。")
    observations, _ = text_tab("模型观察与依据", "以下内容是推测。更新会修正旧观察，保留最近三版；可用下方按钮清除。")
    notes = tk.StringVar(value="请选择好友；切换前请保存编辑。")
    ttk.Label(shell, textvariable=notes, wraplength=790).pack(anchor="w")

    def fill(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def load(_=None):
        cid = mapping.get(choices.get())
        selected["id"] = cid
        fill(persona, app.store.data["persona"])
        if not cid:
            return
        p = app.store.get(cid)
        fill(facts, p["facts"])
        learn.set(p["learn"])
        fill(history, "")
        current = p["observations"]
        rendered = "尚无模型观察。导入历史后点击「分析已保存历史」。"
        if current:
            confidence = {"low": "低", "medium": "中", "high": "高"}
            rendered = f"更新时间：{current['updated_at']}\n模型推测：{current['summary']}\n"
            for tag in current["tags"]:
                rendered += f"\n• {tag['label']}（模型把握：{confidence[tag['confidence']]}）\n"
                for item in tag["evidence"]:
                    rendered += f"  依据｜{'我' if item['from'] == 'me' else '对方'}：{item['text']}\n"
            if p["previous_observations"]:
                rendered += "\n—— 旧版观察（仅供追溯，不作为当前标签）——\n"
                for old in reversed(p["previous_observations"]):
                    rendered += f"\n{old['updated_at']}\n{old['summary']}\n" + " / ".join(t["label"] for t in old["tags"]) + "\n"
        fill(observations, rendered)
        observations.configure(state="disabled")
        notes.set(f"本机已保存 {len(p['history'])} 条历史；保留 {len(p['previous_observations'])} 版旧观察。切换前请保存。")

    def refresh(cid=None):
        mapping.clear()
        for key, p in app.store.data["contacts"].items():
            mapping[f"{p['name']} · {key[:6]}"] = key
        combo.configure(values=list(mapping))
        target = cid or selected["id"] or app.contact_id
        choices.set(next((label for label, key in mapping.items() if key == target), next(iter(mapping), "")))
        load()

    def guarded(action):
        try:
            action()
        except (ServiceError, OSError, UnicodeError) as exc:
            notes.set(str(exc) if isinstance(exc, ServiceError) else "本地文件读写失败；请检查路径、格式或磁盘空间。")

    def create():
        name = simpledialog.askstring("新建好友档案", "备注名（同名好友请加区分说明）：", parent=window)
        if name:
            refresh(app.store.create(name))
            app.refresh_contacts()

    def save():
        app.store.configure(selected["id"], persona=persona.get("1.0", "end"), facts=facts.get("1.0", "end"), learn=learn.get())
        app.invalidate()
        notes.set("角色、确认背景和学习开关已保存。")

    def import_history():
        messages = history_messages(history.get("1.0", "end"))
        app.store.append(selected["id"], messages)
        app.invalidate()
        load()
        notes.set("历史已保存到选中好友；点击「分析已保存历史」才会上传分析。")

    def read_file():
        path = filedialog.askopenfilename(parent=window, filetypes=[("UTF-8 文本", "*.txt")])
        if path:
            p = Path(path)
            if p.stat().st_size > 500_000:
                raise ServiceError("文件过大，请分段提供不超过 500 条消息。")
            fill(history, p.read_text(encoding="utf-8-sig"))

    def use():
        save()
        app.select_contact(selected["id"])
        window.destroy()

    def forget():
        cid = selected["id"]
        app.store.get(cid)
        if messagebox.askyesno("清除好友记忆", "清除该好友已保存的历史、模型标签与旧版本？你的角色和手工背景保留。", parent=window):
            app.store.forget(cid)
            app.invalidate()
            load()

    ttk.Button(row, text="新建好友", command=lambda: guarded(create)).pack(side="left", padx=6)
    combo.bind("<<ComboboxSelected>>", load)
    buttons = ttk.Frame(history_tab)
    buttons.pack(fill="x", pady=(8, 0))
    ttk.Button(buttons, text="选择文本文件", command=lambda: guarded(read_file)).pack(side="left")
    ttk.Button(buttons, text="导入并保存历史", command=lambda: guarded(import_history)).pack(side="left", padx=8)
    actions = ttk.Frame(shell)
    actions.pack(fill="x", pady=10)
    ttk.Button(actions, text="保存设置", command=lambda: guarded(save)).pack(side="left")
    ttk.Button(actions, text="分析已保存历史", command=lambda: guarded(lambda: app.learn_profile(selected["id"], notes))).pack(side="left", padx=5)
    ttk.Button(actions, text="刷新观察", command=load).pack(side="left")
    ttk.Button(actions, text="清除好友记忆", command=lambda: guarded(forget)).pack(side="left", padx=5)
    ttk.Button(actions, text="清除观察并停学", command=lambda: guarded(lambda: (app.store.forget_observations(selected["id"]), app.invalidate(), load()))).pack(side="left")
    ttk.Button(actions, text="使用此好友", command=lambda: guarded(use)).pack(side="right")
    refresh()
