"""fractal.recorder —— 全局子轨迹记录器。

从 fractal 层用 monkeypatch 包装 ``AIAgent.run_conversation``（不改动 hermes
核心任何文件），把每一次对话执行——包括后台线程里跑的 delegate 子 agent——
记录到线程安全的内存仓库里，供构图时按 goal 匹配子轨迹。

特性：
- ``install_recorder()`` 幂等；包装器 fail-open，记录逻辑任何异常都不影响
  ``run_conversation`` 本身。
- 线程安全（threading.Lock）；deque(maxlen=200) 防内存膨胀。
- root agent（depth=0）自己的调用也会被记录，FractalAgent 主流程不使用它。
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any

_MAX_RECORDS = 200

_lock = threading.Lock()
_records: deque = deque(maxlen=_MAX_RECORDS)
_installed = False


def _msg_to_text(content: Any) -> str:
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


def _normalize(text: Any) -> str:
    return " ".join(_msg_to_text(text).split())


def install_recorder() -> bool:
    """幂等安装 monkeypatch。返回是否成功挂上（失败不影响任何主流程）。"""
    global _installed
    if _installed:
        return True
    try:
        from run_agent import AIAgent
    except Exception:  # noqa: BLE001 —— hermes 依赖不可用时静默放弃
        return False
    try:
        original = AIAgent.run_conversation
        if getattr(original, "_fractal_wrapped", False):
            _installed = True
            return True

        def wrapped(self, user_message=None, *args, **kwargs):
            rec = None
            try:
                rec = {
                    "record_id": uuid.uuid4().hex,
                    "user_message": _normalize(user_message),
                    "started_at": time.time(),
                    "depth": getattr(self, "_delegate_depth", 0),
                    "role": getattr(self, "_delegate_role", None),
                    "session_id": getattr(self, "session_id", None),
                    "parent_session_id": getattr(self, "parent_session_id", None),
                }
            except Exception:  # noqa: BLE001
                rec = None
            result = original(self, user_message, *args, **kwargs)
            if rec is not None:
                try:
                    rec["ended_at"] = time.time()
                    if isinstance(result, dict):
                        rec["messages"] = result.get("messages") or []
                        rec["final_response"] = result.get("final_response") or ""
                    else:
                        rec["messages"] = []
                        rec["final_response"] = ""
                    with _lock:
                        _records.append(rec)
                except Exception:  # noqa: BLE001
                    pass
            return result

        wrapped._fractal_wrapped = True  # type: ignore[attr-defined]
        wrapped._fractal_original = original  # type: ignore[attr-defined]
        AIAgent.run_conversation = wrapped
        _installed = True
        return True
    except Exception:  # noqa: BLE001
        return False


def find_children(goal: str, since: float | None = None) -> list[dict]:
    """按规整化 goal 精确或前缀匹配记录，按 started_at 从新到旧返回。

    ``since`` 为时间下界（通常是本轮开始时间）：优先返回不早于 since 的匹配；
    若过滤后为空则回退到全量匹配（容忍时钟/播种时序差异）。
    """
    g = _normalize(goal)
    if not g:
        return []
    with _lock:
        recs = list(_records)

    def _match(r: dict) -> bool:
        um = r.get("user_message") or ""
        return um == g or um.startswith(g) or g.startswith(um)

    candidates = [r for r in recs if _match(r)]
    if since is not None:
        fresh = [r for r in candidates if (r.get("started_at") or 0) >= since]
        if fresh:
            candidates = fresh
    candidates.sort(key=lambda r: r.get("started_at") or 0, reverse=True)
    return candidates


def is_pending(goal: str, since: float | None = None) -> bool:
    """delegate_task 已发出但仓库里暂无匹配记录 → 视为仍在后台运行。"""
    return not find_children(goal, since)


# ---------------------------------------------------------------- 测试辅助
def push_record(rec: dict) -> dict:
    """手动塞入一条记录（演示/测试用）。自动补齐 id 与时间戳并规整 user_message。"""
    rec = dict(rec)
    rec.setdefault("record_id", uuid.uuid4().hex)
    rec["user_message"] = _normalize(rec.get("user_message"))
    rec.setdefault("started_at", time.time())
    rec.setdefault("ended_at", time.time())
    with _lock:
        _records.append(rec)
    return rec


def snapshot() -> list[dict]:
    with _lock:
        return list(_records)


def clear() -> None:
    with _lock:
        _records.clear()
