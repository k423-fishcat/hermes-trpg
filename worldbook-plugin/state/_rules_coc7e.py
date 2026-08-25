"""state/ 包的 COC 7e 规则适配

COC 7e 与 D&D 关键差异：
- 没有"调整值"概念 — 技能直接是 0-99 百分比
- 属性（特征）有 8 个：STR/CON/SIZ/DEX/APP/INT/POW/EDU
- HP = (CON + SIZ) / 10
- MP = POW / 5
- SAN（理智值）= POW
- LUCK = POW * 5
- IDEA = INT * 5（灵感）
- KNOWLEDGE = EDU * 5（知识）
- 检定：d100 <= 技能值（越低越成功），支持奖励/惩罚骰
- 没有"等级"和"经验值"概念（调查员无升级，靠技能成长）
"""

from __future__ import annotations

from typing import Any, Dict

from . import _core


# 8 个 COC 7e 特征
_COC_ABILITIES = ("str", "con", "siz", "dex", "app", "int", "pow", "edu")


def get_modifier(state_mgr, ability: str) -> int:
    """COC 7e 没有调整值 — 直接返回原始特征值（0-99）

    与 D&D 5e/3.5 的"（score-10）//2"语义不同。
    """
    abbr = ability.lower()[:3]
    if abbr == "luc":  # LUK 别名
        abbr = "luk"
    score = _core.get(state_mgr, f"characteristics.{abbr}")
    if score is None:
        return 0
    return int(score)


def get_skill_modifier(state_mgr, skill_name: str) -> int:
    """COC 7e 技能值（0-99）— 直接返回，无调整值"""
    skills = _core.get(state_mgr, "skills") or {}
    val = skills.get(skill_name)
    if val is None:
        return 0
    return int(val)


def get_derived_stats(state_mgr) -> Dict[str, int]:
    """COC 7e 派生属性（HP/MP/SAN/LUCK/IDEA/KNOWLEDGE）"""
    chars = _core.get(state_mgr, "characteristics") or {}
    str_v = int(chars.get("str", 50))
    con_v = int(chars.get("con", 50))
    siz_v = int(chars.get("siz", 50))
    dex_v = int(chars.get("dex", 50))
    int_v = int(chars.get("int", 50))
    pow_v = int(chars.get("pow", 50))
    edu_v = int(chars.get("edu", 50))
    return {
        "hp_max": (con_v + siz_v) // 10,
        "mp_max": pow_v // 5,
        "san_max": pow_v,
        "luck": pow_v * 5,
        "idea": int_v * 5,
        "knowledge": edu_v * 5,
        "dodge": dex_v // 2,  # 闪避技能
    }


def compute_derived(state_mgr) -> Dict[str, int]:
    """计算并写入 derived 字段（HP/MP/SAN/LUCK 等）"""
    derived = get_derived_stats(state_mgr)
    # 保留 current 值（玩家可能已受伤/失智）
    existing = _core.get(state_mgr, "derived") or {}
    for k, v in derived.items():
        if k not in existing:
            existing[k] = v
        elif k.endswith("_max"):
            # max 总是按公式算
            existing[k] = v
    _core.update(state_mgr, {"derived": existing},
                  reason="重算派生属性", actor="系统")
    return existing


__all__ = [
    "get_modifier", "get_skill_modifier", "get_derived_stats", "compute_derived",
    "_COC_ABILITIES",
]
