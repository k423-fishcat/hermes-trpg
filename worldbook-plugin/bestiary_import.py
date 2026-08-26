"""SRD 怪物导入工具

从 dnd-rules MCP 拉取怪物数据，转换成 bestiary 格式保存到本地。
支持：
- 批量搜索并导入
- 按 CR 范围/类型过滤导入
- 增量更新（已存在的跳过或覆盖）
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _load_creature_name_map() -> Dict[str, str]:
    """加载 rules/zh_mapping.json 中的怪物中文名映射"""
    mapping_path = Path(__file__).resolve().parent / "rules" / "zh_mapping.json"
    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("creatures", {})
    except Exception:
        return {}


# 懒加载：只在需要时读一次
_CREATURE_NAME_MAP: Dict[str, str] = {}


def _get_creature_name(key_or_name: str) -> str:
    """根据 SRD key 或英文名取中文名，找不到返回空字符串"""
    global _CREATURE_NAME_MAP
    if not _CREATURE_NAME_MAP:
        _CREATURE_NAME_MAP = _load_creature_name_map()
    # key 形如 srd-2024_goblin，取末段
    slug = key_or_name.split("_")[-1] if "_" in key_or_name else key_or_name
    return _CREATURE_NAME_MAP.get(slug, "")


def convert_creature_to_bestiary(src: dict) -> dict:
    """把 dnd-rules 的结构化怪物数据转成 bestiary 格式"""

    name = src.get("name", "")
    key = src.get("key", "")

    # 尝试中文名映射
    cn_name = _get_creature_name(key) or _get_creature_name(name)
    size_obj = src.get("size", {})
    type_obj = src.get("type", {})
    speed_obj = src.get("speed", {})
    speed_all = src.get("speed_all", {})

    # 速度
    speeds = {}
    if speed_all.get("walk"):
        speeds["walk"] = speed_all["walk"]
    if speed_all.get("fly"):
        speeds["fly"] = speed_all["fly"]
    if speed_all.get("swim"):
        speeds["swim"] = speed_all["swim"]
    if speed_all.get("climb"):
        speeds["climb"] = speed_all["climb"]
    if speed_all.get("burrow"):
        speeds["burrow"] = speed_all["burrow"]

    speed_display = speed_obj.get("walk", 30)
    speed_special = {}
    for k, v in speeds.items():
        if k != "walk" and v:
            speed_special[k] = v

    # 属性
    abilities = {}
    ability_map = {
        "strength": "str",
        "dexterity": "dex",
        "constitution": "con",
        "intelligence": "int",
        "wisdom": "wis",
        "charisma": "cha",
    }
    abbr_full = {
        "str": "力量", "dex": "敏捷", "con": "体质",
        "int": "智力", "wis": "感知", "cha": "魅力",
    }
    for full, abbr in ability_map.items():
        abilities[abbr] = src.get("ability_scores", {}).get(full, 10)

    # 技能
    skills = {}
    skill_map = {
        "acrobatics": "体操",
        "animal_handling": "驯兽",
        "arcana": "奥秘",
        "athletics": "运动",
        "deception": "欺瞒",
        "history": "历史",
        "insight": "洞悉",
        "intimidation": "威吓",
        "investigation": "调查",
        "medicine": "医药",
        "nature": "自然",
        "perception": "察觉",
        "performance": "表演",
        "persuasion": "游说",
        "religion": "宗教",
        "sleight_of_hand": "巧手",
        "stealth": "隐匿",
        "survival": "生存",
    }
    skill_bonuses = src.get("skill_bonuses_all", {})
    for eng, cn in skill_map.items():
        bonus = skill_bonuses.get(eng)
        if bonus is not None and bonus != 0:
            # 只存熟练的（加值 > 属性调整值 或等于0但可能有其他修正）
            # 简化：所有非零技能都存
            skills[cn] = bonus

    # 感官
    senses = {}
    if src.get("darkvision_range"):
        senses["黑暗视觉"] = src["darkvision_range"]
    if src.get("blindsight_range"):
        senses["盲感"] = src["blindsight_range"]
    if src.get("tremorsense_range"):
        senses["震动感知"] = src["tremorsense_range"]
    if src.get("truesight_range"):
        senses["真视"] = src["truesight_range"]
    if src.get("passive_perception"):
        senses["被动察觉"] = src["passive_perception"]

    # 语言
    lang_obj = src.get("languages", {})
    languages = []
    for lang in lang_obj.get("data", []):
        languages.append(lang.get("name", ""))

    # 攻击
    attacks = []
    for action in src.get("actions", []):
        action_type = action.get("action_type", "")
        act_attacks = action.get("attacks", [])
        if not act_attacks:
            continue

        for atk in act_attacks:
            dmg_type_obj = atk.get("damage_type", {}) or {}
            dmg_type = dmg_type_obj.get("name", "")
            # 从动作名推断攻击名
            atk_name = action.get("name", "")

            damage_die_count = atk.get("damage_die_count", 1)
            damage_die_type = atk.get("damage_die_type", "d6")
            damage_bonus = atk.get("damage_bonus", 0)
            damage_str = f"{damage_die_count}{damage_die_type.lower()}"
            if damage_bonus:
                damage_str += f"+{damage_bonus}"

            # 攻击类型
            if action_type == "ACTION":
                atk_type_display = "近战武器攻击" if atk.get("reach") else "远程武器攻击"
                if atk.get("attack_type") == "SPELL":
                    atk_type_display = "法术攻击"
            elif action_type == "BONUS_ACTION":
                atk_type_display = "附赠动作攻击"
            else:
                atk_type_display = action_type or "攻击"

            range_str = ""
            if atk.get("reach"):
                range_str = f"{atk['reach']}尺"
            elif atk.get("range"):
                long_range = atk.get("long_range")
                range_str = f"{atk['range']}/{long_range}尺" if long_range else f"{atk['range']}尺"

            attack_entry = {
                "name": atk_name,
                "type": atk_type_display,
                "hit_bonus": atk.get("to_hit_mod", 0),
                "range": range_str,
                "damage": damage_str,
                "damage_type": dmg_type,
            }
            # 额外伤害（偷袭之类）
            if atk.get("extra_damage_die_count"):
                extra_count = atk["extra_damage_die_count"]
                extra_die = atk.get("extra_damage_die_type", "d6")
                extra_bonus = atk.get("extra_damage_bonus", 0)
                extra_type_obj = atk.get("extra_damage_type", {}) or {}
                extra_type = extra_type_obj.get("name", "")
                extra_str = f"{extra_count}{extra_die.lower()}"
                if extra_bonus:
                    extra_str += f"+{extra_bonus}"
                attack_entry["extra_damage"] = extra_str
                attack_entry["extra_damage_type"] = extra_type
                attack_entry["extra_condition"] = "有优势时"  # 简化描述

            attacks.append(attack_entry)

    # 特殊能力（traits + 非攻击类的 actions/reactions）
    special_abilities = []
    for trait in src.get("traits", []):
        special_abilities.append({
            "name": trait.get("name", ""),
            "desc": trait.get("desc", ""),
        })
    # 非攻击的动作/反应也归入特性
    for action in src.get("actions", []):
        if not action.get("attacks") and action.get("name") and action.get("desc"):
            special_abilities.append({
                "name": f"{action['name']}（{_action_type_label(action.get('action_type', ''))}）",
                "desc": action.get("desc", ""),
            })

    # 传奇动作
    legendary_actions = []
    for action in src.get("legendary_actions", []):
        legendary_actions.append({
            "name": action.get("name", ""),
            "desc": action.get("desc", ""),
            "cost": action.get("legendary_action_cost", 1),
        })

    # 抗性免疫
    res_imm = src.get("resistances_and_immunities", {})
    damage_resistances = res_imm.get("damage_resistances_display", "")
    damage_resistances = [s.strip() for s in damage_resistances.split(",") if s.strip()] if isinstance(damage_resistances, str) else res_imm.get("damage_resistances", [])
    damage_immunities = res_imm.get("damage_immunities_display", "")
    damage_immunities = [s.strip() for s in damage_immunities.split(",") if s.strip()] if isinstance(damage_immunities, str) else res_imm.get("damage_immunities", [])
    condition_immunities = res_imm.get("condition_immunities_display", "")
    condition_immunities = [s.strip() for s in condition_immunities.split(",") if s.strip()] if isinstance(condition_immunities, str) else res_imm.get("condition_immunities", [])

    # ID 生成
    monster_id = key.replace("srd-2024_", "").replace("wotc-srd_", "")

    # 描述 - 从 markdown 里提取风味描述（如果有的话）
    description = ""

    # CR 数字转换
    cr = src.get("challenge_rating", 0)

    # 标签
    tags = [type_obj.get("name", "").lower() if isinstance(type_obj, dict) else str(type_obj).lower()]
    if cr <= 1:
        tags.append("低等级")
    if cr >= 10:
        tags.append("高等级")
    if src.get("alignment") and "evil" in src["alignment"].lower():
        tags.append("邪恶")

    # 若映射到中文，则中文为主、英文为 name_en；并保留原英文名作为别名便于搜索
    aliases = []
    if cn_name and cn_name != name:
        display_name = cn_name
        name_en = name
        aliases.append(name.lower())
    else:
        display_name = name
        name_en = name

    result = {
        "id": monster_id,
        "name": display_name,
        "name_en": name_en,
        "aliases": aliases,
        "size": size_obj.get("name", "") if isinstance(size_obj, dict) else str(size_obj),
        "type": type_obj.get("name", "") if isinstance(type_obj, dict) else str(type_obj),
        "alignment": src.get("alignment", ""),
        "cr": cr,
        "challenge": str(cr),
        "xp": src.get("experience_points", 0),
        "source": "SRD 2024",
        "stats": {
            "hp": f"{src.get('hit_points', 0)} ({src.get('hit_dice', '')})",
            "hp_average": src.get("hit_points", 0),
            "ac": src.get("armor_class", 10),
            "ac_source": src.get("armor_detail", ""),
            "speed": speed_obj.get("walk", 30),
            "speed_special": speed_special,
        },
        "abilities": abilities,
        "proficiency_bonus": src.get("proficiency_bonus") or 2,
        "saving_throws": src.get("saving_throws_all", {}),
        "skills": skills,
        "damage_resistances": damage_resistances if isinstance(damage_resistances, list) else [],
        "damage_immunities": damage_immunities if isinstance(damage_immunities, list) else [],
        "condition_immunities": condition_immunities if isinstance(condition_immunities, list) else [],
        "senses": senses,
        "languages": languages,
        "attacks": attacks,
        "special_abilities": special_abilities,
        "legendary_actions": legendary_actions,
        "equipment": [],
        "description": description,
        "tags": [t for t in tags if t],
        "srd_key": key,
    }
    return result


def _action_type_label(action_type: str) -> str:
    labels = {
        "ACTION": "动作",
        "BONUS_ACTION": "附赠动作",
        "REACTION": "反应",
        "MYTHIC_ACTION": "神话动作",
    }
    return labels.get(action_type, action_type or "动作")


def import_creatures_from_search(bestiary, search_query: str = "",
                                 cr_min: float = None, cr_max: float = None,
                                 type_filter: str = "",
                                 overwrite: bool = False,
                                 limit: int = 100) -> Dict[str, Any]:
    """通过 dnd-rules 搜索并导入怪物

    Args:
        bestiary: Bestiary 实例
        search_query: 搜索关键词（空=全部）
        cr_min/cr_max: CR 范围
        type_filter: 类型过滤
        overwrite: 已存在的是否覆盖
        limit: 最多导入多少
    """
    # 注意：此函数需要在能调用 MCP 工具的环境中运行
    # 这里只提供转换逻辑，实际调用由外部脚本完成
    pass
