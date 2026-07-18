"""fractal.trace —— 把一轮对话的增量消息流转换为「问题 → 答案」的有向无环图模型。

图模型契约（与渲染端约定）::

    {
      "id": "turn_1",
      "question": "...",
      "answer": "...",
      "created_at": "ISO时间",
      "meta": {"model": "...", "api_calls": 3, "duration_s": 12.3},
      "nodes": [{"id", "kind", "label", "summary", "content", "meta", "expandable"}],
      "edges": [{"source", "target", "kind": "flow|branch|merge"}]
    }

保证：question 节点唯一且入度为 0；answer 节点唯一且出度为 0；图弱连通。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# 工具结果错误嗅探的启发式关键词（小写匹配）
_ERROR_HINTS = (
    "traceback (most recent call last)",
    "command failed",
    "permission denied",
    "no such file",
    "timed out",
    "timeout",
    "exception",
    "error:",
    "failed:",
    "not found",
)

_SUMMARY_LIMIT = 120

# 分形递归的最大深度兜底（delegate_task 子图里再有 delegate_task 时逐层下钻）
_MAX_FRACTAL_DEPTH = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _content_to_text(content: Any) -> str:
    """容错地把 OpenAI 消息 content（str / list[dict] / 其他）拼成纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(p for p in parts if p)
    return str(content)


def _summarize(text: str, limit: int = _SUMMARY_LIMIT) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip() + "…"


def _looks_error(text: str) -> bool:
    low = (text or "").lower()
    return any(hint in low for hint in _ERROR_HINTS)


def _parse_arguments(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {"_raw": raw}
    return {}


def _format_call(name: str, args: Any) -> str:
    try:
        rendered = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = str(args)
    return f"{name}({rendered})"


def _extract_delegate_goals(args: Any) -> list[str]:
    """从 delegate_task 的 arguments 里取出所有子任务 goal（单个 goal 或 tasks[].goal）。"""
    goals: list[str] = []
    if isinstance(args, dict):
        g = args.get("goal")
        if isinstance(g, str) and g.strip():
            goals.append(" ".join(g.split()))
        tasks = args.get("tasks")
        if isinstance(tasks, list):
            for t in tasks:
                if isinstance(t, dict):
                    tg = t.get("goal")
                    if isinstance(tg, str) and tg.strip():
                        goals.append(" ".join(tg.split()))
    seen: set[str] = set()
    out: list[str] = []
    for g in goals:
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out


def build_turn_trace(
    question: str,
    new_messages: list,
    final_response: str,
    turn_id: str,
    meta: dict | None = None,
    child_resolver: Any = None,
    _depth: int = 0,
) -> dict:
    """把一轮交互的新增消息段构建成图 JSON dict。

    参数:
        question: 用户本轮问题（图的唯一源点）。
        new_messages: 本轮新增的 OpenAI 格式消息（assistant/tool 会被消费，其余角色忽略）。
        final_response: 本轮最终回答（图的唯一汇点）。
        turn_id: 轮次 id，如 "turn_1"。
        meta: 可选的运行元信息（model / api_calls / duration_s 等）。
        child_resolver: 可选回调 ``f(goal) -> record|None``；遇到 delegate_task
            工具调用时按 goal 查询子 agent 轨迹，命中则递归生成子图挂到
            节点的 ``children``，未命中则标记 ``meta.pending = True``。
        _depth: 内部递归深度（外部调用勿传），超过 _MAX_FRACTAL_DEPTH 停止下钻。
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    def add_node(
        kind: str,
        label: str,
        content: str,
        summary: str | None = None,
        node_meta: dict | None = None,
        expandable: bool = False,
    ) -> str:
        node_id = f"n{len(nodes)}"
        nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "label": label,
                "summary": _summarize(content) if summary is None else summary,
                "content": content or "",
                "meta": node_meta or {},
                "expandable": bool(expandable),
            }
        )
        return node_id

    def connect(tails: list[str], target: str) -> None:
        """把当前主流水尾部接到 target：单尾 flow，多尾 merge。"""
        kind = "flow" if len(tails) <= 1 else "merge"
        for tail in tails:
            edges.append({"source": tail, "target": target, "kind": kind})

    question = question or ""
    final_response = final_response or ""
    messages = [m for m in (new_messages or []) if isinstance(m, dict)]

    qid = add_node("question", "问题", question)
    tails: list[str] = [qid]
    pending: dict[str, tuple[str, str]] = {}  # tool_call_id -> (node_id, tool_name)

    last_assistant_idx = max(
        (i for i, m in enumerate(messages) if m.get("role") == "assistant"),
        default=-1,
    )

    for idx, msg in enumerate(messages):
        role = msg.get("role")

        if role == "assistant":
            reasoning = msg.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                rid = add_node(
                    "reasoning",
                    "推理",
                    reasoning,
                    node_meta={"chars": len(reasoning)},
                )
                connect(tails, rid)
                tails = [rid]

            text = _content_to_text(msg.get("content"))
            tool_calls = msg.get("tool_calls") or []
            is_last_assistant = idx == last_assistant_idx
            # 非空 content 且不是最终回答 → 中间想法（thought）节点
            if text.strip() and (tool_calls or not is_last_assistant):
                tid = add_node("thought", "想法", text, node_meta={"chars": len(text)})
                connect(tails, tid)
                tails = [tid]

            if tool_calls:
                is_branch = len(tool_calls) > 1
                new_tails: list[str] = []
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    fn = tc.get("function") or {}
                    name = fn.get("name") or "tool"
                    args = _parse_arguments(fn.get("arguments"))
                    cid = add_node(
                        "tool_call",
                        name,
                        _format_call(name, args),
                        summary=f"{name}(…)  { _summarize(json.dumps(args, ensure_ascii=False, default=str), 80) }",
                        node_meta={"arguments": args, "tool_call_id": tc.get("id")},
                        expandable=True,  # 分形预留：未来可展开为子 agent 的子图
                    )
                    node_obj = nodes[-1]
                    # ---- 分形递归：delegate_task → 挂载子 agent 的真实轨迹子图 ----
                    if (name == "delegate_task"
                            and child_resolver is not None
                            and _depth < _MAX_FRACTAL_DEPTH):
                        goals = _extract_delegate_goals(args)
                        child_traces: list[dict] = []
                        unmatched = 0
                        for gi, goal in enumerate(goals):
                            rec = None
                            try:
                                rec = child_resolver(goal)
                            except Exception:  # noqa: BLE001 —— resolver 故障不毁主图
                                rec = None
                            if isinstance(rec, list):
                                rec = rec[0] if rec else None
                            if not isinstance(rec, dict):
                                unmatched += 1
                                continue
                            child_meta = {
                                "depth": rec.get("depth", _depth + 1),
                                "role": rec.get("role"),
                                "record_id": rec.get("record_id"),
                                "duration_s": (
                                    round(rec["ended_at"] - rec["started_at"], 2)
                                    if isinstance(rec.get("started_at"), (int, float))
                                    and isinstance(rec.get("ended_at"), (int, float))
                                    else None
                                ),
                            }
                            child_traces.append(build_turn_trace(
                                goal,
                                rec.get("messages") or [],
                                rec.get("final_response") or "",
                                f"{turn_id}.c{gi + 1}",
                                child_meta,
                                child_resolver=child_resolver,
                                _depth=_depth + 1,
                            ))
                        if child_traces:
                            node_obj["children"] = child_traces
                        if unmatched:
                            node_obj["meta"]["pending"] = True
                    for tail in tails:
                        kind = "branch" if is_branch else ("merge" if len(tails) > 1 else "flow")
                        edges.append({"source": tail, "target": cid, "kind": kind})
                    if tc.get("id"):
                        pending[tc["id"]] = (cid, name)
                    new_tails.append(cid)
                if new_tails:
                    tails = new_tails

        elif role == "tool":
            content = _content_to_text(msg.get("content"))
            call_id = msg.get("tool_call_id")
            source = None
            name = "tool"
            if call_id and call_id in pending:
                source, name = pending.pop(call_id)
            rid = add_node(
                "tool_result",
                f"{name} 结果",
                content,
                node_meta={
                    "status": "error" if _looks_error(content) else "ok",
                    "tool_call_id": call_id,
                    "chars": len(content),
                },
            )
            if source is not None:
                edges.append({"source": source, "target": rid, "kind": "flow"})
                tails = [rid if t == source else t for t in tails]
            else:
                connect(tails, rid)
                tails = [rid]

    aid = add_node("answer", "答案", final_response)
    connect(tails, aid)

    return {
        "id": str(turn_id),
        "question": question,
        "answer": final_response,
        "created_at": _now_iso(),
        "meta": dict(meta or {}),
        "nodes": nodes,
        "edges": edges,
    }
