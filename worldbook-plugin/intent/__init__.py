"""Intent Detector 公共入口

设计文档：docs/intent-detector-design.md

用法（injector.py）：
    from .intent import detect_intent
    trigger_text = detect_intent(user_message, template_name)
    if trigger_text:
        sections.append({"priority": 0, "name": "规则触发", "content": trigger_text, "max_ratio": 0.10})
"""

from __future__ import annotations

from typing import List, Optional

from .detector import detect, plan
from .types import ActionCategory, ActionRule, RuleEvent

# 规则表缓存（按 system 缓存，避免重复编译正则）
_RULES_CACHE: dict[str, List[ActionRule]] = {}


def _rules_for(system: str) -> List[ActionRule]:
    """获取指定系统的规则表（带缓存）"""
    if system not in _RULES_CACHE:
        if system == "dnd5e":
            from .dnd5e import build_rules
            _RULES_CACHE[system] = build_rules()
        else:
            # 3r / coc 规则表在 P3 实现，暂为空
            _RULES_CACHE[system] = []
    return _RULES_CACHE[system]


def detect_intent(user_input: str, template_name: str = "dnd5e") -> str:
    """扫描玩家输入，返回需注入的触发文本（空 = 无触发）

    Args:
        user_input: 玩家输入
        template_name: 模板名（dnd5e / dnd3r / coc7e）

    Returns:
        注入文本（多触发已按规则顺序拼接），无触发返回 ""
    """
    if not user_input or not user_input.strip():
        return ""

    tpl = (template_name or "dnd5e").lower()
    system = "dnd5e"
    if tpl in ("dnd3r", "dnd3.5", "dnd35e"):
        system = "dnd3r"
    elif tpl in ("coc", "coc7e", "coc7"):
        system = "coc7e"

    rules = _rules_for(system)
    if not rules:
        return ""

    events = detect(user_input, rules)
    return plan(events)


def get_events(user_input: str, template_name: str = "dnd5e") -> List[RuleEvent]:
    """暴露 RuleEvent 列表（测试用 / P2 planner 用）"""
    tpl = (template_name or "dnd5e").lower()
    system = "dnd5e"
    if tpl in ("dnd3r", "dnd3.5", "dnd35e"):
        system = "dnd3r"
    elif tpl in ("coc", "coc7e", "coc7"):
        system = "coc7e"
    return detect(user_input, _rules_for(system))


def clear_cache() -> None:
    """清空规则缓存（测试用）"""
    _RULES_CACHE.clear()


__all__ = ["detect_intent", "get_events", "clear_cache", "ActionCategory", "ActionRule", "RuleEvent"]
