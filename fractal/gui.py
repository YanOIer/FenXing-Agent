"""fractal.gui —— 分形Agent 的极简 tkinter 交互窗口。

运行方式:

    python fenxing.py --gui

窗口左侧（或上方）显示 Agent 回答，底部输入框提问；每轮问答后
自动用系统浏览器打开分形图。调用模型耗时在后台线程中执行，
界面不会卡死。
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext

import webbrowser


class FractalGui:
    """基于 tkinter 的极简交互窗口。"""

    def __init__(self, agent_kwargs: dict | None = None):
        self.agent_kwargs = agent_kwargs or {}
        self.fa = None
        self.pending = False

        self.root = tk.Tk()
        self.root.title("分形Agent · FractalAgent")
        self.root.geometry("800x600")
        self.root.minsize(640, 480)
        self._build_ui()
        self._init_agent()

    def _build_ui(self) -> None:
        tk.Label(
            self.root,
            text="分形Agent · 每次问答生成分形推理图",
            font=("Microsoft YaHei", 14, "bold"),
        ).pack(pady=12)

        tk.Label(self.root, text="Agent 回答：", anchor="w").pack(
            padx=16, pady=(8, 0), fill="x"
        )
        self.answer_box = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, state="disabled", font=("Microsoft YaHei", 11)
        )
        self.answer_box.pack(padx=16, pady=(4, 8), fill="both", expand=True)

        input_frame = tk.Frame(self.root)
        input_frame.pack(padx=16, pady=(0, 8), fill="x")
        self.entry = tk.Entry(input_frame, font=("Microsoft YaHei", 11))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _e: self._on_send())
        self.entry.focus_set()

        self.send_btn = tk.Button(
            input_frame, text="发送", command=self._on_send, width=10
        )
        self.send_btn.pack(side="left", padx=(8, 0))

        self.status = tk.Label(self.root, text="Agent 初始化中…", anchor="w", relief="sunken")
        self.status.pack(side="bottom", fill="x")

        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="退出", command=self.root.quit)
        menubar.add_cascade(label="文件", menu=file_menu)
        self.root.config(menu=menubar)

    def _init_agent(self) -> None:
        """在后台线程初始化 FractalAgent，避免界面冻结。"""
        def load() -> None:
            try:
                from .agent import FractalAgent
                self.fa = FractalAgent(agent_kwargs=self.agent_kwargs)
                self.root.after(0, lambda: self.status.config(text="Agent 初始化完成，可以开始提问"))
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self.status.config(text=f"初始化失败：{exc}"))
                self.root.after(0, lambda: messagebox.showerror(
                    "初始化失败", f"{exc}\n\n请检查 ~/.hermes/.env 与 ~/.hermes/config.yaml 配置。"
                ))
        threading.Thread(target=load, daemon=True).start()

    def _on_send(self) -> None:
        if self.pending or self.fa is None:
            return
        q = self.entry.get().strip()
        if not q:
            return
        self.entry.delete(0, tk.END)
        self._append_text(f"你：{q}\n")
        self.send_btn.config(state="disabled")
        self.status.config(text="思考中…")
        self.pending = True

        def ask() -> None:
            try:
                result = self.fa.ask(q)
                answer = result.get("answer") or "（无回答）"
                html_path = result.get("html_path")
                pending_children = result.get("pending_children", 0)
                trace_error = result.get("trace_error")

                lines = [f"Agent：{answer}\n"]
                if html_path:
                    lines.append(f"分形图：{html_path}\n")
                if pending_children:
                    lines.append(f"⏳ {pending_children} 个子任务仍在后台运行\n")
                if trace_error:
                    lines.append(f"（绘图出错：{trace_error}）\n")
                lines.append("\n")

                def update() -> None:
                    self._append_text("".join(lines))
                    self.send_btn.config(state="normal")
                    self.pending = False
                    if html_path:
                        self._open_html(html_path)
                        self.status.config(text="已打开分形图")
                    else:
                        self.status.config(text="回答完成")
                self.root.after(0, update)
            except Exception as exc:  # noqa: BLE001
                def err() -> None:
                    self._append_text(f"错误：{exc}\n\n")
                    self.send_btn.config(state="normal")
                    self.pending = False
                    self.status.config(text="调用失败")
                self.root.after(0, err)

        threading.Thread(target=ask, daemon=True).start()

    def _append_text(self, text: str) -> None:
        self.answer_box.config(state="normal")
        self.answer_box.insert(tk.END, text)
        self.answer_box.see(tk.END)
        self.answer_box.config(state="disabled")

    def _open_html(self, path: str) -> None:
        try:
            uri = Path(path).resolve().as_uri()
            webbrowser.open(uri, new=2)
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        self.root.mainloop()


def main(agent_kwargs: dict | None = None) -> int:
    FractalGui(agent_kwargs).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
