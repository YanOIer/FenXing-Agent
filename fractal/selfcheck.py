"""fractal.selfcheck —— 离线自检：重新生成演示并对图结构与 HTML 做断言。

运行::

    python -m fractal.selfcheck

退出码 0 = 全部通过；1 = 存在失败项。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .demo import DEFAULT_DEMO_DIR, run_demo

_EXTERNAL_REF_RE = re.compile(r"""(?:src|href)\s*=\s*["']https?://""", re.IGNORECASE)
_TRACE_LINE_RE = re.compile(r"^const TRACE = (.*);$", re.MULTILINE)


def check_graph(trace: dict, name: str, failures: list[str]) -> None:
    """通用图结构断言：question/answer 唯一、度数、边引用、双向可达。"""
    nodes = trace["nodes"]
    edges = trace["edges"]
    ids = [n["id"] for n in nodes]
    id_set = set(ids)

    questions = [n for n in nodes if n["kind"] == "question"]
    answers = [n for n in nodes if n["kind"] == "answer"]
    if len(questions) != 1:
        failures.append(f"{name}: question 节点数量={len(questions)}，应为 1")
    if len(answers) != 1:
        failures.append(f"{name}: answer 节点数量={len(answers)}，应为 1")

    for e in edges:
        if e["source"] not in id_set or e["target"] not in id_set:
            failures.append(f"{name}: 边引用了不存在的节点: {e}")

    indeg = {i: 0 for i in ids}
    outdeg = {i: 0 for i in ids}
    adj = {i: [] for i in ids}
    rev = {i: [] for i in ids}
    for e in edges:
        if e["source"] in id_set and e["target"] in id_set:
            indeg[e["target"]] += 1
            outdeg[e["source"]] += 1
            adj[e["source"]].append(e["target"])
            rev[e["target"]].append(e["source"])

    if questions and indeg[questions[0]["id"]] != 0:
        failures.append(f"{name}: question 入度={indeg[questions[0]['id']]}，应为 0")
    if answers and outdeg[answers[0]["id"]] != 0:
        failures.append(f"{name}: answer 出度={outdeg[answers[0]['id']]}，应为 0")

    if questions:
        seen = set()
        stack = [questions[0]["id"]]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adj[cur])
        unreachable = id_set - seen
        if unreachable:
            failures.append(f"{name}: 从 question 不可达的节点: {sorted(unreachable)}")

    if answers:
        seen = set()
        stack = [answers[0]["id"]]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(rev[cur])
        cant_reach = id_set - seen
        if cant_reach:
            failures.append(f"{name}: 无法到达 answer 的节点: {sorted(cant_reach)}")


def _delegate_nodes(trace: dict) -> list[dict]:
    return [n for n in trace["nodes"]
            if n["kind"] == "tool_call" and n["label"] == "delegate_task"]


def check_nested(trace: dict, failures: list[str]) -> None:
    """turn_4 的分形嵌套结构断言。"""
    name = "turn_4"
    roots = _delegate_nodes(trace)
    if len(roots) != 1:
        failures.append(f"{name}: 根图 delegate_task 节点数={len(roots)}，应为 1")
        return
    root = roots[0]
    children = root.get("children") or []
    if len(children) != 3:
        failures.append(f"{name}: delegate 节点 children={len(children)}，应为 3")
        return
    if root.get("meta", {}).get("pending"):
        failures.append(f"{name}: 三个子任务都已命中，不应标记 pending")

    for i, child in enumerate(children):
        check_graph(child, f"{name}.child{i + 1}", failures)
        if child.get("meta", {}).get("depth") != 1:
            failures.append(f"{name}.child{i + 1}: meta.depth="
                            f"{child.get('meta', {}).get('depth')}，应为 1")

    fastapi = next((c for c in children if "FastAPI" in c.get("question", "")), None)
    if fastapi is None:
        failures.append(f"{name}: 未找到 FastAPI 子图")
        return
    grands = _delegate_nodes(fastapi)
    if len(grands) != 1:
        failures.append(f"{name}: FastAPI 子图内 delegate_task 节点数={len(grands)}，应为 1")
        return
    grand_children = grands[0].get("children") or []
    if len(grand_children) != 1:
        failures.append(f"{name}: FastAPI 子图的孙图数量={len(grand_children)}，应为 1")
        return
    check_graph(grand_children[0], f"{name}.grandchild", failures)
    if grand_children[0].get("meta", {}).get("depth") != 2:
        failures.append(f"{name}.grandchild: meta.depth="
                        f"{grand_children[0].get('meta', {}).get('depth')}，应为 2")


def check_pending(trace: dict, failures: list[str]) -> None:
    """turn_5 的 pending 态断言。"""
    name = "turn_5"
    roots = _delegate_nodes(trace)
    if len(roots) != 1:
        failures.append(f"{name}: delegate_task 节点数={len(roots)}，应为 1")
        return
    node = roots[0]
    if not node.get("meta", {}).get("pending"):
        failures.append(f"{name}: delegate 节点 meta.pending 应为 True")
    if node.get("children"):
        failures.append(f"{name}: pending 节点不应有 children")


def extract_trace_from_html(html_text: str, name: str, failures: list[str]):
    """从 HTML 中抽取 const TRACE 并解析（JSON 单行内嵌，`</` 已转义）。"""
    m = _TRACE_LINE_RE.search(html_text)
    if not m:
        failures.append(f"{name}: HTML 中未找到 const TRACE 行")
        return None
    try:
        return json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError as exc:
        failures.append(f"{name}: HTML 内嵌 TRACE 解析失败: {exc}")
        return None


def check_html(html_path: Path, name: str, failures: list[str]) -> str:
    text = html_path.read_text(encoding="utf-8")
    low = text.lower()
    if "const TRACE" not in text:
        failures.append(f"{name}: HTML 缺少 `const TRACE`")
    for pat, desc in (("<script src", "<script src>"),
                      ("<link", "<link>"),
                      ("@import", "@import")):
        if pat in low:
            failures.append(f"{name}: HTML 含外部引用 {desc}")
    if _EXTERNAL_REF_RE.search(text):
        failures.append(f"{name}: HTML 含 src/href 指向 http(s) 的外部资源")
    return text


def main() -> int:
    print("== 重新生成演示 ==")
    paths = run_demo()

    failures: list[str] = []
    traces: dict[str, dict] = {}
    html_texts: dict[str, str] = {}
    for json_path, html_path in paths:
        name = Path(json_path).stem
        trace = json.loads(Path(json_path).read_text(encoding="utf-8"))
        traces[name] = trace
        check_graph(trace, name, failures)
        html_texts[name] = check_html(Path(html_path), name, failures)

    # turn_2 的并行分支结构：3 条 branch + 3 条 merge
    t2 = traces.get("turn_2")
    if t2:
        n_branch = sum(1 for e in t2["edges"] if e["kind"] == "branch")
        n_merge = sum(1 for e in t2["edges"] if e["kind"] == "merge")
        if n_branch != 3:
            failures.append(f"turn_2: branch 边={n_branch}，应为 3")
        if n_merge != 3:
            failures.append(f"turn_2: merge 边={n_merge}，应为 3")

    # turn_4 分形嵌套 / turn_5 pending
    if "turn_4" in traces:
        check_nested(traces["turn_4"], failures)
    if "turn_5" in traces:
        check_pending(traces["turn_5"], failures)

    # turn_4 HTML：内嵌递归数据可解析 + 面包屑/视图栈标识存在
    t4_html = html_texts.get("turn_4")
    if t4_html:
        embedded = extract_trace_from_html(t4_html, "turn_4.html", failures)
        if embedded:
            roots = _delegate_nodes(embedded)
            if not roots or len(roots[0].get("children") or []) != 3:
                failures.append("turn_4.html: 内嵌 TRACE 的 delegate 节点应有 3 个 children")
        for marker in ('id="breadcrumb"', "viewStack", "drillInto"):
            if marker not in t4_html:
                failures.append(f"turn_4.html: 缺少钻取交互标识 {marker}")

    print("\n== 自检结果 ==")
    if failures:
        for f in failures:
            print(f"❌ {f}")
        print(f"\n共 {len(failures)} 项失败")
        return 1
    print("✅ 图结构断言全部通过（question/answer 唯一性、度数、边引用、双向可达性）")
    print("✅ turn_2 含 3 条 branch 边和 3 条 merge 边")
    print("✅ turn_4 嵌套正确：根 delegate ×3 子图（depth=1），FastAPI 子图含 1 孙图（depth=2）")
    print("✅ turn_5 delegate 节点 pending=True 且无 children")
    print("✅ HTML 含 const TRACE（递归 children 可解析）与面包屑标识，无外部引用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
