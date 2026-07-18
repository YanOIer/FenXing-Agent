"""分形Agent · FractalAgent —— 把每一轮问答的推理过程渲染成可交互的分形图。"""
from .agent import FractalAgent
from .render import render_trace_html, save_trace
from .trace import build_turn_trace

__all__ = ["FractalAgent", "build_turn_trace", "render_trace_html", "save_trace"]
__version__ = "0.1.0"
