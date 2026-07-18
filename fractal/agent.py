"""fractal.agent —— FractalAgent：包装 hermes AIAgent，每轮问答产出一幅推理分形图。

支持分形递归：delegate_task 委派出的子 agent 真实轨迹（由 fractal.recorder
全局记录）会按 goal 匹配并递归挂到父图的 delegate 节点上；顶层委派的子
agent 默认后台异步执行，未完成的节点标记 pending，可用 refresh_last()
在子任务完成后重新构图。
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path


def _count_pending(trace: dict) -> int:
    """递归统计图中仍 pending 的 delegate 节点数。"""
    n = 0
    for node in trace.get("nodes", []):
        if isinstance(node, dict):
            if node.get("meta", {}).get("pending"):
                n += 1
            for child in node.get("children") or []:
                n += _count_pending(child)
    return n


class FractalAgent:
    """对 hermes `AIAgent` 的轻包装：多问上下文 + 每轮生成 trace/HTML 图。

    用法::

        fa = FractalAgent()
        result = fa.ask("对比一下 Python 3.13 和 3.12 的性能")
        result["answer"], result["html_path"], result["pending_children"]
    """

    def __init__(self, output_dir: str = "fractal_output",
                 agent_kwargs: dict | None = None, agent=None):
        self.output_dir = Path(output_dir)
        self.session_id = "sess_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        self._history: list = []
        self._turn = 0
        self._last_html_path: str | None = None
        self._last_turn: dict | None = None  # refresh_last() 用的上一轮快照
        if agent is not None:
            self._agent = agent
        else:
            kwargs = {"quiet_mode": True, "platform": "fractal"}
            kwargs.update(agent_kwargs or {})
            # 延迟导入：避免 --demo / --help 等场景加载整个 hermes 依赖链
            from run_agent import AIAgent
            self._agent = AIAgent(**kwargs)
        # 安装全局子轨迹记录器（幂等、fail-open）
        try:
            from .recorder import install_recorder
            install_recorder()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ 内部
    def _make_resolver(self, since: float):
        """返回 child_resolver(goal) -> 最新匹配记录 | None。"""
        def _resolve(goal: str):
            try:
                from .recorder import find_children
                recs = find_children(goal, since=since)
                return recs[0] if recs else None
            except Exception:  # noqa: BLE001
                return None
        return _resolve

    def _render_turn(self, question: str, new_messages: list,
                     final_response: str, turn_id: str, meta: dict,
                     since: float) -> dict:
        from .trace import build_turn_trace
        from .render import render_trace_html, save_trace

        trace = build_turn_trace(
            question, new_messages, final_response, turn_id, meta,
            child_resolver=self._make_resolver(since),
        )
        title = f"{turn_id} · {question[:24]}"
        html = render_trace_html(trace, title=title)
        json_path, html_path = save_trace(
            trace, html, self.output_dir / self.session_id)
        self._last_html_path = html_path
        return {
            "trace": trace,
            "html_path": html_path,
            "json_path": json_path,
            "pending_children": _count_pending(trace),
        }

    # ------------------------------------------------------------------ 对外
    def ask(self, question: str) -> dict:
        """问一轮。返回 {"answer", "trace", "html_path", "json_path",
        "pending_children"(, "trace_error")}。"""
        self._turn += 1
        turn_id = f"turn_{self._turn}"
        before = len(self._history)
        t0 = time.time()
        result = self._agent.run_conversation(
            question, conversation_history=self._history
        )
        duration = time.time() - t0
        messages = result.get("messages") or []
        final_response = result.get("final_response") or ""
        new_messages = messages[before:]
        self._history = messages

        out = {
            "answer": final_response,
            "trace": None,
            "html_path": None,
            "json_path": None,
            "pending_children": 0,
        }
        meta = {
            "model": getattr(self._agent, "model", None) or None,
            "api_calls": sum(1 for m in new_messages
                             if isinstance(m, dict) and m.get("role") == "assistant"),
            "duration_s": round(duration, 2),
        }
        # 保存本轮快照供 refresh_last() 使用
        self._last_turn = {
            "question": question,
            "new_messages": new_messages,
            "final_response": final_response,
            "turn_id": turn_id,
            "meta": meta,
            "started_at": t0,
        }
        # 渲染/存图失败绝不允许中断问答主流程
        try:
            out.update(self._render_turn(question, new_messages,
                                         final_response, turn_id, meta, t0))
        except Exception as exc:  # noqa: BLE001 —— 有意兜底
            out["trace_error"] = f"{type(exc).__name__}: {exc}"
        return out

    def refresh_last(self) -> dict | None:
        """用上一轮保存的快照重新构图渲染（后台子任务可能已完成）。

        不改变对话 history；没有上一轮时返回 None。
        """
        snap = self._last_turn
        if snap is None:
            return None
        try:
            return self._render_turn(
                snap["question"], snap["new_messages"], snap["final_response"],
                snap["turn_id"], snap["meta"], snap["started_at"],
            )
        except Exception as exc:  # noqa: BLE001
            return {"trace_error": f"{type(exc).__name__}: {exc}"}

    def last_trace_path(self) -> str | None:
        return self._last_html_path
