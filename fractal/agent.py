"""fractal.agent —— FractalAgent：包装 hermes AIAgent，每轮问答产出一幅推理分形图。

支持分形递归：delegate_task 委派出的子 agent 真实轨迹（由 fractal.recorder
全局记录）会按 goal 匹配并递归挂到父图的 delegate 节点上；顶层委派的子
agent 默认后台异步执行，未完成的节点标记 pending，可用 refresh_last()
在子任务完成后重新构图。

推理网络模式：通过 ephemeral_system_prompt 引导 AI 在每次交互中
展开 5~6 步的推理网络过程，使推理分形图呈现丰富的网络结构。
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path


# ── 推理网络引导 prompt ──────────────────────────────────────────────────
# 注入到 AIAgent 的 ephemeral_system_prompt，引导 AI 每次交互
# 都产出 5~6 步的结构化推理网络，而非直接给出结论。
_REASONING_NETWORK_PROMPT = """\
[推理网络模式 ·严格执行]

你必须在每次回复中展开一个 **5~6 步的推理网络**，而非直接给出结论。
每一步推理必须明确包含以下三个要素：
- **输入**：该步需要什么信息或前置条件
- **操作**：该步做什么（分析/检索/计算/验证/综合）
- **输出**：该步得出什么中间结论

推理网络的约束：
1. 步骤数必须为 5 或 6 步，不得更少。
2. 网络不必须是纯线性的——如果某些步骤互不依赖，应该并行执行（在同一次 tool_calls 中发出）。
3. 每一步的 `reasoning` 字段必须写明该步在网络中的位置和作用，格式：
   「步骤 N/6｜操作：…｜依赖：步骤 X, Y｜产出：…」
4. 即使是最简单的问题，也要拆解为多步推理：
   - 步骤1: 问题解析——识别核心概念与关键约束
   - 步骤2: 知识检索——搜索或回忆相关事实
   - 步骤3: 交叉验证——用不同来源/角度验证关键事实
   - 步骤4: 结构化分析——将信息按维度组织
   - 步骤5: 综合推理——从各维度推导结论
   - 步骤6: 回答构建——组织最终答案并自检
5. 如果涉及工具调用，优先在第2、3步集中并行调用；第4、5步做综合分析。
6. 最终回答（content 字段）放在最后一步，必须在推理网络全部完成后才给出。

示例（问题：「什么是分形？」）：
- 步骤1/6｜操作：问题解析｜依赖：无｜产出：核心概念=自相似性，需一个生活例子
- 步骤2/6｜操作：知识检索｜依赖：步骤1｜产出：自相似性的数学定义与典型分形
- 步骤3/6｜操作：交叉验证｜依赖：步骤2｜产出：科赫雪花/曼德博集合/罗马花椰菜均符合
- 步骤4/6｜操作：类比分析｜依赖：步骤1,3｜产出：罗马花椰菜最适合做生活类比
- 步骤5/6｜操作：综合推理｜依赖：步骤2,3,4｜产出：定义+例子的两段式回答
- 步骤6/6｜操作：回答构建｜依赖：步骤5｜产出：最终答案（先定义后举例）
"""


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


def _find_node(trace: dict, node_id: str) -> dict | None:
    """递归查找节点；支持下钻子图里的 node_id。"""
    for node in trace.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if node.get("id") == node_id:
            return node
        for child in node.get("children") or []:
            found = _find_node(child, node_id)
            if found is not None:
                return found
    return None


class FractalAgent:
    """对 hermes `AIAgent` 的轻包装：多问上下文 + 每轮生成 trace/HTML 图。

    用法::

        fa = FractalAgent()
        result = fa.ask("对比一下 Python 3.13 和 3.12 的性能")
        result["answer"], result["html_path"], result["pending_children"]
    """

    def __init__(self, output_dir: str = "fractal_output",
                 agent_kwargs: dict | None = None, agent=None,
                 streaming: bool = True, stream_callback=None):
        self.output_dir = Path(output_dir)
        self.session_id = "sess_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        self._history: list = []
        self._turn = 0
        self._last_html_path: str | None = None
        self._last_turn: dict | None = None  # refresh_last() 用的上一轮快照
        self.streaming = bool(streaming)
        self.stream_callback = stream_callback
        self._stream_write_every_steps = 3
        self._stream_write_min_interval = 2.0
        if agent is not None:
            self._agent = agent
            prev_step_callback = getattr(self._agent, "step_callback", None)
            self._agent.step_callback = self._stream_step_callback(prev_step_callback)
        else:
            kwargs = {
                "quiet_mode": True,
                "platform": "fractal",
                "ephemeral_system_prompt": _REASONING_NETWORK_PROMPT,
            }
            kwargs.update(agent_kwargs or {})
            prev_step_callback = kwargs.get("step_callback")
            kwargs["step_callback"] = self._stream_step_callback(prev_step_callback)
            # 自动从 config.yaml 解析 model（CLI 通过 --model 传递时优先）
            if not kwargs.get("model"):
                try:
                    from pathlib import Path as _P
                    import yaml as _yaml
                    _cfg = _P.home() / ".hermes" / "config.yaml"
                    if _cfg.is_file():
                        _data = _yaml.safe_load(_cfg.read_text(encoding="utf-8"))
                        _providers = _data.get("providers", {}) if isinstance(_data, dict) else {}
                        for _pv in _providers.values():
                            if isinstance(_pv, dict) and _pv.get("model"):
                                kwargs["provider"] = kwargs.get("provider") or list(_providers.keys())[0]
                                kwargs["model"] = _pv["model"]
                                break
                except Exception:  # noqa: BLE001
                    pass
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
                      since: float, partial: bool = False) -> dict:
        from .trace import build_turn_trace
        from .render import render_trace_html, save_trace

        trace = build_turn_trace(
            question, new_messages, final_response, turn_id, meta,
            child_resolver=self._make_resolver(since),
            partial=partial,
        )
        title = f"{turn_id} · {question[:24]}"
        rethink_url = None
        if not partial:
            try:
                from .rethink_server import PORT
                rethink_url = f"http://localhost:{PORT}/rethink?session={self.session_id}"
            except Exception:  # noqa: BLE001
                rethink_url = None
        html = render_trace_html(trace, title=title, auto_refresh=partial,
                                 rethink_url=rethink_url)
        json_path, html_path = save_trace(
            trace, html, self.output_dir / self.session_id)
        self._last_html_path = html_path
        return {
            "trace": trace,
            "html_path": html_path,
            "json_path": json_path,
            "pending_children": _count_pending(trace),
        }

    def _stream_step_callback(self, prev_step_callback=None):
        """包装 AIAgent.step_callback：节流写出 partial HTML，失败不影响对话。"""
        def _callback(iteration: int, prev_tools: list) -> None:
            if prev_step_callback is not None:
                try:
                    prev_step_callback(iteration, prev_tools)
                except Exception:  # noqa: BLE001
                    pass
            state = getattr(self, "_stream_state", None)
            if not self.streaming or not isinstance(state, dict):
                return
            now = time.time()
            last_iter = int(state.get("last_iteration") or 0)
            last_write = float(state.get("last_write") or 0.0)
            if (iteration - last_iter) < self._stream_write_every_steps and (now - last_write) < self._stream_write_min_interval:
                return
            try:
                messages = list(getattr(self._agent, "_session_messages", []) or [])
                new_messages = messages[state["before"]:]
                meta = {
                    "model": getattr(self._agent, "model", None) or None,
                    "api_calls": iteration,
                    "duration_s": round(now - state["started_at"], 2),
                    "streaming": True,
                }
                rendered = self._render_turn(
                    state["question"], new_messages, "", state["turn_id"], meta,
                    state["started_at"], partial=True,
                )
                state["last_iteration"] = iteration
                state["last_write"] = now
                if not state.get("announced") and self.stream_callback is not None:
                    state["announced"] = True
                    try:
                        self.stream_callback(rendered["html_path"])
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001 —— 流式绘图失败不影响主对话
                pass
        return _callback

    # ------------------------------------------------------------------ 对外
    def ask(self, question: str, trace_meta: dict | None = None) -> dict:
        """问一轮。返回 {"answer", "trace", "html_path", "json_path",
        "pending_children"(, "trace_error")}。"""
        self._turn += 1
        turn_id = f"turn_{self._turn}"
        before = len(self._history)
        t0 = time.time()
        self._stream_state = {
            "question": question,
            "turn_id": turn_id,
            "before": before,
            "started_at": t0,
            "last_iteration": 0,
            "last_write": 0.0,
            "announced": False,
        }
        try:
            result = self._agent.run_conversation(
                question, conversation_history=self._history
            )
        finally:
            self._stream_state = None
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
        meta.update(trace_meta or {})
        # 保存本轮快照供 refresh_last() 使用
        self._last_turn = {
            "question": question,
            "new_messages": new_messages,
            "final_response": final_response,
            "turn_id": turn_id,
            "meta": meta,
            "started_at": t0,
            "history_start": before,
        }
        # 渲染/存图失败绝不允许中断问答主流程
        try:
            rendered = self._render_turn(question, new_messages,
                                         final_response, turn_id, meta, t0)
            out.update(rendered)
            self._last_turn["trace"] = rendered.get("trace")
        except Exception as exc:  # noqa: BLE001 —— 有意兜底
            out["trace_error"] = f"{type(exc).__name__}: {exc}"
        return out

    def rethink(self, node_id: str) -> dict:
        """从上一张图中的某个节点之前截断 history，并要求 Agent 重新思考。"""
        snap = self._last_turn
        trace = (snap or {}).get("trace") if isinstance(snap, dict) else None
        if not isinstance(trace, dict):
            return {"trace_error": "还没有可重思考的推理图，先完成一轮问答。"}
        node = _find_node(trace, node_id)
        if node is None:
            return {"trace_error": f"未找到节点 {node_id}"}
        msg_idx = (node.get("meta") or {}).get("msg_idx")
        if not isinstance(msg_idx, int):
            return {"trace_error": f"节点 {node_id} 没有关联的步骤索引"}
        base = int(snap.get("history_start") or 0)
        cutoff = max(0, base + msg_idx)
        self._history = list(self._history[:cutoff])
        prompt = (
            "请重新思考此步骤，并从这里开始重新推理。\n"
            f"节点：{node_id}｜{node.get('kind')}｜{node.get('label')}\n"
            f"原内容摘要：{node.get('summary') or node.get('content') or ''}"
        )
        return self.ask(prompt, trace_meta={
            "branched_from": node_id,
            "rethink_msg_idx": msg_idx,
        })

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
