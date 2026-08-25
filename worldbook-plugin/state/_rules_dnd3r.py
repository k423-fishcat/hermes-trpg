"""state/ 包的 D&D 3.5 Revised 规则适配

D&D 3.5 与 5e 关键差异：
- 属性调整值：相同 (score - 10) // 2
- AC：分总 AC / 接触 AC / 措手不及 AC（无 DEX）
- 攻击：d20 + BAB + 调整值 vs AC（5e 是熟练 + 调整）
- 豁免：Fort/Ref/Will 三项 + 基础值随职业和等级增长（5e 是 PB + 调整）
- 技能：跨职业技能点减半（5e 是熟练 OR 不熟练）
- 等级上限 20（5e 也是 20）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import _core


# D&D 3.5 职业 BAB / 豁免进度
# 来源：d20srd.org 职业表（精简版）
# BAB 进度："full"=等级, "3/4"=3/4 等级, "1/2"=1/2 等级
# 豁免进度："good" 或 "poor"
_CLASS_PROGRESS = {
    # 全 BAB + 强豁免
    "barbarian": {"bab": "full", "fort": "good", "ref": "poor", "will": "poor", "hd": 12, "skill_pts": 4},
    "fighter":  {"bab": "full", "fort": "good", "ref": "poor", "will": "poor", "hd": 10, "skill_pts": 2},
    "paladin":  {"bab": "full", "fort": "good", "ref": "poor", "will": "good", "hd": 10, "skill_pts": 2},
    "ranger":   {"bab": "full", "fort": "good", "ref": "good", "will": "poor", "hd": 8,  "skill_pts": 6},
    # 3/4 BAB + 中等豁免
    "bard":     {"bab": "3/4", "fort": "poor", "ref": "good", "will": "good", "hd": 6,  "skill_pts": 6},
    "cleric":   {"bab": "3/4", "fort": "good", "ref": "poor", "will": "good", "hd": 8,  "skill_pts": 2},
    "druid":    {"bab": "3/4", "fort": "good", "ref": "poor", "will": "good", "hd": 8,  "skill_pts": 4},
    "monk":     {"bab": "3/4", "fort": "good", "ref": "good", "will": "good", "hd": 8,  "skill_pts": 4},
    "rogue":    {"bab": "3/4", "fort": "poor", "ref": "good", "will": "poor", "hd": 6,  "skill_pts": 8},
    # 1/2 BAB + 弱豁免（施法者）
    "sorcerer": {"bab": "1/2", "fort": "poor", "ref": "poor", "will": "good", "hd": 4,  "skill_pts": 2},
    "wizard":   {"bab": "1/2", "fort": "poor", "ref": "poor", "will": "good", "hd": 4,  "skill_pts": 2},
}
_DEFAULT_PROGRESS = {"bab": "1/2", "fort": "poor", "ref": "poor", "will": "poor", "hd": 8, "skill_pts": 2}


def _class_progress(class_name: str) -> dict:
    cn = (class_name or "").lower()
    for k, v in _CLASS_PROGRESS.items():
        if k in cn or cn in k:
            return v
    return _DEFAULT_PROGRESS


def _bab(level: int, progress: str) -> int:
    """基础攻击加值 BAB"""
    if progress == "full":
        return level
    if progress == "3/4":
        return (level * 3 + 1) // 4  # 向上取整
    if progress == "1/2":
        return level // 2
    return 0


def _good_save(level: int) -> int:
    """强豁免基础值 = 2 + 等级/2"""
    return 2 + level // 2


def _poor_save(level: int) -> int:
    """弱豁免基础值 = 等级/3"""
    return level // 3


def get_modifier(state_mgr, ability: str) -> int:
    """D&D 3.5 属性调整值 = (score - 10) // 2（与 5e 相同）"""
    abbr = ability.lower()[:3]
    for base_path in ["player.abilities", "characteristics"]:
        score = _core.get(state_mgr, f"{base_path}.{abbr}")
        if score is not None and isinstance(score, (int, float)):
            return (score - 10) // 2
    return 0


def get_skill_modifier(state_mgr, skill_name: str) -> int:
    """D&D 3.5 技能加值 = 调整值 + (职业技能点 vs 跨职业点)"""
    tmpl = _core.load_template(state_mgr, state_mgr.template_name)
    skill_map = tmpl.get("skill_abilities", {})

    abbr = skill_name.lower()
    ab = None
    for k, v in skill_map.items():
        if k.lower() == abbr or k == skill_name:
            ab = v
            break

    if not ab:
        return 0

    abil_mod = get_modifier(state_mgr, ab)

    # 读取技能点
    skills = _core.get(state_mgr, "player.skills") or {}
    rank = 0
    is_class_skill = True  # 默认 class skill
    for k, v in skills.items():
        if k.lower() == abbr or k == skill_name:
            rank = v.get("ranks", 0) if isinstance(v, dict) else int(v or 0)
            is_class_skill = v.get("class_skill", True) if isinstance(v, dict) else True
            break

    if not is_class_skill:
        rank = rank // 2  # 跨职业减半

    return abil_mod + rank


def get_bab(state_mgr) -> int:
    """基础攻击加值 = 职业 BAB 进度按等级推导

    D&D 3.5 的 BAB 是职业/等级的派生值，不持久化在 player 里。
    """
    player = _core.get(state_mgr, "player") or {}
    level = int(player.get("level", 1))
    cn = player.get("class", "")
    prog = _class_progress(cn)
    return _bab(level, prog["bab"])


def get_saving_throw(state_mgr, save_key: str) -> int:
    """D&D 3.5 豁免值 = 基础 + 调整值"""
    player = _core.get(state_mgr, "player") or {}
    level = int(player.get("level", 1))
    cn = player.get("class", "")
    prog = _class_progress(cn)
    key_map = {"fortitude": "fort", "reflex": "ref", "will": "will"}
    progress = prog.get(key_map.get(save_key, ""), "poor")
    base = _good_save(level) if progress == "good" else _poor_save(level)
    tmpl = _core.load_template(state_mgr, state_mgr.template_name)
    ab_key = tmpl.get("saving_throw_abilities", {}).get(save_key, "con")
    return base + get_modifier(state_mgr, ab_key)


def get_ac(state_mgr) -> Dict[str, int]:
    """完整 AC 分解（3.5 风格：分总 AC / 接触 AC / 措手不及 AC）"""
    player = _core.get(state_mgr, "player") or {}
    ac = player.get("ac", {})
    if not isinstance(ac, dict):
        return {"total": 10, "touch": 10, "flat_footed": 10}
    return ac


def get_initiative_mod(state_mgr) -> int:
    """先攻加值 = 敏捷调整"""
    return get_modifier(state_mgr, "dex")


__all__ = [
    "get_modifier", "get_skill_modifier", "get_bab", "get_saving_throw",
    "get_ac", "get_initiative_mod",
]
