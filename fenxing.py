#!/usr/bin/env python3
"""分形Agent · FractalAgent —— 命令行入口。

    python fenxing.py [--model X] [--toolsets web,terminal] [--demo] [--no-open]

每轮问答除打印答案外，还会把「从问题到答案的推理过程」渲染成一张可交互的
二维分形图（HTML），输出到 fractal_output/<session_id>/turn_<N>.html，
并自动用浏览器打开该图（可用 --no-open 关闭）。
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

BANNER = r"""
  ╔══════════════════════════════════════════════╗
  ║        分形Agent · FractalAgent              ║
  ║   每次问答，生成一张可交互的推理分形图       ║
  ╚══════════════════════════════════════════════╝
"""

HELP_TEXT = """\
斜杠命令：
  /graph   刷新并打印最新推理图的 HTML 路径（后台子任务完成后用它把子图挂上）
  /demo    运行无需 API key 的合成演示（输出到 fractal_output/demo/）
  /help    显示本帮助
  /quit    退出
直接输入其他内容即向 Agent 提问。每张图保存为 fractal_output/<session>/turn_<N>.html，
问答后默认自动用浏览器打开（可用 --no-open 关闭），图中可缩放、拖拽、点击节点
查看完整推理内容。\
"""

_KNOWN_KEY_VARS = (
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
    "MISTRAL_API_KEY", "TOGETHER_API_KEY", "XAI_API_KEY",
)


def _credentials_available() -> bool:
    """粗略探测：环境变量或 ~/.hermes/.env 里是否可能有 API key。"""
    if any(os.environ.get(k) for k in _KNOWN_KEY_VARS):
        return True
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.is_file():
        try:
            for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    if key.strip().endswith(("API_KEY", "TOKEN")) and value.strip().strip("\"'"):
                        return True
        except OSError:
            pass
    return False


def _print_credential_hint() -> None:
    print("! 未检测到可用的 API key，无法启动问答模式。\n")
    print("请任选其一配置后再试：")
    print("  1. 在 ~/.hermes/.env 中写入一行，例如：")
    print("       OPENROUTER_API_KEY=sk-or-...")
    print("  2. 或直接设置环境变量（如 OPENAI_API_KEY / DEEPSEEK_API_KEY 等）；")
    print("  3. 模型与服务商的详细配置见 ~/.hermes/config.yaml。\n")
    print("提示：没有 key 也可以先看效果 -- 运行  python fenxing.py --demo")


def _open_html(path: str | None) -> None:
    """用系统默认浏览器打开分形图 HTML；失败时静默。"""
    if not path:
        return
    try:
        uri = Path(path).resolve().as_uri()
        webbrowser.open(uri, new=2)  # new=2 尽量在新标签页打开
    except Exception:  # noqa: BLE001
        pass


def _build_agent_kwargs(args: argparse.Namespace) -> dict:
    """根据命令行参数构造 FractalAgent 的 agent_kwargs。"""
    agent_kwargs: dict = {}
    if args.model:
        agent_kwargs["model"] = args.model
    if args.toolsets:
        agent_kwargs["enabled_toolsets"] = [
            s.strip() for s in args.toolsets.split(",") if s.strip()
        ]
    return agent_kwargs


def run_repl(args: argparse.Namespace) -> int:
    print(BANNER)
    if not _credentials_available():
        _print_credential_hint()
        return 2

    agent_kwargs = _build_agent_kwargs(args)

    try:
        from fractal.agent import FractalAgent
        fa = FractalAgent(agent_kwargs=agent_kwargs)
    except Exception as exc:  # noqa: BLE001 —— 给用户友好提示而不是 traceback
        print(f"⚠ 初始化 Agent 失败：{type(exc).__name__}: {exc}\n")
        print("请检查 ~/.hermes/config.yaml 与 ~/.hermes/.env 的配置是否完整、")
        print("API key 是否有效；也可以先运行  python fenxing.py --demo  查看效果。")
        return 2

    print("输入问题开始对话，/help 查看命令，/quit 退出。")
    while True:
        try:
            q = input("\n分形> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.startswith("/"):
            cmd = q.split()[0].lower()
            if cmd in ("/quit", "/exit", "/q"):
                break
            if cmd == "/help":
                print(HELP_TEXT)
            elif cmd == "/graph":
                refreshed = fa.refresh_last()
                if refreshed and refreshed.get("html_path"):
                    print(f"最新推理图（已刷新）：{refreshed['html_path']}")
                    if getattr(args, "open", True):
                        _open_html(refreshed["html_path"])
                    pc = refreshed.get("pending_children", 0)
                    if pc:
                        print(f"[pending] 仍有 {pc} 个子任务在后台运行，稍后可再次 /graph 刷新。")
                elif refreshed and refreshed.get("trace_error"):
                    print(f"刷新失败：{refreshed['trace_error']}")
                else:
                    print("还没有生成任何图，先问一个问题吧。")
            elif cmd == "/demo":
                from fractal.demo import run_demo
                run_demo()
            else:
                print(f"未知命令 {cmd}，输入 /help 查看可用命令。")
            continue

        try:
            result = fa.ask(q)
        except KeyboardInterrupt:
            print("\n（已中断本轮调用）")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"⚠ 本轮调用失败：{type(exc).__name__}: {exc}")
            print("（常见原因：网络不通 / API key 失效 / 模型名错误；会话仍在，可继续提问）")
            continue

        print(f"\n{result['answer']}")
        if result.get("html_path"):
            print(f"\n推理分形图：{result['html_path']}")
            if getattr(args, "open", True):
                _open_html(result["html_path"])
        if result.get("pending_children"):
            print(f"[pending] {result['pending_children']} 个子任务仍在后台运行，"
                  f"完成后输入 /graph 刷新分形图")
        if result.get("trace_error"):
            print(f"（绘图环节出错但不影响回答：{result['trace_error']}）")

    print("再见")
    return 0


def run_gui(args: argparse.Namespace) -> int:
    """启动 tkinter 图形交互窗口。"""
    if not _credentials_available():
        _print_credential_hint()
        return 2
    try:
        from fractal.gui import FractalGui
    except Exception as exc:  # noqa: BLE001
        print(f"⚠ 无法启动 GUI：{type(exc).__name__}: {exc}")
        print("请确认当前环境支持图形界面；也可使用命令行模式：python fenxing.py")
        return 2
    FractalGui(agent_kwargs=_build_agent_kwargs(args)).run()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fenxing",
        description="分形Agent · FractalAgent —— 每次问答生成一张可交互的推理分形图",
    )
    parser.add_argument("--model", help="覆盖默认模型（等价于 hermes 的 model 配置）")
    parser.add_argument("--toolsets",
                        help="逗号分隔的工具集，如 web,terminal")
    parser.add_argument("--demo", action="store_true",
                        help="运行合成演示（无需 API key）后退出")
    parser.add_argument("--no-open", dest="open", action="store_false", default=True,
                        help="问答后不自动用浏览器打开分形图")
    parser.add_argument("--gui", action="store_true",
                        help="启动 tkinter 图形窗口交互（默认仍为命令行 REPL）")
    args = parser.parse_args(argv)

    if args.demo:
        from fractal.demo import run_demo
        run_demo()
        return 0
    if args.gui:
        return run_gui(args)
    return run_repl(args)


if __name__ == "__main__":
    sys.exit(main())
