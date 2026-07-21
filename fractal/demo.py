"""fractal.demo —— 无需 API key 的合成演示：构造 3 个典型 trace 并渲染。

运行::

    python -m fractal.demo

输出到 fractal_output/demo/turn_1..3.{json,html}。
"""
from __future__ import annotations

import json

from .render import render_trace_html, save_trace
from .trace import build_turn_trace

DEFAULT_DEMO_DIR = "fractal_output/demo"


def _tc(call_id: str, name: str, args: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


def _tool(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


# ---------------------------------------------------------------- turn 1
def _turn1():
    q = "什么是分形？用一句话解释，再给一个生活里的例子。"
    reasoning = (
        "用户在问一个概念性问题，不需要调用任何工具。要点：分形的核心是"
        "「自相似」——局部放大后与整体相似；同时它通常具有分数维度。例子要"
        "选生活化的：西兰花/罗马花椰菜、海岸线、雪花、血管分叉都可以。"
        "回答控制在两句话以内，先定义后举例。"
    )
    answer = (
        "分形是一种「局部放大后仍与整体相似」的自相似结构，无论放大多少倍都能看到相似的纹样。"
        "生活里的例子：罗马花椰菜——掰下一小朵，形状和整颗几乎一样；海岸线、雪花也是如此。"
    )
    msgs = [
        {"role": "user", "content": q},
        {"role": "assistant", "reasoning": reasoning, "content": answer},
    ]
    meta = {"model": "demo-synthetic", "api_calls": 1, "duration_s": 1.8}
    return q, msgs, answer, meta, None


# ---------------------------------------------------------------- turn 2
def _turn2():
    q = "对比 Python 3.13 和 3.12 的性能，顺便查一下官方基准数据"
    r1 = (
        "这是一个事实型对比问题，需要查证。策略：并行发起三个查询——"
        "(1) 英文资料：pyperformance 官方基准里 3.13 vs 3.12 的几何平均；"
        "(2) 中文资料：3.13 的 free-threading(no-GIL) 与实验性 JIT 对性能的"
        "实际影响；(3) 本地笔记 notes/py_bench.md 里之前跑过的数据。"
        "三路互不依赖，应该一次性并行发出，等结果齐后再综合。"
    )
    thought1 = (
        "我打算并行做三件事：搜两路资料（官方基准 + no-GIL/JIT 影响），"
        "同时读一下本地的基准笔记，然后再汇总。"
    )
    ws1 = (
        "搜索结果（web_search · query=\"Python 3.13 vs 3.12 pyperformance geometric mean\"）：\n"
        "1. Python 3.13.0 final 发布说明（docs.python.org/whatsnew/3.13.html）——"
        "官方称 CPython 3.13 在 pyperformance 套件上相对 3.12 几何平均提升约 5%，"
        "其中 specializing adaptive interpreter (PEP 659 的延续) 贡献了主要部分；"
        "实验性 free-threaded 构建 (PEP 703) 默认关闭，单线程性能约回退 5–10%。\n"
        "2. pyperformance 官方跑分页（pyperformance.readthedocs.io）——"
        "3.13.0 vs 3.12.x：geometric_mean ≈ 1.05x；细分：nbody +9%，raytrace +7%，"
        "scimark_fft +12%，regex_dna 持平，json_loads +2%。\n"
        "3. Faster CPython 团队博客——提到 3.13 的 Tier-1 解释器 micro-op 化基本完成，"
        "为 3.14 的 Tier-2 JIT 铺路；实验性 JIT (--enable-experimental-jit) 在部分"
        "基准上有 2–9% 提升，但不稳定。\n"
        "4. 第三方复测（towardsdatascience 博文）——Docker python:3.13 vs 3.12，"
        "fib(35) 递归耗时 3.13 快约 6%；asyncio 场景差异在噪声范围内。\n"
        "（结果 5–8 略去：多为转载与版本号勘误）"
    )
    ws2 = (
        "搜索结果（web_search · query=\"Python 3.13 free-threading JIT 基准 影响\"）：\n"
        "1. 知乎专栏《Python 3.13 性能实测》——free-threaded 构建下多线程 CPU 密集"
        "任务（4 线程矩阵乘）相对 GIL 版提升约 3.2x（接近线性），但单线程回退约 8%；"
        "作者提醒 no-GIL 构建与大量 C 扩展尚不兼容。\n"
        "2. CPython 核心开发者访谈（podcast 文字稿）——PEP 703 的 bias-refcounting "
        "是单线程回退的主要来源；3.14 计划引入 deferred refcounting 把回退压到 <2%。\n"
        "3. Real Python 评测——实验性 JIT 在纯 Python 数值循环上最高 +9%，"
        "在 I/O 密集服务里无感知；建议生产环境继续用默认构建。\n"
        "4. 基准方法论提醒（LWN 评论）——pyperformance 各子项方差大，"
        "应报告几何平均而非算术平均，且要固定 CPU 调频。\n"
        "（结果 5–10 略去）"
    )
    rf1 = (
        "notes/py_bench.md（本地笔记，read_file 返回）：\n"
        "# 本机 pyperformance 复测记录（2024-11，i7-12700H，平衡电源模式）\n"
        "- 环境：python3.12.7 / python3.13.0，均为 python.org 官方安装包\n"
        "- 命令：pyperformance run -b nbody,raytrace,scimark,regex_dna,json_loads\n"
        "- 结果（三次取中位数）：\n"
        "  - nbody:        3.12=412ms  3.13=379ms  (+8.7%)\n"
        "  - raytrace:     3.12=689ms  3.13=641ms  (+7.5%)\n"
        "  - scimark_fft:  3.12=301ms  3.13=268ms  (+12.3%)\n"
        "  - regex_dna:    3.12=176ms  3.13=177ms  (-0.6%，噪声内)\n"
        "  - json_loads:   3.12=28.9us 3.13=28.2us (+2.4%)\n"
        "- 备注：本机几何平均约 +5.9%，与官方公布的 ~5% 一致；"
        "free-threaded 构建单线程 fib(32) 慢 8.4%，与公开数据吻合。"
    )
    r2 = (
        "三路数据已经齐了，且互相印证：官方 ~5%、本机笔记 +5.9%、第三方 +6%。"
        "为了给用户一个确定数字，我想用一个本地小脚本把官方子项与本机子项"
        "合并算一个几何平均，并检查口径（几何平均 vs 算术平均）是否一致。"
        "注意：这里只是汇总已有数字，不需要再搜新资料。"
    )
    thought2 = "资料齐了。跑个本地小脚本把官方与本机的子项数据合并，算几何平均验证口径。"
    t1 = (
        "$ python scripts/bench_summary.py --compare 3.12 3.13\n"
        "merged 10 benchmark rows (official=5, local=5)\n"
        "geometric_mean_speedup: 1.054x  (official 1.050x, local 1.059x)\n"
        "min: regex_dna 0.994x | max: scimark_fft 1.123x\n"
        "note: free-threaded build single-thread penalty ≈ 8% (excluded from mean)\n"
        "exit code: 0"
    )
    answer = (
        "结论：Python 3.13 相对 3.12 在官方 pyperformance 套件上几何平均快约 5%，"
        "本地复测 +5.9%，合并口径 1.054x，数字可信。\n\n"
        "要点：\n"
        "1. 提升主要来自 specializing adaptive 解释器；数值类子项最明显"
        "（scimark_fft +12%，nbody +9%，raytrace +7%），regex_dna 基本持平。\n"
        "2. free-threaded（no-GIL，PEP 703）构建默认关闭：多线程 CPU 密集任务接近线性加速"
        "（4 线程约 3.2x），但单线程回退约 8%，且不少 C 扩展尚未兼容。\n"
        "3. 实验性 JIT 在纯 Python 数值循环上 +2~9%，仍不建议生产开启。\n\n"
        "建议：常规服务直接用默认构建的 3.13 即可获得约 5% 的免费提速；"
        "若吃满多核 CPU 且依赖纯 Python，可评估 free-threaded 构建。"
    )
    msgs = [
        {"role": "user", "content": q},
        {"role": "assistant", "reasoning": r1, "content": thought1,
         "tool_calls": [
             _tc("call_ws1", "web_search",
                 {"query": "Python 3.13 vs 3.12 pyperformance geometric mean"}),
             _tc("call_ws2", "web_search",
                 {"query": "Python 3.13 free-threading JIT 基准 影响"}),
             _tc("call_rf1", "read_file", {"path": "notes/py_bench.md"}),
         ]},
        _tool("call_ws1", ws1),
        _tool("call_ws2", ws2),
        _tool("call_rf1", rf1),
        {"role": "assistant", "reasoning": r2, "content": thought2,
         "tool_calls": [
             _tc("call_t1", "terminal",
                 {"command": "python scripts/bench_summary.py --compare 3.12 3.13"}),
         ]},
        _tool("call_t1", t1),
        {"role": "assistant", "content": answer},
    ]
    meta = {"model": "demo-synthetic", "api_calls": 3, "duration_s": 14.6}
    return q, msgs, answer, meta, None


# ---------------------------------------------------------------- turn 3
def _turn3():
    q = (
        "帮我分析 sales_2024.csv 的销售数据：算一下各季度总额、找出 Top 3 产品，"
        "最后把结论写成 report.md"
    )
    r1 = "多步数据处理任务。先看数据文件长什么样，再决定统计脚本的写法。"
    t1 = "先看一下 data 目录和文件头几行。"
    res1 = (
        "$ ls -lh data/\n"
        "total 2.1M\n"
        "-rw-r--r-- 1 user staff 2.1M Jan  5 10:23 sales_2024.csv\n"
        "$ head -5 data/sales_2024.csv\n"
        "order_id,date,product,category,region,quantity,unit_price\n"
        "A10001,2024-01-03,机械键盘K870,外设,华东,2,399.00\n"
        "A10002,2024-01-03,无线鼠标M2,外设,华南,1,129.00\n"
        "A10003,2024-01-04,显示器U27,显示,华北,1,1899.00\n"
        "A10004,2024-01-05,人体工学椅E1,家具,华东,1,2499.00\n"
        "(共 18,442 行，字段完整，无明显乱码)"
    )
    r2 = (
        "字段清晰：date/product/quantity/unit_price 足够算季度总额与 Top 产品。"
        "写一个 pandas 脚本一次算完：按季度 groupby 求 GMV，按产品 groupby 求销售额取前 3。"
    )
    t2 = "写个统计脚本算季度 GMV 和产品榜。"
    res2 = (
        "$ python scripts/analyze_sales.py --input data/sales_2024.csv\n"
        "Traceback (most recent call last):\n"
        "  File \"scripts/analyze_sales.py\", line 14, in <module>\n"
        "    df[\"date\"] = pd.to_datetime(df[\"date\"], format=\"%Y/%m/%d\")\n"
        "ValueError: time data \"2024-01-03\" doesn't match format \"%Y/%m/%d\", at position 0\n"
        "exit code: 1"
    )
    r3 = "日期格式写错了，实际是 YYYY-MM-DD。改成让 pandas 自动推断即可。"
    t3 = "日期格式修一下，重跑。"
    res3 = (
        "$ python scripts/analyze_sales.py --input data/sales_2024.csv\n"
        "rows: 18442 | total GMV: ¥9,731,204.50\n"
        "Q1: ¥2,105,388.00 | Q2: ¥2,318,772.50 | Q3: ¥2,402,991.00 | Q4: ¥2,904,053.00\n"
        "top_products_by_revenue:\n"
        "  1. 显示器U27      ¥1,386,270.00  (730 件)\n"
        "  2. 人体工学椅E1   ¥1,174,530.00  (470 件)\n"
        "  3. 机械键盘K870   ¥  986,214.00  (2470 件)\n"
        "saved -> data/sales_summary.json\n"
        "exit code: 0"
    )
    r4 = "数字出来了。环比也算一下再写报告：Q4 相比 Q3 增长约 20.9%，全年逐季上行。"
    t4 = "补一个环比，然后生成报告文件。"
    res4 = (
        "$ python scripts/qoq.py data/sales_summary.json\n"
        "QoQ: Q2 +10.1% | Q3 +3.6% | Q4 +20.9%\n"
        "exit code: 0"
    )
    t5 = "把结论写进 report.md。"
    res5 = (
        "write_file: report.md 已写入（1,284 字节）\n"
        "--- report.md 预览 ---\n"
        "# 2024 年度销售分析\n"
        "- 全年 GMV：¥9,731,204.50（18,442 单）\n"
        "- 季度：Q1 ¥210.5万 → Q2 ¥231.9万(+10.1%) → Q3 ¥240.3万(+3.6%) → Q4 ¥290.4万(+20.9%)\n"
        "- Top 3 产品：显示器U27 / 人体工学椅E1 / 机械键盘K870\n"
        "- 结论：全年逐季增长，Q4 大促拉动明显；显示与外设品类贡献 56% GMV。\n"
        "exit code: 0"
    )
    t6 = "最后校验一下报告文件确实落盘了。"
    res6 = (
        "$ ls -lh report.md && wc -l report.md\n"
        "-rw-r--r-- 1 user staff 1.3K Jan  5 10:41 report.md\n"
        "22 report.md\n"
        "exit code: 0"
    )
    answer = (
        "完成了，报告已写入 report.md。核心结论：\n\n"
        "- 全年 GMV ¥973.1 万（18,442 单），四个季度逐季增长：Q1 ¥210.5 万 → Q4 ¥290.4 万；\n"
        "- Q4 环比 +20.9%（大促拉动），Q2 +10.1%，Q3 +3.6%；\n"
        "- Top 3 产品：显示器U27（¥138.6 万）、人体工学椅E1（¥117.5 万）、机械键盘K870（¥98.6 万）。\n\n"
        "过程插曲：第一版统计脚本日期格式写错（%Y/%m/%d vs 实际的 - 分隔），"
        "改为自动推断后顺利通过，最终数据与文件都已校验。"
    )
    msgs = [
        {"role": "user", "content": q},
        {"role": "assistant", "reasoning": r1, "content": t1,
         "tool_calls": [_tc("c1", "terminal",
                            {"command": "ls -lh data/ && head -5 data/sales_2024.csv"})]},
        _tool("c1", res1),
        {"role": "assistant", "reasoning": r2, "content": t2,
         "tool_calls": [_tc("c2", "terminal",
                            {"command": "python scripts/analyze_sales.py --input data/sales_2024.csv"})]},
        _tool("c2", res2),
        {"role": "assistant", "reasoning": r3, "content": t3,
         "tool_calls": [_tc("c3", "terminal",
                            {"command": "python scripts/analyze_sales.py --input data/sales_2024.csv  # fix date format"})]},
        _tool("c3", res3),
        {"role": "assistant", "reasoning": r4, "content": t4,
         "tool_calls": [_tc("c4", "terminal",
                            {"command": "python scripts/qoq.py data/sales_summary.json"})]},
        _tool("c4", res4),
        {"role": "assistant", "content": t5,
         "tool_calls": [_tc("c5", "write_file",
                            {"path": "report.md", "content": "# 2024 年度销售分析\n…(全文略)…"})]},
        _tool("c5", res5),
        {"role": "assistant", "content": t6,
         "tool_calls": [_tc("c6", "terminal",
                            {"command": "ls -lh report.md && wc -l report.md"})]},
        _tool("c6", res6),
        {"role": "assistant", "content": answer},
    ]
    meta = {"model": "demo-synthetic", "api_calls": 7, "duration_s": 41.2}
    return q, msgs, answer, meta, None


# ---------------------------------------------------------------- turn 4（分形嵌套）
_G_FLASK = "调研 Flask 的最新生态与适用场景，给出 3 条要点"
_G_DJANGO = "调研 Django 的最新生态与适用场景，给出 3 条要点"
_G_FASTAPI = "调研 FastAPI 的最新生态与性能基准，给出 3 条要点"
_G_BENCH = "查询并整理 Python Web 框架公开基准数据（requests/sec）"


def _rec(goal, msgs, final, depth, role):
    """合成一条 recorder 风格的子轨迹记录。"""
    return {
        "record_id": "demo-" + str(abs(hash(goal)) % 100000),
        "user_message": goal,
        "started_at": 0.0, "ended_at": 0.0,
        "depth": depth, "role": role,
        "messages": msgs, "final_response": final,
    }


def _turn4():
    q = "调研并对比三个 Python Web 框架（Flask / Django / FastAPI），给出选型建议"

    flask_msgs = [
        {"role": "user", "content": _G_FLASK},
        {"role": "assistant",
         "reasoning": "子任务：调研 Flask。先搜生态近况，再搜适用场景，两路串行即可。",
         "content": "先查 Flask 生态的最新情况。",
         "tool_calls": [_tc("f1", "web_search", {"query": "Flask 3.x 生态 2025 常用扩展"})]},
        _tool("f1", "搜索结果（Flask 3.x 生态）：\n"
              "1. Flask 3.0/3.1 延续轻量内核路线，官方推荐组合：Flask + SQLAlchemy(独立) + "
              "Jinja2 + Click；async 视图自 2.0 起原生支持（asgiref 桥接）。\n"
              "2. 常用扩展：Flask-SQLAlchemy、Flask-Migrate、Flask-Login、Flask-WTF、"
              "Flask-Caching、Celery（任务队列事实标准）。\n"
              "3. 生态趋势：大型新项目更多选 FastAPI/Django，Flask 份额稳定在教学、"
              "原型与中小型内部服务。\n（结果 4-8 略）"),
        {"role": "assistant", "content": "再查适用场景的共识。",
         "tool_calls": [_tc("f2", "web_search", {"query": "Flask 适用场景 微服务 原型 2025"})]},
        _tool("f2", "搜索结果（Flask 适用场景）：\n"
              "共识：Flask 适合原型验证、中小型 REST 服务、需要完全自由技术选型的团队；"
              "不适合开箱即用要求高的企业级场景（无自带 admin/ORM/迁移）。\n"
              "典型用户：教学、内部工具、Serverless 函数封装。"),
        {"role": "assistant",
         "content": "Flask 调研结论：\n1. 轻量内核 + 自由选型，生态成熟但需自行拼装（ORM/校验/迁移都要选）。\n"
                   "2. 适合原型、教学、中小服务；大型项目样板成本高。\n3. 份额被 FastAPI/Django 挤压，但存量巨大、资料最全。"},
    ]
    django_msgs = [
        {"role": "user", "content": _G_DJANGO},
        {"role": "assistant",
         "reasoning": "子任务：调研 Django。重点在 batteries-included 生态与企业级场景。",
         "content": "查 Django 生态。",
         "tool_calls": [_tc("d1", "web_search", {"query": "Django 5.x 生态 2025"})]},
        _tool("d1", "搜索结果（Django 5.x 生态）：\n"
              "1. Django 5.0/5.1：简化表单渲染、异步能力持续增强（async views/ORM 接口逐步完善）。\n"
              "2. 全家桶：ORM + migrations、admin、auth、forms、DRF（Django REST Framework）"
              "是 API 开发事实标准之一；生态包超 4000+（django-packages）。\n"
              "3. 企业采用：内容平台、金融后台、政府系统常见。"),
        {"role": "assistant", "content": "查适用场景。",
         "tool_calls": [_tc("d2", "web_search", {"query": "Django 适用场景 企业级 admin 后台"})]},
        _tool("d2", "搜索结果（Django 适用场景）：\n"
              "共识：需要快速交付完整产品（含后台/权限/ORM）时 Django 最省时；"
              "admin 是核心竞争力。缺点：重、约定大于配置、高并发 IO 场景不如异步框架。"),
        {"role": "assistant",
         "content": "Django 调研结论：\n1. batteries-included：ORM/admin/auth/迁移开箱即用，DRF 成熟。\n"
                   "2. 适合企业级 CRUD、内容平台、快速交付；学习曲线平缓但框架较重。\n3. 异步能力在补强，纯 IO 高并发仍非首选。"},
    ]
    fastapi_msgs = [
        {"role": "user", "content": _G_FASTAPI},
        {"role": "assistant",
         "reasoning": "子任务：调研 FastAPI，重点是生态与性能。性能数字要可靠——先搜生态，"
                      "再把基准数据委派给一个孙任务去查，最后补一个适用场景的搜索。",
         "content": "先查 FastAPI 生态。",
         "tool_calls": [_tc("a1", "web_search", {"query": "FastAPI 生态 2025 pydantic v2"})]},
        _tool("a1", "搜索结果（FastAPI 生态）：\n"
              "1. FastAPI 基于 Starlette(ASGI) + Pydantic v2（Rust 核心 pydantic-core，"
              "校验提速 5-50x）；自动 OpenAPI/Swagger 文档。\n"
              "2. 生态：SQLModel、fastapi-users、Asyncer；是 LLM 服务/推理网关的主流选择"
              "（vLLM、OpenAI 兼容服务多为 FastAPI）。\n3. 类型驱动开发体验被普遍好评。"),
        {"role": "assistant", "content": "性能数字要准确，派个孙任务专门查公开基准。",
         "tool_calls": [_tc("a2", "delegate_task", {"goal": _G_BENCH})]},
        _tool("a2", "子任务已完成。基准结论：FastAPI(Starlette) 公开基准约 3-8x 于 Flask/Django "
                    "同步 worker；同机 uvicorn 单 worker 简单 JSON 路由约 25k-40k req/s。"),
        {"role": "assistant", "content": "最后查适用场景。",
         "tool_calls": [_tc("a3", "web_search", {"query": "FastAPI 适用场景 微服务 IO 密集 LLM"})]},
        _tool("a3", "搜索结果（FastAPI 适用场景）：\n"
              "共识：IO 密集 API、微服务、ML/LLM 推理服务首选；自带数据校验与文档；"
              "缺点：无内置 admin/ORM，复杂业务需自行组合；同步代码混写易阻塞事件循环。"),
        {"role": "assistant",
         "content": "FastAPI 调研结论：\n1. ASGI 异步 + Pydantic v2，性能与 DX 俱佳，公开基准领先 Flask/Django 3-8x。\n"
                   "2. 适合 IO 密集微服务、LLM/ML 推理网关；自动 OpenAPI 文档。\n3. 无全家桶，企业级后台需另配 admin/ORM。"},
    ]
    bench_msgs = [
        {"role": "user", "content": _G_BENCH},
        {"role": "assistant",
         "reasoning": "孙任务：只查基准数字。找 TechEmpower 类公开基准与可复现的单机测试。",
         "content": "查公开基准数据。",
         "tool_calls": [_tc("b1", "web_search",
                            {"query": "TechEmpower benchmark FastAPI Flask Django requests/sec"})]},
        _tool("b1", "搜索结果（公开基准）：\n"
              "1. TechEmpower Framework Benchmarks（多轮平均，JSON 序列化测试）："
              "Starlette/FastAPI 档位约 100k-200k req/s（物理机、多 worker），"
              "Flask(gunicorn sync) 约 20k-40k，Django 约 15k-35k。\n"
              "2. 单机可复现测试（uvicorn/gunicorn 单 worker，本地 hello-json）："
              "FastAPI ≈ 25k-40k req/s；Flask(sync) ≈ 6k-9k；Django ≈ 5k-8k。\n"
              "3. 解读提醒：基准测的是框架开销上限，真实服务瓶颈通常在 DB/序列化/业务逻辑，"
              "差距会收窄到 1.2-2x。"),
        {"role": "assistant",
         "content": "基准整理：公开套件（多 worker）FastAPI 档约 100k-200k req/s，Flask 20k-40k，"
                    "Django 15k-35k；单机单 worker 简单路由 FastAPI 25k-40k vs Flask 6-9k vs Django 5-8k。"
                    "结论：框架层差距 3-8x，真实业务差距通常收窄至 1.2-2x。"},
    ]

    store = {
        _G_FLASK: _rec(_G_FLASK, flask_msgs, flask_msgs[-1]["content"], 1, "leaf"),
        _G_DJANGO: _rec(_G_DJANGO, django_msgs, django_msgs[-1]["content"], 1, "leaf"),
        _G_FASTAPI: _rec(_G_FASTAPI, fastapi_msgs, fastapi_msgs[-1]["content"], 1, "orchestrator"),
        _G_BENCH: _rec(_G_BENCH, bench_msgs, bench_msgs[-1]["content"], 2, "leaf"),
    }

    def resolver(goal: str):
        return store.get(goal)

    r_main = (
        "这是典型的可并行调研任务：三个框架互不依赖，应该用一次 delegate_task "
        "批量孵化三个子 agent 并行调研，我只需等三份结论汇总后做对比与选型建议。"
    )
    thought = "三份调研可以并行，我用一次 delegate_task 派三个子任务。"
    delegate_result = (
        "delegate_task 已完成 3 个子任务：\n"
        "[1] Flask：轻量自由、原型/中小服务首选，生态成熟需自行拼装。\n"
        "[2] Django：全家桶开箱即用，企业级 CRUD 与后台最省时。\n"
        "[3] FastAPI：异步高性能（基准领先 3-8x），LLM/微服务首选，无全家桶。\n"
        "（其中 FastAPI 子任务内部又委派了一个基准查询孙任务，数据已并入结论）"
    )
    r_sum = (
        "三份结论齐了，且 FastAPI 子任务还自动下钻查了基准数据。现在按维度对比："
        "开发效率（Django>FastAPI>Flask 视团队而定）、运行时性能（FastAPI>>Flask≈Django）、"
        "生态开箱度（Django>Flask>FastAPI）、适用场景各不相同。给出选型矩阵即可。"
    )
    answer = (
        "三框架对比（调研自 3 个并行子任务，基准数字来自孙任务）：\n\n"
        "| 维度 | Flask | Django | FastAPI |\n"
        "|---|---|---|---|\n"
        "| 定位 | 轻量内核、自由拼装 | 全家桶、batteries-included | 异步高性能、类型驱动 |\n"
        "| 框架层基准 | 6-9k req/s（单机单 worker） | 5-8k req/s | 25-40k req/s |\n"
        "| 开箱功能 | 需自选 ORM/校验/迁移 | ORM/admin/auth/迁移全带 | 自带校验+OpenAPI，无 admin/ORM |\n"
        "| 典型场景 | 原型、教学、中小服务 | 企业级 CRUD、内容平台 | IO 密集微服务、LLM 推理网关 |\n\n"
        "选型建议：要快出完整产品选 Django；做高性能 API / LLM 服务选 FastAPI；"
        "做原型或想要完全自由的选型选 Flask。"
    )
    msgs = [
        {"role": "user", "content": q},
        {"role": "assistant", "reasoning": r_main, "content": thought,
         "tool_calls": [_tc("m1", "delegate_task", {
             "tasks": [
                 {"goal": _G_FLASK, "role": "researcher"},
                 {"goal": _G_DJANGO, "role": "researcher"},
                 {"goal": _G_FASTAPI, "role": "researcher"},
             ]})]},
        _tool("m1", delegate_result),
        {"role": "assistant", "reasoning": r_sum, "content": answer},
    ]
    meta = {"model": "demo-synthetic", "api_calls": 3, "duration_s": 68.4}
    return q, msgs, answer, meta, resolver


# ---------------------------------------------------------------- turn 5（pending 态）
def _turn5():
    q = "帮我把 20 个竞品官网的定价页抓下来汇总成表（后台慢慢跑），先告诉我你打算怎么做"
    goal = "抓取 20 个竞品官网的定价页并汇总成对比表"
    r1 = ("用户明确说「后台慢慢跑」——这是一个长耗时抓取任务，应该 delegate_task "
          "提交后立刻返回计划，不阻塞本轮回答。本轮结束时子任务大概率还在跑。")
    thought = "这个任务耗时长，我提交到后台执行，先给你执行计划。"
    delegate_result = ("delegate_task 已受理（task_id=task_8f31a2）：目标「" + goal +
                       "」。任务已提交后台执行，完成后将推送结果。")
    answer = (
        "计划如下：\n"
        "1. 从竞品清单读出 20 个官网 URL，逐个抓取 /pricing 页面（限速并发 3，带重试）；\n"
        "2. 用 read_file/解析规则抽取套餐名、价格、计费周期、核心限制；\n"
        "3. 汇总成 Markdown 对比表并写入 competitors_pricing.md。\n\n"
        "任务已提交后台运行（⏳），完成后我会把汇总表给你。"
    )
    msgs = [
        {"role": "user", "content": q},
        {"role": "assistant", "reasoning": r1, "content": thought,
         "tool_calls": [_tc("p1", "delegate_task", {"goal": goal, "context": "竞品清单见 notes/competitors.md"})]},
        _tool("p1", delegate_result),
        {"role": "assistant", "content": answer},
    ]
    meta = {"model": "demo-synthetic", "api_calls": 2, "duration_s": 6.1}
    # resolver 永远查不到记录 → delegate 节点 pending
    return q, msgs, answer, meta, lambda goal: None


def run_demo(out_dir: str = DEFAULT_DEMO_DIR) -> list[tuple[str, str]]:
    """生成 5 个演示 trace 并渲染。返回 [(json_path, html_path), ...]。"""
    builders = [_turn1, _turn2, _turn3, _turn4, _turn5]
    paths: list[tuple[str, str]] = []
    for i, build in enumerate(builders, start=1):
        q, msgs, answer, meta, resolver = build()
        trace = build_turn_trace(q, msgs, answer, f"turn_{i}", meta,
                                 child_resolver=resolver)
        html = render_trace_html(trace, title=f"演示 {i} · {q[:20]}")
        json_path, html_path = save_trace(trace, html, out_dir)
        paths.append((json_path, html_path))
        print(f"[OK] turn_{i}: {html_path}")
        print(f"           {json_path}")
    print(f"\n[GENERATED] {len(paths)} demo graphs in: {out_dir}")
    return paths


def main() -> None:
    run_demo()


if __name__ == "__main__":
    main()
