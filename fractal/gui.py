"""fractal.gui —— 分形Agent 的 CustomTkinter 交互窗口。

运行方式:

    python fenxing.py --gui

浅色米白主题 + 左右分栏布局 + 分形图列表。
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
import webbrowser


class FractalGui:
    """基于 CustomTkinter 的分形Agent 分栏交互窗口。"""

    def __init__(self, agent_kwargs: dict | None = None, streaming: bool = True,
                 rethink_http: bool = True):
        self.agent_kwargs = agent_kwargs or {}
        self.streaming = bool(streaming)
        self.rethink_http = bool(rethink_http)
        self.fa = None
        self.pending = False
        self._graph_paths: list[str] = []
        self._turn_count = 0
        self._model_name = ""

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk(fg_color="#f5f0e8")
        self.root.title("分形Agent · FractalAgent")
        self.root.geometry("960x640")
        self.root.minsize(800, 500)
        self._build_ui()
        self._init_agent()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        ctk.CTkLabel(
            self.root,
            text="分形Agent · 每次问答生成分形推理图",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(20, 8))

        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(padx=20, pady=(0, 8), fill="both", expand=True)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # -- 左侧面板 --
        self._build_left_panel(main_frame)

        # -- 右侧面板 --
        self._build_right_panel(main_frame)

        # -- 底部状态栏 --
        self.status = ctk.CTkLabel(
            self.root, text="Agent 初始化中…", anchor="w",
            font=ctk.CTkFont(size=12),
            fg_color="#ede6d9", corner_radius=0,
        )
        self.status.pack(side="bottom", fill="x", ipady=5)

        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="退出", command=self.root.quit)
        menubar.add_cascade(label="文件", menu=file_menu)
        self.root.config(menu=menubar)

    def _build_left_panel(self, parent) -> None:
        left = ctk.CTkFrame(parent, width=220, corner_radius=10,
                            fg_color=("#faf9f6", "#f0ebe0"))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.grid_propagate(False)
        left.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            left, text="分形图", font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(14, 4), sticky="w")

        ctk.CTkButton(
            left, text="打开最新分形图", width=180,
            command=self._open_latest_graph,
            fg_color="transparent", border_width=1,
            text_color=("#3b82f6", "#60a5fa"),
        ).grid(row=1, column=0, padx=14, pady=(0, 10))

        self.graph_list = ctk.CTkScrollableFrame(
            left, corner_radius=8, fg_color="transparent",
        )
        self.graph_list.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self._refresh_graph_list()

        # 分隔
        sep = ctk.CTkFrame(left, height=1, fg_color=("#e5e0d8", "#d5d0c8"))
        sep.grid(row=3, column=0, padx=14, pady=(4, 6), sticky="ew")

        # 会话信息
        info = ctk.CTkFrame(left, fg_color="transparent")
        info.grid(row=4, column=0, padx=14, pady=(0, 14), sticky="ew")

        self._info_model = ctk.CTkLabel(
            info, text="模型：-", font=ctk.CTkFont(size=12),
        )
        self._info_model.pack(anchor="w")
        self._info_turns = ctk.CTkLabel(
            info, text="对话：0 轮", font=ctk.CTkFont(size=12),
        )
        self._info_turns.pack(anchor="w", pady=(2, 0))
        self._info_graphs = ctk.CTkLabel(
            info, text="分形图：0 张", font=ctk.CTkFont(size=12),
        )
        self._info_graphs.pack(anchor="w", pady=(2, 0))

    def _build_right_panel(self, parent) -> None:
        right = ctk.CTkFrame(parent, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right, text="Agent 回答", font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
        ).grid(row=0, column=0, padx=4, pady=(0, 4), sticky="w")

        self.answer_box = ctk.CTkTextbox(
            right, font=ctk.CTkFont(size=15), wrap="word",
            corner_radius=10, border_width=1,
        )
        self.answer_box.configure(state="disabled")
        self.answer_box.grid(row=1, column=0, sticky="nsew")

        input_row = ctk.CTkFrame(right, fg_color="transparent")
        input_row.grid(row=2, column=0, padx=0, pady=(8, 0), sticky="ew")
        input_row.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            input_row, font=ctk.CTkFont(size=14),
            placeholder_text="输入问题，按 Enter 发送…",
            corner_radius=8,
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self._on_send())
        self.entry.focus_set()

        self.send_btn = ctk.CTkButton(
            input_row, text="发送", command=self._on_send,
            width=72, corner_radius=8,
        )
        self.send_btn.grid(row=0, column=1)

        self.clear_btn = ctk.CTkButton(
            input_row, text="清空", command=self._clear_chat,
            width=56, corner_radius=8,
            fg_color="transparent", border_width=1,
        )
        self.clear_btn.grid(row=0, column=2, padx=(6, 0))

    # ------------------------------------------------------------------ actions
    def _init_agent(self) -> None:
        def load() -> None:
            try:
                from .agent import FractalAgent
                self.fa = FractalAgent(
                    agent_kwargs=self.agent_kwargs,
                    streaming=self.streaming,
                    stream_callback=lambda path: self.root.after(0, lambda: self._open_html(path)),
                )
                self._model_name = (self.agent_kwargs or {}).get("model", "") or "deepseek-v4-pro"
                if self.rethink_http:
                    from .rethink_server import register_agent, start_rethink_server
                    start_rethink_server()
                    register_agent(self.fa)
                self.root.after(0, lambda: self._update_status("Agent 就绪，可以开始提问"))
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda exc=exc: self._update_status(f"初始化失败：{exc}"))
                self.root.after(0, lambda exc=exc: tk.messagebox.showerror(
                    "初始化失败", f"{exc}\n\n请检查 ~/.hermes/.env 与 ~/.hermes/config.yaml 配置。"
                ))
        threading.Thread(target=load, daemon=True).start()

    def _on_send(self) -> None:
        if self.pending or self.fa is None:
            return
        q = self.entry.get().strip()
        if not q:
            return
        self.entry.delete(0, "end")
        self._append_text(f"你：{q}\n")
        self.send_btn.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        self._update_status("思考中…")
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
                    lines.append(f"[pending] {pending_children} 个子任务仍在后台运行\n")
                if trace_error:
                    lines.append(f"（绘图出错：{trace_error}）\n")
                lines.append("\n")

                def update() -> None:
                    self._append_text("".join(lines))
                    self.send_btn.configure(state="normal")
                    self.clear_btn.configure(state="normal")
                    self.pending = False
                    if html_path:
                        self._add_graph(html_path)
                        self._open_html(html_path)
                    self._update_status("已打开分形图" if html_path else "回答完成")
                self.root.after(0, update)
            except Exception as exc:  # noqa: BLE001
                def err(exc=exc) -> None:
                    self._append_text(f"错误：{exc}\n\n")
                    self.send_btn.configure(state="normal")
                    self.clear_btn.configure(state="normal")
                    self.pending = False
                    self._update_status("调用失败")
                self.root.after(0, err)

        threading.Thread(target=ask, daemon=True).start()

    def _add_graph(self, path: str) -> None:
        self._graph_paths.append(path)
        self._turn_count += 1
        self._refresh_graph_list()
        self._info_turns.configure(text=f"对话：{self._turn_count} 轮")
        self._info_graphs.configure(text=f"分形图：{len(self._graph_paths)} 张")

    def _refresh_graph_list(self) -> None:
        for w in self.graph_list.winfo_children():
            w.destroy()
        if not self._graph_paths:
            ctk.CTkLabel(
                self.graph_list, text="暂无分形图", font=ctk.CTkFont(size=12),
                text_color=("gray60", "gray50"),
            ).pack(pady=20)
            return
        for i, p in enumerate(reversed(self._graph_paths[-20:]), 1):
            name = Path(p).stem
            btn = ctk.CTkButton(
                self.graph_list, text=f"{i}. {name}", anchor="w",
                command=lambda pp=p: self._open_html(pp),
                fg_color="transparent", text_color=("gray30", "gray80"),
                font=ctk.CTkFont(size=12), height=32,
                hover_color=("#e8e3d8", "#3a3a3a"),
            )
            btn.pack(fill="x", padx=2, pady=1)

    def _open_latest_graph(self) -> None:
        if self._graph_paths:
            self._open_html(self._graph_paths[-1])

    def _clear_chat(self) -> None:
        self.answer_box.configure(state="normal")
        self.answer_box.delete("1.0", "end")
        self.answer_box.configure(state="disabled")

    def _append_text(self, text: str) -> None:
        self.answer_box.configure(state="normal")
        self.answer_box.insert("end", text)
        self.answer_box.see("end")
        self.answer_box.configure(state="disabled")

    def _open_html(self, path: str) -> None:
        try:
            webbrowser.open(Path(path).resolve().as_uri(), new=2)
        except Exception:  # noqa: BLE001
            pass

    def _update_status(self, text: str) -> None:
        self.status.configure(text=text)
        self._info_model.configure(text=f"模型：{self._model_name}")

    def run(self) -> None:
        self.root.mainloop()


def main(agent_kwargs: dict | None = None, streaming: bool = True,
         rethink_http: bool = True) -> int:
    FractalGui(agent_kwargs, streaming=streaming, rethink_http=rethink_http).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
