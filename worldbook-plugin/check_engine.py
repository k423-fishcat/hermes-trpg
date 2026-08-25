"""检定引擎（Check Engine）

所有 DnD 5e 检定必须通过此引擎，确保规则一致性。
- 自动匹配技能→属性
- 自动从状态中读取加值（属性调整+熟练）
- 自动附规则引用（来自 dnd-rules）
- 支持优势/劣势
- 支持自定义加值/减值

设计目标：AI 不能口述判定结果，必须调用此工具。
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from .dice import roll_d20


# 技能 → 属性 映射（DnD 5e）
SKILL_TO_ABILITY = {
    # 力量
    "运动": "str",
    "athletics": "str",
    # 敏捷
    "体操": "dex",
    "acrobatics": "dex",
    "巧手": "dex",
    "sleight": "dex",
    "sleight of hand": "dex",
    "隐匿": "dex",
    "stealth": "dex",
    # 智力
    "奥秘": "int",
    "arcana": "int",
    "历史": "int",
    "history": "int",
    "调查": "int",
    "investigation": "int",
    "自然": "int",
    "nature": "int",
    "宗教": "int",
    "religion": "int",
    # 感知
    "驯兽": "wis",
    "animal handling": "wis",
    "洞悉": "wis",
    "insight": "wis",
    "医药": "wis",
    "medicine": "wis",
    "察觉": "wis",
    "perception": "wis",
    "生存": "wis",
    "survival": "wis",
    # 魅力
    "欺瞒": "cha",
    "deception": "cha",
    "威吓": "cha",
    "intimidation": "cha",
    "表演": "cha",
    "performance": "cha",
    "游说": "cha",
    "persuasion": "cha",
    "说服": "cha",
}

# 属性中文/英文/缩写映射
ABILITY_MAP = {
    "力量": "str", "力": "str", "str": "str", "strength": "str",
    "敏捷": "dex", "敏": "dex", "dex": "dex", "dexterity": "dex",
    "体质": "con", "体": "con", "con": "con", "constitution": "con",
    "智力": "int", "智": "int", "int": "int", "intelligence": "int",
    "感知": "wis", "意": "wis", "wis": "wis", "wisdom": "wisdom",
    "魅力": "cha", "魅": "cha", "cha": "cha", "charisma": "cha",
}

ABILITY_NAMES = {
    "str": "力量", "dex": "敏捷", "con": "体质",
    "int": "智力", "wis": "感知", "cha": "魅力",
}

# 豁免检定类型
SAVE_TYPES = {"str_save", "dex_save", "con_save", "int_save", "wis_save", "cha_save",
              "力量豁免", "敏捷豁免", "体质豁免", "智力豁免", "感知豁免", "魅力豁免"}

# DC 难度标准说明
DC_GUIDE = {
    5: "非常简单（日常动作，几乎不会失败）",
    10: "简单（熟练者轻松完成）",
    12: "简单偏难",
    13: "中等偏低",
    14: "中等",
    15: "中等（标准挑战）",
    16: "中等偏难",
    18: "困难",
    19: "困难偏高",
    20: "困难（需要专业技能或运气）",
    25: "极难（英雄级壮举）",
    30: "近乎不可能（传说中的事迹）",
}


def _ability_key(name: str) -> Optional[str]:
    """把任意格式的属性名转成标准 key"""
    if not name:
        return None
    name = name.strip().lower()
    return ABILITY_MAP.get(name)


def _skill_to_ability(skill_name: str) -> Optional[str]:
    """技能名 → 属性 key"""
    if not skill_name:
        return None
    key = skill_name.strip().lower()
    # 先直接查
    if key in SKILL_TO_ABILITY:
        return SKILL_TO_ABILITY[key]
    # 再模糊匹配中文
    for cn, ab in SKILL_TO_ABILITY.items():
        if len(cn) > 1 and cn in skill_name:
            return ab
    return None


def _modifier(score: int) -> int:
    """属性调整值"""
    return (score - 10) // 2


def _dc_label(dc: int) -> str:
    """DC 难度描述"""
    if dc in DC_GUIDE:
        return DC_GUIDE[dc]
    if dc < 8:
        return "非常简单"
    if dc < 12:
        return "简单"
    if dc < 17:
        return "中等"
    if dc < 22:
        return "困难"
    if dc < 28:
        return "极难"
    return "近乎不可能"


def _rule_reference(check_type: str, name: str) -> str:
    """生成规则引用文本。

    v2.9 起：优先从 RulesBook 查（带 rule_id），查不到再 fallback 到硬编码字符串。
    返回纯文本（兼容旧调用方），但内容现在更准确且带 PHB 页码。
    """
    # 尝试从 RulesBook 取
    try:
        from .app_context import get_app
        rules = get_app().rules
        if rules and rules.is_loaded("dnd5e"):
            rule = _lookup_rule_from_book(rules, check_type, name)
            if rule:
                phb = f" PHB p.{rule['phb_page']}" if rule.get("phb_page") else ""
                return (
                    f"规则依据：{rule['name_zh']} ({rule['rule_id']}{phb})。"
                    f"{rule.get('summary', rule.get('description', ''))[:200]}"
                )
    except Exception:
        pass

    # Fallback：保留原硬编码字符串
    if check_type == "ability":
        ab = ABILITY_NAMES.get(name, name)
        return f"规则依据：DnD 5e 属性检定（{ab}）。d20 + 属性调整值，结果 ≥ DC 则成功。"
    elif check_type == "save":
        ab = ABILITY_NAMES.get(name, name)
        return f"规则依据：DnD 5e 豁免检定（{ab}）。d20 + 豁免加值，结果 ≥ DC 则成功。常用于闪避法术/陷阱效果。"
    elif check_type == "skill":
        ab = _skill_to_ability(name)
        ab_cn = ABILITY_NAMES.get(ab, "?") if ab else "?"
        return f"规则依据：DnD 5e 技能检定「{name}」（{ab_cn}）。d20 + 属性调整 + 熟练加值（若熟练），结果 ≥ DC 则成功。"
    elif check_type == "death":
        return "规则依据：DnD 5e 死亡豁免。d20=20 立即恢复 1 HP，10-19 算一次成功，2-9 算一次失败，1 算两次失败。3次成功稳定，3次失败死亡。"
    return "规则依据：DnD 5e 核心规则。"


def _lookup_rule_from_book(rules, check_type: str, name: str) -> dict | None:
    """从 RulesBook 查规则。"""
    if check_type == "death":
        return rules.get("dnd5e", "combat", "death_saving_throw")
    if check_type == "ability":
        # 属性检定：没专门 rule，按豁免走
        ability_to_save = {
            "str": "save_str", "dex": "save_dex", "con": "save_con",
            "int": "save_int", "wis": "save_wis", "cha": "save_cha",
        }
        save_key = ability_to_save.get(name.lower())
        if save_key:
            return rules.get("dnd5e", "checks", save_key)
    if check_type == "save":
        ability_to_save = {
            "str": "save_str", "dex": "save_dex", "con": "save_con",
            "int": "save_int", "wis": "save_wis", "cha": "save_cha",
            "力量": "save_str", "敏捷": "save_dex", "体质": "save_con",
            "智力": "save_int", "感知": "save_wis", "魅力": "save_cha",
        }
        save_key = ability_to_save.get(name.lower())
        if save_key:
            return rules.get("dnd5e", "checks", save_key)
    if check_type == "skill":
        # 技能名（中文）→ rule_id slug
        skill_name_to_slug = {
            "运动": "athletics", "体操": "acrobatics", "巧手": "sleight_of_hand",
            "隐匿": "stealth", "奥秘": "arcana", "历史": "history",
            "调查": "investigation", "自然": "nature", "宗教": "religion",
            "驯兽": "animal_handling", "洞察": "insight", "医药": "medicine",
            "察觉": "perception", "生存": "survival", "欺瞒": "deception",
            "威吓": "intimidation", "表演": "performance", "说服": "persuasion",
        }
        slug = skill_name_to_slug.get(name) or name.lower().replace(" ", "_")
        return rules.get("dnd5e", "checks", slug)
    return None


def _get_player_bonus(state_mgr) -> Dict[str, Any]:
    """从状态中读取玩家属性、熟练加值、技能熟练情况

    返回：字典，包含：
      - abilities: 属性值 dict
      - proficiency: 熟练加值
      - save_profs: 豁免熟练 set {ability_key}

    注：技能熟练（skill_profs/expertise）已改由 state.get_skill_modifier()
    系统路由统一计算（见 roll_check 的 skill 分支），此处不再解析。
    """
    abilities = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}
    prof = 2
    save_profs = set()

    try:
        player = state_mgr.get("player") or {}
        ab = player.get("abilities", {})
        if ab:
            for k in abilities:
                if k in ab and ab[k]:
                    abilities[k] = ab[k]
                elif f"{k}_score" in ab:
                    abilities[k] = ab[f"{k}_score"]

        prof_val = player.get("proficiency_bonus")
        if prof_val is not None:
            prof = int(prof_val)

        # 豁免熟练（skill_data.save_proficient）
        skill_data = player.get("skill_data", {})
        if isinstance(skill_data, dict):
            for s in skill_data.get("save_proficient", []):
                save_profs.add(s)
    except Exception:
        pass

    return {
        "abilities": abilities,
        "proficiency": prof,
        "save_profs": save_profs,
    }


def roll_check(state_mgr, check_type: str = "skill",
               check_name: str = "",
               dc: int = 15,
               advantage: bool = False,
               disadvantage: bool = False,
               bonus: int = 0,
               use_proficiency: bool = True,
               description: str = "",
               chron: Any = None) -> Dict[str, Any]:
    """执行一次检定

    Args:
        state_mgr: StateManager 实例
        check_type: skill / ability / save / death / coc
        check_name: 技能名或属性名或豁免名（COC: 技能名）
        dc: 难度等级（D&D 用；COC 自动按技能值算）
        advantage: 是否优势
        disadvantage: 是否劣势
        bonus: 额外加值/减值
        use_proficiency: 是否计算熟练加值（技能检定默认是，属性检定默认否）
        description: 检定描述
        chron: ChronicleManager 实例（可选），传入后会把检定记到编年史

    Returns:
        完整的检定结果字典
    """
    # COC 7e 走 d100 vs 技能值路径
    if (state_mgr.template_name or "").lower() in ("coc", "coc7e", "coc7"):
        return _roll_coc_check(state_mgr, check_name, bonus, description, chron)

    # D&D 5e / 3r 共用下面的逻辑（rules adapter 已自动路由）
    # 1. 确定属性
    ability_key = None
    display_name = check_name

    if check_type == "skill":
        ability_key = _skill_to_ability(check_name)
        if not ability_key:
            # 没识别出来，默认按属性算
            ability_key = _ability_key(check_name) or "wis"
            display_name = check_name
        else:
            display_name = check_name
    elif check_type == "ability":
        ability_key = _ability_key(check_name) or "str"
        display_name = f"{ABILITY_NAMES.get(ability_key, ability_key)}检定"
    elif check_type == "save":
        # 豁免检定：从名字里提取属性
        raw = check_name.lower().replace("豁免", "").replace("save", "").strip()
        ability_key = _ability_key(raw) or _ability_key(check_name) or "dex"
        display_name = f"{ABILITY_NAMES.get(ability_key, ability_key)}豁免"
    elif check_type == "death":
        ability_key = None
        display_name = "死亡豁免"

    # 2. 从状态读加值
    bonus_data = _get_player_bonus(state_mgr)
    abilities = bonus_data["abilities"]
    prof_bonus = bonus_data["proficiency"]
    save_profs = bonus_data["save_profs"]

    if ability_key:
        ability_score = abilities.get(ability_key, 10)
        ability_mod = _modifier(ability_score)
    else:
        ability_score = 10
        ability_mod = 0

    # 计算熟练加值
    prof_add = 0
    is_proficient = False
    is_expertise = False
    if use_proficiency:
        if check_type == "skill":
            # 系统路由：get_skill_modifier 按模板自动分发
            #  5e: 属性调整 + 熟练加值（若熟练）
            #  3r: 属性调整 + 技能点（class_skill 全额 / 跨职业减半）
            #  prof_add = 适配器加值 - 纯属性加值 = 熟练/技能点部分
            skill_total = state_mgr.get_skill_modifier(check_name)
            prof_add = max(0, skill_total - ability_mod)
            is_proficient = prof_add > 0
            is_expertise = False  # 双倍熟练已含在 get_skill_modifier 的 PB 计算里
        elif check_type == "save":
            # 从角色卡数据读豁免熟练
            if ability_key in save_profs:
                is_proficient = True
                prof_add = prof_bonus

    # 总加值
    total_bonus = ability_mod + prof_add + bonus

    # 3. 骰 d20
    d20_result = roll_d20(advantage=advantage, disadvantage=disadvantage)
    nat_roll = d20_result["nat_roll"]
    if d20_result["is_advantage"]:
        rolls = d20_result["all_rolls"]
        roll_detail = f"优势骰: 1d20({rolls[0]}) + 1d20({rolls[1]}) = 取{nat_roll}"
    elif d20_result["is_disadvantage"]:
        rolls = d20_result["all_rolls"]
        roll_detail = f"劣势骰: 1d20({rolls[0]}) + 1d20({rolls[1]}) = 取{nat_roll}"
    else:
        roll_detail = f"1d20 = {nat_roll}"

    # 4. 判定
    total = nat_roll + total_bonus
    is_crit_success = (nat_roll == 20)
    is_crit_fail = (nat_roll == 1)

    if check_type == "death":
        # 死亡豁免特殊规则
        if nat_roll == 20:
            result = "crit_success"
            result_text = "大成功！恢复 1 点生命值"
        elif nat_roll == 1:
            result = "crit_fail"
            result_text = "大失败！算两次失败"
        elif total >= 10:
            result = "success"
            result_text = "成功！算一次成功"
        else:
            result = "fail"
            result_text = "失败！算一次失败"
    else:
        if is_crit_success:
            result = "crit_success"
            result_text = "大成功！"
        elif is_crit_fail:
            result = "crit_fail"
            result_text = "大失败！"
        elif total >= dc:
            result = "success"
            result_text = "成功"
        else:
            result = "fail"
            result_text = "失败"

    # 5. 规则引用
    rule = _rule_reference(check_type, check_name)

    # 6. 记录到事件日志
    if description and chron is not None:
        try:
            chron.add_event(
                f"检定：{description} | {display_name} DC{dc} → {result_text}（d20={nat_roll}+{total_bonus:+d}={total}）",
                importance="normal"
            )
        except Exception:
            # 编年史记录失败不阻塞检定结果
            pass

    # 7. 组装结果
    tpl = (state_mgr.template_name or "").lower()
    if tpl in ("dnd3r", "dnd3.5", "dnd35e"):
        _system_tag = "dnd3r"
    elif tpl in ("coc", "coc7e", "coc7"):
        _system_tag = "coc7e"
    else:
        _system_tag = "dnd5e"
    return {
        "success": True,
        "system": _system_tag,
        "type": check_type,
        "name": display_name,
        "ability": ability_key,
        "ability_score": ability_score,
        "ability_mod": ability_mod,
        "proficiency": is_proficient,
        "proficiency_bonus": prof_add,
        "other_bonus": bonus,
        "total_bonus": total_bonus,
        "dc": dc,
        "dc_difficulty": _dc_label(dc),
        "natural_roll": nat_roll,
        "roll_detail": roll_detail,
        "total": total,
        "result": result,
        "result_text": result_text,
        "advantage": advantage and not disadvantage,
        "disadvantage": disadvantage and not advantage,
        "rule_reference": rule,
        "description": description,
        "timestamp": time.strftime("%H:%M:%S"),
    }


def format_check_result(r: Dict[str, Any]) -> str:
    """格式化检定结果为可读文本（COC / D&D 自动识别）"""
    if r.get("system") == "coc7e":
        return format_coc_check_result(r)
    lines = []

    # 标题
    emoji = {
        "crit_success": "💥", "success": "✅",
        "crit_fail": "💀", "fail": "❌"
    }.get(r["result"], "🎲")

    title = f"{emoji} {r['name']} 检定 — {r['result_text']}"
    lines.append(title)
    lines.append("─" * 40)

    # DC 信息
    lines.append(f"📊 难度: DC {r['dc']}（{r['dc_difficulty']}）")

    # 加值明细
    lines.append(f"➕ 加值: {r['total_bonus']:+d} "
                 f"（{ABILITY_NAMES.get(r['ability'], '?')}调整{r['ability_mod']:+d}")
    if r['proficiency']:
        lines[-1] += f"，熟练+{r['proficiency_bonus']}"
    if r['other_bonus'] != 0:
        lines[-1] += f"，其他{r['other_bonus']:+d}"
    lines[-1] += "）"

    # 掷骰
    lines.append(f"🎲 掷骰: {r['roll_detail']}")
    lines.append(f"📐 结果: {r['natural_roll']} + {r['total_bonus']} = {r['total']}")

    # 判定
    if r['result'] == 'crit_success':
        lines.append(f"\n💥 大成功！天然 20！")
    elif r['result'] == 'crit_fail':
        lines.append(f"\n💀 大失败！天然 1！")
    elif r['result'] == 'success':
        diff = r['total'] - r['dc']
        lines.append(f"\n✅ 成功（超过 DC {diff:+d}）")
    else:
        diff = r['dc'] - r['total']
        lines.append(f"\n❌ 失败（差 {diff} 点）")

    # 规则引用
    lines.append("")
    lines.append(f"📖 {r['rule_reference']}")

    return "\n".join(lines)


# ============================================================
# COC 7e 检定（d100 vs 技能值）
# ============================================================

def _roll_coc_check(state_mgr, skill_name: str, bonus: int,
                    description: str, chron: Any) -> Dict[str, Any]:
    """COC 7e 技能检定：d100 <= 技能值（越低越成功）

    Args:
        skill_name: 技能名（中文/英文都行）
        bonus: 奖励/惩罚骰数量（正=奖励，负=惩罚）
        description: 检定描述
        chron: ChronicleManager（可选）

    Returns:
        完整检定结果字典（结构与 D&D roll_check 一致）
    """
    from .dice import coc_check
    from .state._rules_coc7e import get_skill_modifier

    skill_value = get_skill_modifier(state_mgr, skill_name)
    # bonus > 0 = 奖励骰数；bonus < 0 = 惩罚骰数（绝对值）
    b_dice = max(0, bonus)
    p_dice = max(0, -bonus)

    result = coc_check(skill_value, bonus_dice=b_dice, penalty_dice=p_dice)

    out = {
        "system": "coc7e",
        "type": "skill",
        "name": skill_name,
        "skill_value": skill_value,
        "roll": result["roll"],
        "units": result["units"],
        "tens_all": result["tens_all"],
        "level": result["level"],
        "success": result["success"],
        "margin": result["margin"],
        "bonus_dice": b_dice,
        "penalty_dice": p_dice,
        "description": description,
        "timestamp": time.strftime("%H:%M:%S"),
    }
    out["result"] = "success" if result["success"] else "fail"
    out["result_text"] = result["level"]

    # 写入编年史
    if description and chron is not None:
        try:
            chron.add_event(
                f"COC检定：{description} | {skill_name} 技能{skill_value} → {result['roll']} ({result['level']})",
                importance="normal",
            )
        except Exception:
            pass

    return out


def format_coc_check_result(r: Dict[str, Any]) -> str:
    """格式化 COC 检定结果"""
    icon = {
        "大成功": "💥", "极难成功": "✨", "困难成功": "✅", "成功": "✅",
        "失败": "❌", "大失败": "💀",
    }.get(r.get("level", ""), "🎲")
    lines = [
        f"{icon} {r['name']}（技能 {r['skill_value']}）",
        "─" * 40,
        f"🎯 骰值: {r['roll']}（个位 {r['units']}，十位 {r['tens_all']}）",
    ]
    if r.get("bonus_dice"):
        lines.append(f"  奖励骰: {r['bonus_dice']}")
    if r.get("penalty_dice"):
        lines.append(f"  惩罚骰: {r['penalty_dice']}")
    if r.get("description"):
        lines.append(f"  描述: {r['description']}")
    if r["success"]:
        diff = r["margin"]
        lines.append(f"\n✅ {r['level']}（超过技能 {diff} 点）")
    else:
        diff = abs(r["margin"])
        lines.append(f"\n❌ {r['level']}（差 {diff} 点）")
    return "\n".join(lines)
