"""准备型施法者（Prepared casters）

D&D 5e PHB：牧师/德鲁伊/圣武士/法师/游侠。
- 长休后从已知/职业法术列表选法术准备
- 法师特殊：从法术书（spells_known）准备，每日可换
- 准备数 = 施法属性调整 + 职业等级（最少 1）
"""

from __future__ import annotations

from typing import Dict, List, Any

# 准备型职业名集合
PREPARED_CASTER_NAMES = {
    "牧师", "德鲁伊", "圣武士", "法师", "游侠",
    "cleric", "druid", "paladin", "wizard", "ranger",
}


def is_prepared_caster(class_name: str) -> bool:
    """判断是否是准备型施法者（大小写不敏感）"""
    if not class_name:
        return False
    return class_name.strip().lower() in {c.lower() for c in PREPARED_CASTER_NAMES}


def max_prepared_count(level: int, spellcasting_ability: int) -> int:
    """准备型职业每日可准备的最大法术数

    PHB: 施法属性调整 + 职业等级（最少 1）
    """
    if level <= 0:
        return 0
    mod = (spellcasting_ability - 10) // 2
    return max(1, level + mod)


def can_cast_from_prepared(class_name: str, spell_id: str,
                           spells_known: List[str],
                           spells_prepared: List[str]) -> Dict[str, Any]:
    """准备型：检查是否同时在 known 和 prepared 中

    Returns:
        {"ok": bool, "reason": str}
    """
    if not is_prepared_caster(class_name):
        return {"ok": False, "reason": f"{class_name} 不是准备型施法者"}
    if spell_id not in spells_known:
        return {"ok": False, "reason": f"{class_name}（准备型）尚未习得此法术: {spell_id}"}
    if spell_id not in spells_prepared:
        return {"ok": False, "reason": f"{class_name}今天没有准备这个法术: {spell_id}"}
    return {"ok": True}
