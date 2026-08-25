"""state/ 包的 D&D 5e 规则适配（属性调整 + 技能调整）

被 StateManager facade 调用，外部不要直接用。
加 D&D 4e / COC 时新建 _rules_dnd4e.py / _rules_coc7e.py。
"""

from __future__ import annotations

from typing import Any

from . import _core


def get_modifier(state_mgr, ability: str) -> int:
    """获取属性调整值

    DnD 5e 风格：(score - 10) // 2
    COC 风格：直接返回原始值（COC 不用调整值）
    """
    abbr = ability.lower()[:3]
    _core.load_template(state_mgr, state_mgr.template_name)
    _core.load(state_mgr)

    for base_path in ["player.abilities", "characteristics"]:
        score = _core.get(state_mgr, f"{base_path}.{abbr}")
        if score is not None and isinstance(score, (int, float)):
            if _core.get(state_mgr, "player.proficiency_bonus") is not None:
                return (score - 10) // 2
            return score
    return 0


def get_skill_modifier(state_mgr, skill_name: str) -> int:
    """D&D 5e 技能加值 = 属性调整 + 熟练加值（如果熟练）

    Args:
        state_mgr: StateManager 实例
        skill_name: 技能名（中文，如 运动 / 察觉）

    Returns:
        技能检定加值（int）
    """
    tmpl = _core.load_template(state_mgr, state_mgr.template_name)
    skill_map = tmpl.get("skill_abilities", {})

    # 找到技能对应的能力
    ability = None
    for k, v in skill_map.items():
        if k.lower() == skill_name.lower() or k == skill_name:
            ability = v
            break
    abil_mod = get_modifier(state_mgr, ability) if ability else 0

    # 判断是否熟练（支持 bool 或 dict 两种 skills 格式）
    skills = _core.get(state_mgr, "player.skills") or {}
    is_prof = False
    for k, v in skills.items():
        if k.lower() == skill_name.lower() or k == skill_name:
            if isinstance(v, bool):
                is_prof = v
            elif isinstance(v, dict):
                is_prof = bool(v.get("proficient", False))
            else:
                is_prof = bool(v)
            break

    if is_prof:
        prof = _core.get(state_mgr, "player.proficiency_bonus") or 0
        return abil_mod + prof
    return abil_mod


__all__ = ["get_modifier", "get_skill_modifier"]
