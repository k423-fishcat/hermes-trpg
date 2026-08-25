"""D&D 5e 角色卡数据模型 + 管理器

完整角色卡：种族/职业/属性/技能熟练/豁免熟练/专长/装备/法术/背景
角色卡是"静态 build"，状态是"动态运行时数据"。
角色卡用于初始化状态、计算检定加值、判断熟练项等。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import atomic_write_json
from .dice import roll_hit_dice


# DnD 5e 技能列表（中文）
SKILLS = {
    "athletics": {"name": "运动", "ability": "str"},
    "acrobatics": {"name": "体操", "ability": "dex"},
    "sleight_of_hand": {"name": "巧手", "ability": "dex"},
    "stealth": {"name": "隐匿", "ability": "dex"},
    "arcana": {"name": "奥秘", "ability": "int"},
    "history": {"name": "历史", "ability": "int"},
    "investigation": {"name": "调查", "ability": "int"},
    "nature": {"name": "自然", "ability": "int"},
    "religion": {"name": "宗教", "ability": "int"},
    "animal_handling": {"name": "驯兽", "ability": "wis"},
    "insight": {"name": "洞悉", "ability": "wis"},
    "medicine": {"name": "医药", "ability": "wis"},
    "perception": {"name": "察觉", "ability": "wis"},
    "survival": {"name": "生存", "ability": "wis"},
    "deception": {"name": "欺瞒", "ability": "cha"},
    "intimidation": {"name": "威吓", "ability": "cha"},
    "performance": {"name": "表演", "ability": "cha"},
    "persuasion": {"name": "游说", "ability": "cha"},
}

# 属性名映射
ABILITY_NAMES = {
    "str": "力量", "dex": "敏捷", "con": "体质",
    "int": "智力", "wis": "感知", "cha": "魅力",
}

# 熟练加值表（按等级）
PROFICIENCY_BY_LEVEL = {
    1: 2, 2: 2, 3: 2, 4: 2,
    5: 3, 6: 3, 7: 3, 8: 3,
    9: 4, 10: 4, 11: 4, 12: 4,
    13: 5, 14: 5, 15: 5, 16: 5,
    17: 6, 18: 6, 19: 6, 20: 6,
}

# XP 阈值（按等级）
XP_THRESHOLDS = {
    1: 0, 2: 300, 3: 900, 4: 2700, 5: 6500,
    6: 14000, 7: 23000, 8: 34000, 9: 48000, 10: 64000,
    11: 85000, 12: 100000, 13: 120000, 14: 140000, 15: 165000,
    16: 195000, 17: 225000, 18: 265000, 19: 305000, 20: 355000,
}


@dataclass
class CharacterSheet:
    """D&D 5e 角色卡"""
    name: str = ""
    race: str = ""
    class_name: str = ""
    subclass: str = ""
    background: str = ""
    alignment: str = ""
    level: int = 1
    xp: int = 0

    # 属性
    abilities: Dict[str, int] = field(default_factory=lambda: {
        "str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10,
    })

    # 熟练
    skill_proficiencies: List[str] = field(default_factory=list)  # 技能 key 列表
    save_proficiencies: List[str] = field(default_factory=list)   # 豁免属性 key 列表
    tool_proficiencies: List[str] = field(default_factory=list)   # 工具熟练
    skill_expertise: List[str] = field(default_factory=list)      # 技能专长（双倍熟练）
    other_languages: List[str] = field(default_factory=list)

    # 专长 / 特性
    feats: List[Dict[str, Any]] = field(default_factory=list)    # [{name, desc, effect}]
    features: List[Dict[str, Any]] = field(default_factory=list) # 职业/种族特性

    # 战斗
    hp_max: int = 0
    hit_dice_total: str = "1d8"  # 如 "2d10"
    ac_base: int = 10
    speed: int = 30

    # 装备
    equipment: List[Dict[str, Any]] = field(default_factory=list)
    weapons: List[Dict[str, Any]] = field(default_factory=list)
    armor: Optional[Dict[str, Any]] = None
    shield: bool = False

    # 法术
    spellcasting_ability: str = "int"  # 施法属性 key
    spells_known: List[str] = field(default_factory=list)
    spells_prepared: List[str] = field(default_factory=list)
    spell_slots_max: Dict[str, int] = field(default_factory=dict)  # { "1": 2, "2": 1 }

    # 金钱
    gold: int = 0

    # 背景故事
    backstory: str = ""
    personality_traits: str = ""
    ideals: str = ""
    bonds: str = ""
    flaws: str = ""

    # 元信息
    player_name: str = ""  # 玩家名字（如果不是单人团）
    notes: str = ""

    # ----------------------------------------------------------------
    # 计算属性
    # ----------------------------------------------------------------

    @property
    def proficiency_bonus(self) -> int:
        """熟练加值"""
        return PROFICIENCY_BY_LEVEL.get(self.level, 2)

    def ability_mod(self, ability_key: str) -> int:
        """属性调整值"""
        score = self.abilities.get(ability_key, 10)
        return (score - 10) // 2

    def skill_bonus(self, skill_key: str) -> int:
        """技能加值 = 属性调整 + 熟练（如果熟练）+ 专长双倍（如果有）"""
        info = SKILLS.get(skill_key)
        if not info:
            return 0
        ab = info["ability"]
        base = self.ability_mod(ab)

        if skill_key in self.skill_expertise:
            base += self.proficiency_bonus * 2
        elif skill_key in self.skill_proficiencies:
            base += self.proficiency_bonus

        return base

    def save_bonus(self, ability_key: str) -> int:
        """豁免加值 = 属性调整 + 熟练（如果豁免熟练）"""
        base = self.ability_mod(ability_key)
        if ability_key in self.save_proficiencies:
            base += self.proficiency_bonus
        return base

    @property
    def ac(self) -> int:
        """计算 AC（基础 + 敏捷调整 + 护甲加值 + 盾牌）

        D&D 5e：护甲与盾牌加值叠加。
        """
        base = self.ac_base
        shield_bonus = 2 if self.shield else 0
        if self.armor:
            # 穿甲时，按护甲类型计算
            armor_type = self.armor.get("type", "light")
            armor_ac = self.armor.get("ac", 11)
            if armor_type == "heavy":
                return armor_ac + shield_bonus
            elif armor_type == "medium":
                return armor_ac + min(self.ability_mod("dex"), 2) + shield_bonus
            else:  # light
                return armor_ac + self.ability_mod("dex") + shield_bonus
        return base + self.ability_mod("dex") + shield_bonus

    @property
    def passive_perception(self) -> int:
        """被动感知 = 10 + 察觉加值"""
        return 10 + self.skill_bonus("perception")

    @property
    def next_level_xp(self) -> int:
        """下一级所需 XP"""
        return XP_THRESHOLDS.get(self.level + 1, 355000)

    def check_level_up(self) -> bool:
        """是否可以升级"""
        return self.xp >= self.next_level_xp and self.level < 20

    def level_up(self, hp_roll: int = None,
                 ability_increases: List[str] = None) -> Dict[str, Any]:
        """执行升级

        Args:
            hp_roll: HP 掷骰结果（不提供则自动掷）
            ability_increases: 属性提升列表（在属性提升等级时有效，如 4/8/12/16/19 级）

        Returns:
            升级结果字典
        """
        if not self.check_level_up():
            return {"success": False, "error": "XP 不足，无法升级"}

        old_level = self.level
        self.level += 1

        # 熟练加值
        new_prof = 2 + (self.level - 1) // 4

        # HP 增加
        con_mod = self.ability_mod("con")
        hd_sides = int(self.hit_dice_total.split('d')[1]) if 'd' in self.hit_dice_total else 8

        if hp_roll is not None:
            roll = max(1, min(hd_sides, hp_roll))
        else:
            roll = roll_hit_dice(hd_sides)
        hp_added = max(1, roll + con_mod)

        self.hp_max += hp_added

        # 命中骰 +1
        hd_num = int(self.hit_dice_total.split('d')[0]) if 'd' in self.hit_dice_total else 1
        self.hit_dice_total = f"{hd_num + 1}d{hd_sides}"

        # 属性提升（每 4 级一次：4/8/12/16/19）
        ability_levels = [4, 8, 12, 16, 19]
        ability_bumped = []
        if self.level in ability_levels and ability_increases:
            for ab in ability_increases[:2]:
                ab = ab.lower()
                if ab in self.abilities:
                    self.abilities[ab] += 1
                    ability_bumped.append(ab)

        return {
            "success": True,
            "old_level": old_level,
            "new_level": self.level,
            "hp_added": hp_added,
            "hp_roll": roll,
            "hit_dice": self.hit_dice_total,
            "proficiency_bonus": new_prof,
            "ability_increases": ability_bumped,
        }

    # ----------------------------------------------------------------
    # 序列化
    # ----------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "race": self.race,
            "class": self.class_name,
            "subclass": self.subclass,
            "background": self.background,
            "alignment": self.alignment,
            "level": self.level,
            "xp": self.xp,
            "abilities": self.abilities,
            "skill_proficiencies": self.skill_proficiencies,
            "save_proficiencies": self.save_proficiencies,
            "tool_proficiencies": self.tool_proficiencies,
            "skill_expertise": self.skill_expertise,
            "other_languages": self.other_languages,
            "feats": self.feats,
            "features": self.features,
            "hp_max": self.hp_max,
            "hit_dice_total": self.hit_dice_total,
            "ac_base": self.ac_base,
            "speed": self.speed,
            "equipment": self.equipment,
            "weapons": self.weapons,
            "armor": self.armor,
            "shield": self.shield,
            "spellcasting_ability": self.spellcasting_ability,
            "spells_known": self.spells_known,
            "spells_prepared": self.spells_prepared,
            "spell_slots_max": self.spell_slots_max,
            "gold": self.gold,
            "backstory": self.backstory,
            "personality_traits": self.personality_traits,
            "ideals": self.ideals,
            "bonds": self.bonds,
            "flaws": self.flaws,
            "player_name": self.player_name,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterSheet":
        char = cls(
            name=data.get("name", ""),
            race=data.get("race", ""),
            class_name=data.get("class", data.get("class_name", "")),
            subclass=data.get("subclass", ""),
            background=data.get("background", ""),
            alignment=data.get("alignment", ""),
            level=data.get("level", 1),
            xp=data.get("xp", 0),
            hp_max=data.get("hp_max", 0),
            hit_dice_total=data.get("hit_dice_total", "1d8"),
            ac_base=data.get("ac_base", 10),
            speed=data.get("speed", 30),
            spellcasting_ability=data.get("spellcasting_ability", "int"),
            gold=data.get("gold", 0),
            backstory=data.get("backstory", ""),
            personality_traits=data.get("personality_traits", ""),
            ideals=data.get("ideals", ""),
            bonds=data.get("bonds", ""),
            flaws=data.get("flaws", ""),
            player_name=data.get("player_name", ""),
            notes=data.get("notes", ""),
        )
        if data.get("abilities"):
            char.abilities.update(data["abilities"])
        char.skill_proficiencies = list(data.get("skill_proficiencies", []))
        char.save_proficiencies = list(data.get("save_proficiencies", []))
        char.tool_proficiencies = list(data.get("tool_proficiencies", []))
        char.skill_expertise = list(data.get("skill_expertise", []))
        char.other_languages = list(data.get("other_languages", []))
        char.feats = list(data.get("feats", []))
        char.features = list(data.get("features", []))
        char.equipment = list(data.get("equipment", []))
        char.weapons = list(data.get("weapons", []))
        char.armor = data.get("armor")
        char.shield = data.get("shield", False)
        char.spells_known = list(data.get("spells_known", []))
        char.spells_prepared = list(data.get("spells_prepared", []))
        char.spell_slots_max = dict(data.get("spell_slots_max", {}))
        return char


class CharacterManager:
    """角色卡管理器

    负责角色卡的存储、加载、和状态系统的交互。
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.chars_dir = self.data_dir / "characters"
        self.chars_dir.mkdir(parents=True, exist_ok=True)

    def list_characters(self) -> List[Dict[str, Any]]:
        """列出所有角色卡"""
        import logging
        logger = logging.getLogger(__name__)
        result = []
        for f in sorted(self.chars_dir.glob("*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                result.append({
                    "id": f.stem,
                    "name": data.get("name", f.stem),
                    "class": data.get("class", ""),
                    "race": data.get("race", ""),
                    "level": data.get("level", 1),
                })
            except json.JSONDecodeError as e:
                logger.error(
                    f"[characters] 角色卡 JSON 损坏: {f} ({e})。"
                    f"该角色将不会出现在列表中。请检查或删除该文件。"
                )
            except Exception as e:
                logger.error(f"[characters] 加载角色卡失败: {f} ({type(e).__name__}: {e})")
        return result

    def load_character(self, char_id: str) -> Optional[CharacterSheet]:
        """加载角色卡"""
        path = self.chars_dir / f"{char_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CharacterSheet.from_dict(data)

    def save_character(self, char_id: str, char: CharacterSheet) -> str:
        """保存角色卡（原子写入）"""
        path = self.chars_dir / f"{char_id}.json"
        atomic_write_json(path, char.to_dict())
        return str(path)

    def delete_character(self, char_id: str) -> bool:
        """删除角色卡"""
        path = self.chars_dir / f"{char_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def apply_to_state(self, char: CharacterSheet, state_mgr) -> Dict[str, Any]:
        """将角色卡数据应用到玩家状态（初始化/刷新）

        把角色卡的静态 build 数据写入 state 的 player 部分，
        动态数据（HP 等）保留已有值或初始化为最大值。
        """
        player = state_mgr.get("player") or {}

        # 基础信息
        player["name"] = char.name
        player["class"] = char.class_name
        player["race"] = char.race
        player["level"] = char.level
        player["xp"] = char.xp
        player["alignment"] = char.alignment
        player["gold"] = char.gold
        player["proficiency_bonus"] = char.proficiency_bonus
        player["ac"] = char.ac
        player["speed"] = char.speed
        player["passive_perception"] = char.passive_perception

        # 属性
        player["abilities"] = dict(char.abilities)

        # HP（如果当前没设就设为满）
        hp = player.setdefault("hp", {})
        hp["max"] = char.hp_max
        if not hp.get("current"):
            hp["current"] = char.hp_max
        hp["temp"] = hp.get("temp", 0)

        # 命中骰
        hit_dice = player.setdefault("hit_dice", {})
        hit_dice["total"] = char.hit_dice_total
        if "used" not in hit_dice:
            hit_dice["used"] = 0

        # 技能熟练（供检定引擎用）
        # 用 dict 形态 {技能名: True}，兼容 _rules_dnd5e.get_skill_modifier 的
        # skills.items() 遍历（若是 list 会 AttributeError 崩）。
        player["skills"] = {}
        for sk_key in char.skill_proficiencies:
            if sk_key in SKILLS:
                player["skills"][SKILLS[sk_key]["name"]] = True
            else:
                player["skills"][sk_key] = True
        # 存详细技能数据
        player["skill_data"] = {
            "proficient": char.skill_proficiencies,
            "expertise": char.skill_expertise,
            "save_proficient": char.save_proficiencies,
        }

        # 法术位
        if char.spell_slots_max:
            spell_slots = player.setdefault("spell_slots", {})
            for level, max_val in char.spell_slots_max.items():
                if level not in spell_slots:
                    spell_slots[level] = max_val

        # 死亡豁免
        player.setdefault("death_saves", {"successes": 0, "failures": 0})

        # 灵感
        player.setdefault("inspiration", False)

        # 语言
        langs = player.setdefault("languages", ["通用语"])
        for lang in char.other_languages:
            if lang not in langs:
                langs.append(lang)

        # 背包（从装备初始化）
        inventory = player.setdefault("inventory", [])
        for item in char.equipment:
            if item.get("name") and not any(i.get("name") == item["name"] for i in inventory):
                inventory.append(item)

        state_mgr.update(
            {"player": player},
            reason=f"角色卡应用：{char.name}",
            actor="系统"
        )
        return {
            "success": True,
            "character": char.name,
            "hp": f"{player['hp']['current']}/{player['hp']['max']}",
            "ac": player["ac"],
            "level": char.level,
        }

    def create_from_sheet_data(self, char_id: str, sheet_data: Dict[str, Any],
                                state_mgr=None) -> CharacterSheet:
        """从角色卡数据创建并保存角色卡，可选应用到状态"""
        char = CharacterSheet.from_dict(sheet_data)
        self.save_character(char_id, char)
        if state_mgr:
            self.apply_to_state(char, state_mgr)
        return char
