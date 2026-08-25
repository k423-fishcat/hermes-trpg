"""conditions - 状态效果增删

独立于 CombatTracker，方便其他模块（spell 状态、装备 buff）复用。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def add_condition_to_creature(
    creature: Dict[str, Any],
    condition_name: str,
    display_name: str = "",
    duration: str = "",
    start_round: int = 1,
) -> Dict[str, Any]:
    """给目标添加状态效果（就地修改 creature）

    Returns:
        {"ok": bool, "duplicate": bool}
    """
    conditions = creature.setdefault("conditions", [])
    for c in conditions:
        if c.get("name") == condition_name:
            return {"ok": False, "duplicate": True}
    conditions.append({
        "name": condition_name,
        "display_name": display_name or condition_name,
        "duration": duration,
        "start_round": start_round,
    })
    return {"ok": True, "duplicate": False}


def remove_condition_from_creature(
    creature: Dict[str, Any],
    condition_name: str,
) -> Dict[str, Any]:
    """从目标移除状态效果

    Returns:
        {"ok": bool, "removed_count": int}
    """
    conditions = creature.get("conditions", [])
    new_conds = [c for c in conditions if c.get("name") != condition_name]
    removed = len(conditions) - len(new_conds)
    if removed == 0:
        return {"ok": False, "removed_count": 0}
    creature["conditions"] = new_conds
    return {"ok": True, "removed_count": removed}


def has_condition(creature: Dict[str, Any], condition_name: str) -> bool:
    return any(c.get("name") == condition_name
               for c in creature.get("conditions", []))


def list_conditions(creature: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(creature.get("conditions", []))
