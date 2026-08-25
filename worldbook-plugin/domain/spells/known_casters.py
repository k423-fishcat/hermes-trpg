"""已知型施法者（Known casters）

D&D 5e PHB：术士/吟游诗人/邪术师。
- 无需准备，从已知法术列表中直接施放
- 已知法术数量 = 职业表固定
- 邪术师特殊：契约法术位（短休恢复全部）
"""

from __future__ import annotations

from typing import Dict, List, Any

# 已知型职业名集合
KNOWN_CASTER_NAMES = {
    "术士", "吟游诗人", "邪术师",
    "sorcerer", "bard", "warlock",
}


def is_known_caster(class_name: str) -> bool:
    """判断是否是已知型施法者（大小写不敏感）"""
    if not class_name:
        return False
    return class_name.strip().lower() in {c.lower() for c in KNOWN_CASTER_NAMES}


def get_known_casters_for(class_name: str) -> List[str]:
    """列出某已知型职业在指定等级的已知法术数（仅占位，由 character_gen 填）"""
    # 实际计算在 character_gen.get_class_resources 等地方
    return []


def can_cast_from_known(class_name: str, spell_id: str,
                        spells_known: List[str]) -> Dict[str, Any]:
    """已知型：检查是否在 spells_known 中

    Returns:
        {"ok": bool, "reason": str}
    """
    if not is_known_caster(class_name):
        return {"ok": False, "reason": f"{class_name} 不是已知型施法者"}
    if spell_id in spells_known:
        return {"ok": True}
    return {"ok": False, "reason": f"{class_name}（已知型）不会这个法术: {spell_id}"}
