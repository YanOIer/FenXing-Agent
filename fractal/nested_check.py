"""fractal.nested_check —— 用桩 AIAgent + 手工播种的 recorder 记录验证分形嵌套构图。

不发任何 API 请求。场景：
- 根 agent 一轮里发出 1 次 delegate_task（2 个 goal：方案甲 / 方案乙）。
- ask 前只播种「方案甲」的子记录 → ask 时方案乙 pending（pending_children=1）。
- ask 后补播「方案乙」（orchestrator，内部再委派一个孙任务）与孙记录，
  refresh_last() 后应挂成 2 个子图、且方案乙子图内含 1 个孙图（depth=2）。

运行::

    python -m fractal.nested_check
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import recorder
from .agent import FractalAgent

GOAL_A = "调研方案甲（单体架构）的可行性"
GOAL_B = "调研方案乙（微服务架构）的可行性"
GOAL_C = "查询方案乙的历史故障数据"


def _tc(call_id: str, name: str, args: dict) -> dict:
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}


class StubAgent:
    """桩 AIAgent：run_conversation 返回带 delegate_task 的合成消息。"""
    model = "stub-nested"

    def run_conversation(self, user_message, conversation_history=None, **kw):
        history = list(conversation_history or [])
        new = [
            {"role": "user", "content": user_message},
            {"role": "assistant",
             "reasoning": "两个方案可以并行委派，先派出去再等结论。",
             "content": "我并行派两个调研子任务。",
             "tool_calls": [_tc("m1", "delegate_task",
                                {"tasks": [{"goal": GOAL_A}, {"goal": GOAL_B}]})]},
            {"role": "tool", "tool_call_id": "m1",
             "content": "delegate_task 已受理 2 个子任务（后台执行）。"},
            {"role": "assistant",
             "content": "已派出两个调研子任务：方案甲（单体）与方案乙（微服务）。"},
        ]
        return {"final_response": new[-1]["content"], "messages": history + new}


def _seed(goal: str, depth: int, role: str, with_grandchild: bool = False) -> None:
    msgs = [
        {"role": "user", "content": goal},
        {"role": "assistant",
         "reasoning": f"子任务「{goal[:12]}…」：先搜资料。",
         "content": "查一下资料。",
         "tool_calls": [_tc("s1", "web_search", {"query": goal[:20]})]},
        {"role": "tool", "tool_call_id": "s1",
         "content": f"关于「{goal}」的搜索结果若干条（略），结论倾向可行。"},
    ]
    if with_grandchild:
        msgs += [
            {"role": "assistant",
             "content": "还需要历史故障数据，派个孙任务去查。",
             "tool_calls": [_tc("s2", "delegate_task", {"goal": GOAL_C})]},
            {"role": "tool", "tool_call_id": "s2",
             "content": "孙任务完成：近一年相关故障 3 起，均为容量规划问题。"},
        ]
    msgs.append({"role": "assistant", "content": f"「{goal}」调研完成：可行，注意成本。"})
    recorder.push_record({
        "user_message": goal, "depth": depth, "role": role,
        "messages": msgs, "final_response": msgs[-1]["content"],
    })


def _root_delegate(trace: dict) -> dict:
    nodes = [n for n in trace["nodes"]
             if n["kind"] == "tool_call" and n["label"] == "delegate_task"]
    assert len(nodes) == 1, f"根图 delegate 节点数={len(nodes)}"
    return nodes[0]


def main() -> int:
    recorder.clear()
    _seed(GOAL_A, depth=1, role="leaf")  # ask 前只有方案甲的记录

    fa = FractalAgent(output_dir="fractal_output/nested_check", agent=StubAgent())
    r = fa.ask("对比方案甲（单体）和方案乙（微服务），哪个适合我们？")

    # ---- 第一轮：方案乙应处于 pending ----
    assert "trace_error" not in r, r.get("trace_error")
    d = _root_delegate(r["trace"])
    assert len(d.get("children") or []) == 1, "ask 时应只挂 1 个子图"
    assert d["meta"].get("pending") is True, "方案乙未播种，应 pending"
    assert r["pending_children"] == 1, r["pending_children"]
    assert Path(r["html_path"]).is_file(), r["html_path"]
    print("✔ 第一轮：1 个子图 + 1 个 pending（pending_children=1）")

    # ---- 补播方案乙（含孙任务）后刷新 ----
    _seed(GOAL_B, depth=1, role="orchestrator", with_grandchild=True)
    _seed(GOAL_C, depth=2, role="leaf")
    ref = fa.refresh_last()
    assert ref and "trace_error" not in ref, ref
    d2 = _root_delegate(ref["trace"])
    kids = d2.get("children") or []
    assert len(kids) == 2, f"refresh 后应有 2 个子图，实际 {len(kids)}"
    assert not d2["meta"].get("pending"), "全部命中后不应再 pending"
    assert ref["pending_children"] == 0, ref["pending_children"]
    kid_b = next(c for c in kids if "方案乙" in c["question"])
    assert kid_b["meta"].get("depth") == 1, kid_b["meta"]
    sub_d = [n for n in kid_b["nodes"]
             if n["kind"] == "tool_call" and n["label"] == "delegate_task"]
    assert len(sub_d) == 1, "方案乙子图内应有 1 个 delegate 节点"
    grands = sub_d[0].get("children") or []
    assert len(grands) == 1, "方案乙子图应含 1 个孙图"
    assert grands[0]["meta"].get("depth") == 2, grands[0]["meta"]
    assert Path(ref["html_path"]).is_file()
    html = Path(ref["html_path"]).read_text(encoding="utf-8")
    assert 'id="breadcrumb"' in html and "viewStack" in html
    print("✔ 刷新后：2 个子图，方案乙含 1 孙图（depth=2），pending=0")
    print(f"✔ HTML 已生成：{ref['html_path']}")
    print("\nnested_check 全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
