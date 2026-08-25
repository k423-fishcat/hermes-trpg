"""Intent Detector：多命中扫描玩家输入 → RuleEvent 列表

设计文档：docs/intent-detector-design.md 三节
"""

from __future__ import annotations

from typing import List

from .types import ActionCategory, ActionRule, RuleEvent


def _to_event(rule: ActionRule, text: str) -> RuleEvent:
    """规则命中 → RuleEvent"""
    base = rule.name[:-len(".weak")] if rule.name.endswith(".weak") else rule.name
    return RuleEvent(
        type=rule.event_type,
        rule=base,
        category=rule.category,
        ability=rule.ability,
        skill=rule.skill,
        tool=rule.tool or "trpg_check",
        text=rule.inject,
    )


def detect(text: str, rules: List[ActionRule]) -> List[RuleEvent]:
    """扫描玩家输入，返回命中的规则事件（多命中，按顺序排序）

    Args:
        text: 玩家输入
        rules: 规则列表

    Returns:
        命中的 RuleEvent 列表（空 = 无触发）
    """
    events: List[RuleEvent] = []
    hit_strong: set[str] = set()  # 已强触发的技能（跳过其弱触发，防重复）

    # 强触发先处理（避免强/弱同技能都注入）；strength 小=强
    for rule in sorted(rules, key=lambda r: r.strength):
        if not rule.matches(text):
            continue
        base = rule.name[:-len(".weak")] if rule.name.endswith(".weak") else rule.name
        if rule.strength == 2 and base in hit_strong:
            continue  # 该技能已强触发，弱提示不需要
        events.append(_to_event(rule, text))
        if rule.strength == 1:
            hit_strong.add(base)

    # 按规则执行顺序排序
    events.sort(key=lambda e: e_order(e))
    return events


def e_order(event: RuleEvent) -> int:
    """事件执行顺序（skill_check 10 < initiative 20 < attack 30 < spell/rest 40 < loot 50）"""
    _ORDER = {
        "skill_check": 10,
        "initiative": 20,
        "attack": 30,
        "spell": 40,
        "rest": 40,
        "loot": 50,
    }
    return _ORDER.get(event.type, 99)


def plan(events: List[RuleEvent]) -> str:
    """把事件列表生成为注入文本"""
    if not events:
        return ""
    return "\n\n".join(e.text for e in events)


__all__ = ["detect", "plan"]
