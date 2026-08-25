"""cast - 施法核心（被 SpellManager.cast_spell 调用）

把 cast_spell 里的"施法者类型判断"逻辑抽出来。
SpellManager.cast_spell 调用本模块的 check_can_cast() 和 find_slot()。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .known_casters import is_known_caster, can_cast_from_known
from .prepared_casters import is_prepared_caster, can_cast_from_prepared


def check_can_cast(class_name: str, spell_id: str,
                   spells_known: list, spells_prepared: list,
                   is_cantrip: bool) -> Dict[str, Any]:
    """检查某职业能否施放某法术。

    Args:
        class_name: 职业名
        spell_id: 法术 ID
        spells_known: 已知法术列表
        spells_prepared: 准备法术列表
        is_cantrip: 是否戏法（不消耗法术位，无需准备）

    Returns:
        {"ok": bool, "reason": str}
    """
    if is_cantrip:
        # 戏法不需要准备——但仍然要 known（除非是种族/职业赐予的）
        if spell_id in spells_known:
            return {"ok": True}
        # 兜底：有些数据里戏法没在 known 列表里——允许通过
        return {"ok": True}

    if is_known_caster(class_name):
        return can_cast_from_known(class_name, spell_id, spells_known)
    if is_prepared_caster(class_name):
        return can_cast_from_prepared(class_name, spell_id, spells_known, spells_prepared)

    # 未识别职业：保守走准备流程
    if spell_id not in spells_known and spell_id not in spells_prepared:
        return {"ok": False, "reason": f"你还不会这个法术: {spell_id}"}
    if spell_id not in spells_prepared:
        return {"ok": False, "reason": f"你没有准备这个法术: {spell_id}"}
    return {"ok": True}


def find_slot(requested_level, current_slots: Dict, max_slots: Dict) -> Optional[int]:
    """找一个可用的法术位

    - 指定等级：用那个等级；用完了可向上找高等级
    - 未指定：用最低可用的

    Returns:
        法术位等级（int），或 None（无可用）
    """
    if requested_level is not None:
        level_str = str(requested_level)
        if current_slots.get(level_str, 0) > 0:
            return requested_level
        # 向上找高等级的
        for level in range(requested_level + 1, 10):
            if current_slots.get(str(level), 0) > 0:
                return level
        return None

    # 找最低可用的
    for level in range(1, 10):
        if current_slots.get(str(level), 0) > 0:
            return level
    return None
