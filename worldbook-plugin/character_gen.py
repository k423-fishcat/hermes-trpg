"""角色卡生成器（DnD 5e）

从 dnd-rules 职业数据 + 种族模板快速生成角色卡，存入 state.player。

支持：
- 职业：从 dnd-rules 拿数据
- 种族：内置常见种族模板
- 属性：标准分配 / 自定义
- 背景：简单模板
"""

import json
from typing import Any, Dict, List, Optional


# 内置种族模板（DnD 5e 2024 SRD）
RACE_TEMPLATES = {
    "human": {
        "id": "human",
        "name": "人类",
        "name_en": "Human",
        "size": "中等",
        "speed": 30,
        "ability_bonus": {"all": 1},  # 全属性 +1
        "traits": [
            {"name": "多才多艺", "desc": "所有属性+1"},
            {"name": "人类专长", "desc": "获得1个1级专长"},
        ],
        "languages": ["通用语", "任选一种"],
    },
    "dwarf": {
        "id": "dwarf",
        "name": "矮人",
        "name_en": "Dwarf",
        "size": "中等",
        "speed": 25,
        "ability_bonus": {"con": 2},
        "traits": [
            {"name": "黑暗视觉", "desc": "60尺黑暗视觉"},
            {"name": "矮人韧性", "desc": "对抗毒素豁免有优势，毒素伤害抗性"},
            {"name": "石之狡黠", "desc": "与石头相关的历史检定加双倍熟练加值"},
            {"name": "矮人战斗训练", "desc": "熟练手斧、战锤、轻锤、战镐"},
            {"name": "工匠工具", "desc": "熟练一种工匠工具"},
        ],
        "languages": ["通用语", "矮人语"],
    },
    "elf": {
        "id": "elf",
        "name": "精灵",
        "name_en": "Elf",
        "size": "中等",
        "speed": 30,
        "ability_bonus": {"dex": 2},
        "traits": [
            {"name": "黑暗视觉", "desc": "60尺黑暗视觉"},
            {"name": "敏锐感官", "desc": "察觉熟练"},
            {"name": "精灵血统", "desc": "对抗魅惑豁免有优势，魔法无法让你入睡"},
            {"name": "冥想", "desc": "4小时冥想代替8小时睡眠"},
            {"name": "精灵步法", "desc": "体操熟练"},
        ],
        "languages": ["通用语", "精灵语"],
    },
    "halfling": {
        "id": "halfling",
        "name": "半身人",
        "name_en": "Halfling",
        "size": "小型",
        "speed": 25,
        "ability_bonus": {"dex": 2},
        "traits": [
            {"name": "幸运", "desc": "攻击骰/属性骰/豁免骰出1可以重投"},
            {"name": "勇敢", "desc": "对抗恐惧豁免有优势"},
            {"name": "半身人灵活", "desc": "可以穿过比自己大的生物空间"},
        ],
        "languages": ["通用语", "半身人语"],
    },
}

# 技能中英对照
SKILL_NAMES = {
    "Acrobatics": "体操", "Animal Handling": "驯兽", "Arcana": "奥秘",
    "Athletics": "运动", "Deception": "欺瞒", "History": "历史",
    "Insight": "洞悉", "Intimidation": "威吓", "Investigation": "调查",
    "Medicine": "医药", "Nature": "自然", "Perception": "察觉",
    "Performance": "表演", "Persuasion": "游说", "Religion": "宗教",
    "Sleight of Hand": "巧手", "Stealth": "隐匿", "Survival": "生存",
}

def _cn_skill(name: str) -> str:
    """技能名转中文"""
    return SKILL_NAMES.get(name.strip(), name.strip())

# 背景模板
BACKGROUND_TEMPLATES = {
    "acolyte": {"name": "侍僧", "skills": ["洞悉", "宗教"], "languages": 2},
    "criminal": {"name": "罪犯", "skills": ["欺瞒", "潜行"], "languages": 0},
    "folk_hero": {"name": "民间英雄", "skills": ["驯兽", "生存"], "languages": 0},
    "noble": {"name": "贵族", "skills": ["历史", "游说"], "languages": 1},
    "sage": {"name": "学者", "skills": ["奥秘", "历史"], "languages": 2},
    "soldier": {"name": "士兵", "skills": ["运动", "威吓"], "languages": 0},
}

# 标准属性分配（Standard Array）
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]


def mod(score: int) -> int:
    """属性调整值"""
    return (score - 10) // 2


def generate_character(
    name: str,
    class_key: str,
    race_id: str = "human",
    level: int = 1,
    ability_scores: Dict[str, int] = None,
    background: str = "soldier",
    class_data: Dict = None,
) -> Dict[str, Any]:
    """生成角色卡

    Args:
        name: 角色名
        class_key: 职业 key 或名称（dnd-rules 的）
        race_id: 种族 ID（内置模板）
        level: 等级（1-20）
        ability_scores: 属性字典 {str,dex,con,int,wis,cha}，None则用标准分配
        background: 背景 ID
        class_data: dnd-rules 返回的职业结构化数据（如果有的话直接用）

    Returns:
        角色卡字典
    """
    race = RACE_TEMPLATES.get(race_id, RACE_TEMPLATES["human"])

    # 属性
    if ability_scores is None:
        ability_scores = {
            "str": 15, "dex": 14, "con": 13, "int": 12, "wis": 10, "cha": 8
        }

    # 加种族加值
    final_abilities = dict(ability_scores)
    ab_bonus = race.get("ability_bonus", {})
    if "all" in ab_bonus:
        for k in final_abilities:
            final_abilities[k] += ab_bonus["all"]
    else:
        for k, v in ab_bonus.items():
            final_abilities[k] = final_abilities.get(k, 10) + v

    # 从职业数据提取关键信息
    hp_die = 10
    skill_choices = []
    saving_throws = []
    armor_profs = []
    weapon_profs = []
    class_name = class_key
    primary_ability = "力量"

    if class_data:
        class_name = class_data.get("name", class_key)
        hd = class_data.get("hit_dice", "d10")
        try:
            hp_die = int(hd.lower().replace("d", ""))
        except:
            hp_die = 10

        # 豁免熟练
        st_list = class_data.get("saving_throws", [])
        saving_throws = [s.get("name", "") for s in st_list]

        # 从 core traits 里找技能熟练
        for feat in class_data.get("features", []):
            if feat.get("feature_type") == "CORE_TRAITS_TABLE":
                desc = feat.get("desc", "")
                # 粗略提取
                import re
                sk_match = re.search(r'Skill Proficiencies.*?:\s*(.*?)(\n|\|)', desc, re.I)
                if sk_match:
                    skill_text = sk_match.group(1)
                    skill_choices = [s.strip() for s in re.split(r'[,;，]', skill_text) if s.strip()]
                break

    # 1级 HP = 满骰 + 体质调整
    max_hp = hp_die + mod(final_abilities["con"])

    # 熟练加值
    if level <= 4:
        prof_bonus = 2
    elif level <= 8:
        prof_bonus = 3
    elif level <= 12:
        prof_bonus = 4
    elif level <= 16:
        prof_bonus = 5
    else:
        prof_bonus = 6

    # AC（无甲时默认 10 + 敏调）
    base_ac = 10 + mod(final_abilities["dex"])

    # 背景技能
    bg = BACKGROUND_TEMPLATES.get(background, BACKGROUND_TEMPLATES["soldier"])
    bg_skills = bg.get("skills", [])

    # 初始技能（从职业可选里自动选几个典型的）
    # 简化：选前两个有属性加值的
    class_skills_proficient = []
    if skill_choices:
        class_skills_proficient = [_cn_skill(s) for s in skill_choices[:2]]

    all_skills = list(set(class_skills_proficient + bg_skills))

    character = {
        "name": name,
        "class": class_name,
        "class_key": class_key,
        "race": race["name"],
        "race_id": race_id,
        "background": bg.get("name", background),
        "level": level,
        "experience": 0,
        "hp": {
            "max": max_hp,
            "current": max_hp,
            "temp": 0,
            "hit_dice": f"1d{hp_die}",
            "hit_dice_total": level,
            "hit_dice_used": 0,
        },
        "ac": base_ac,
        "speed": race.get("speed", 30),
        "size": race.get("size", "中等"),
        "proficiency_bonus": prof_bonus,
        "abilities": {
            "str": final_abilities["str"],
            "dex": final_abilities["dex"],
            "con": final_abilities["con"],
            "int": final_abilities["int"],
            "wis": final_abilities["wis"],
            "cha": final_abilities["cha"],
        },
        "ability_modifiers": {
            "str": mod(final_abilities["str"]),
            "dex": mod(final_abilities["dex"]),
            "con": mod(final_abilities["con"]),
            "int": mod(final_abilities["int"]),
            "wis": mod(final_abilities["wis"]),
            "cha": mod(final_abilities["cha"]),
        },
        "saving_throws": saving_throws,
        "skills_proficient": all_skills,
        "armor_proficiencies": armor_profs,
        "weapon_proficiencies": weapon_profs,
        "languages": list(race.get("languages", ["通用语"])),
        "racial_traits": race.get("traits", []),
        "class_features": [],
        "equipment": [],
        "gold": 0,
        "conditions": [],
    }

    # 从职业数据提取等级特性
    if class_data:
        features = []
        for feat in class_data.get("features", []):
            ftype = feat.get("feature_type", "")
            if ftype in ("CLASS_LEVEL_FEATURE", "CORE_TRAITS_TABLE"):
                gained = feat.get("gained_at", [])
                min_level = min((g.get("level", 99) for g in gained), default=99)
                if min_level <= level:
                    features.append({
                        "name": feat.get("name", ""),
                        "desc": feat.get("desc", "")[:300],
                        "level": min_level,
                    })
        character["class_features"] = sorted(features, key=lambda x: x.get("level", 0))

    return character


def format_character_sheet(char: Dict) -> str:
    """格式化角色卡为可阅读文本"""
    lines = [
        f"{'═' * 40}",
        f"  {char['name']}",
        f"  {char['race']} {char['class']}  Lv.{char['level']}",
        f"{'═' * 40}",
        "",
        f"❤️ HP: {char['hp']['current']}/{char['hp']['max']}"
        f" (骰: {char['hp']['hit_dice']}×{char['hp']['hit_dice_total']})",
        f"🛡️ AC: {char['ac']}   🏃 速度: {char['speed']}尺",
        f"⭐ 熟练加值: +{char['proficiency_bonus']}",
        "",
        "┌───────┬────┬────┬────┬────┬────┬────┐",
        "│  属性  │ STR│ DEX│ CON│ INT│ WIS│ CHA│",
        "├───────┼────┼────┼────┼────┼────┼────┤",
        f"│  数值  │ {char['abilities']['str']:>3} │ {char['abilities']['dex']:>3} │ "
        f"{char['abilities']['con']:>3} │ {char['abilities']['int']:>3} │ "
        f"{char['abilities']['wis']:>3} │ {char['abilities']['cha']:>3} │",
        f"│ 调整值 │ {char['ability_modifiers']['str']:>+3d} │ "
        f"{char['ability_modifiers']['dex']:>+3d} │ {char['ability_modifiers']['con']:>+3d} │ "
        f"{char['ability_modifiers']['int']:>+3d} │ {char['ability_modifiers']['wis']:>+3d} │ "
        f"{char['ability_modifiers']['cha']:>+3d} │",
        "└───────┴────┴────┴────┴────┴────┴────┘",
        "",
        f"豁免熟练: {', '.join(char['saving_throws']) if char['saving_throws'] else '无'}",
        f"技能熟练: {', '.join(char['skills_proficient']) if char['skills_proficient'] else '无'}",
        f"语言: {', '.join(char['languages'])}",
        "",
        f"种族特性 ({len(char['racial_traits'])}):",
    ]
    for t in char['racial_traits']:
        lines.append(f"  • {t['name']}: {t['desc']}")

    if char.get('class_features'):
        lines.append("")
        lines.append(f"职业特性 ({len(char['class_features'])}):")
        for f in char['class_features']:
            lines.append(f"  • Lv{f['level']} {f['name']}")

    lines.append("")
    lines.append(f"背景: {char['background']}")

    return "\n".join(lines)


def list_races() -> List[Dict]:
    """列出所有内置种族"""
    return [{"id": k, "name": v["name"], "size": v["size"], "speed": v["speed"]}
            for k, v in RACE_TEMPLATES.items()]


def list_backgrounds() -> List[Dict]:
    """列出所有背景"""
    return [{"id": k, "name": v["name"], "skills": v["skills"]}
            for k, v in BACKGROUND_TEMPLATES.items()]
