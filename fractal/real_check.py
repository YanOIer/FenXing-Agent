"""真实环境端到端验证：FractalAgent + 真实 AIAgent（Kimi 网关）+ delegate_task 子轨迹捕获。

用法: .venv/Scripts/python.exe -m fractal.real_check
需要环境变量 KIMI_API_KEY / KIMI_BASE_URL（或 ~/.hermes/.env）。
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    if not os.environ.get("KIMI_API_KEY"):
        print("❌ 缺少 KIMI_API_KEY"); return 2
    # 桌面环境的网关缺 /v1 段会导致 404，且必须显式指定模型
    os.environ["KIMI_BASE_URL"] = "https://agent-gw.kimi.com/coding/v1"

    from fractal.agent import FractalAgent
    from fractal import recorder

    q = ("请使用 delegate_task 工具派两个子 agent（tasks 数组，两个 goal）："
         "一个用一句话介绍 Flask，一个用一句话介绍 Django。"
         "子任务结果回来后，用一句话对比总结两者。")

    agent = FractalAgent(
        output_dir="fractal_output",
        agent_kwargs={
            "quiet_mode": True,
            "platform": "fractal",
            "model": "kimi-for-coding",
            "enabled_toolsets": ["delegation"],
            "max_iterations": 12,
        },
    )
    print("recorder installed:", recorder.install_recorder())

    t0 = time.time()
    r = agent.ask(q)
    dt = time.time() - t0

    print("=== 答案 ===")
    print((r.get("answer") or "")[:600])
    print(f"\nask 耗时 {dt:.1f}s | pending_children={r.get('pending_children')} | trace_error={r.get('trace_error')}")
    print("html:", r.get("html_path"))

    # 顶层委派是后台异步：轮询等待子记录，然后 refresh 让子图挂上
    deadline = time.time() + 150
    done = []
    while time.time() < deadline:
        snaps = recorder.snapshot()
        child_recs = [s for s in snaps if s.get("depth", 0) >= 1]
        done = [s for s in child_recs if s.get("ended_at")]
        if len(done) >= 2:
            break
        time.sleep(3)
    print(f"recorder 记录: 共 {len(recorder.snapshot())} 条, 子 agent 已完成 {len(done)} 条")

    r2 = agent.refresh_last()
    if not r2:
        print("❌ refresh_last 返回 None"); return 1
    trace = json.loads(Path(r2["json_path"]).read_text(encoding="utf-8"))

    n_children = sum(len(n.get("children") or []) for n in trace["nodes"])
    n_pending = sum(1 for n in trace["nodes"] if n.get("meta", {}).get("pending"))
    print(f"refresh 后: 挂载子图 {n_children} | pending {n_pending}")
    print("刷新后 html:", r2["html_path"])

    ok = n_children >= 1
    print("✅ 端到端通过" if ok else "❌ 未捕获到子图")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
