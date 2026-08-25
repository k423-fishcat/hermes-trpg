"""法术系统（Spell System）

管理玩家的法术：已知法术、准备法术、法术位、施放、专注。

设计原则：
- 法术详细数据（描述/范围/成分等）从 dnd-rules MCP 查询，不存本地
- 本地只存：已知法术 ID 列表、准备法术 ID 列表、法术位剩余数量
- 施放时消耗法术位，应用效果（伤害/治疗/状态）

D&D 5e 施法者类型（Player's Handbook 2014, p. 53）：
- 已知型（Known casters）—— 无需准备，已知即能施：
    * 术士 Sorcerer
    * 吟游诗人 Bard
    * 邪术师 Warlock
- 准备型（Prepared casters）—— 每日从已知/职业法术列表中选法术准备：
    * 牧师 Cleric（从全职业法术列表准备）
    * 德鲁伊 Druid（从全职业法术列表准备）
    * 圣武士 Paladin（从全职业法术列表准备）
    * 法师 Wizard（从法术书准备）
- 游侠 Ranger —— 准备型，但法术数量受限（半职业等级，向上取整）
- 邪术师 Warlock —— 已知型（已知即用），但有特殊 Pact Magic 法术位（全部同等最高级）

施法者类型的派别见 _is_known_caster / _is_prepared_caster。

法术攻击加值 = 施法属性调整 + 熟练加值
法术豁免 DC = 8 + 施法属性调整 + 熟练加值
"""

import time
from typing import Any, Dict, List, Optional

from .dice import roll_healing, roll_d20
from .domain.spells import (
    is_known_caster as _is_known_caster,
    is_prepared_caster as _is_prepared_caster,
    check_can_cast as _check_can_cast,
    find_slot as _find_slot_from_domain,
)


# 旧导入路径仍可被外部访问（向后兼容）
KNOWN_CASTERS = {
    # 中文
    "术士", "吟游诗人", "邪术师",
    # 英文 / 拼音
    "sorcerer", "bard", "warlock",
}

PREPARED_CASTERS = {
    # 中文
    "牧师", "德鲁伊", "圣武士", "法师", "游侠",
    # 英文 / 拼音
    "cleric", "druid", "paladin", "wizard", "ranger",
}


class SpellManager:
    """法术管理器"""

    def __init__(self, state_mgr):
        self.state = state_mgr

    # ----------------------------------------------------------------
    # 基础信息
    # ----------------------------------------------------------------

    def get_spell_info(self) -> Dict[str, Any]:
        """获取玩家法术信息摘要"""
        player = self.state.get("player") or {}

        spellcasting_ability = player.get("spellcasting_ability", "int")
        ability_score = player.get("abilities", {}).get(spellcasting_ability, 10)
        ability_mod = (ability_score - 10) // 2
        prof_bonus = player.get("proficiency_bonus", 2)

        attack_bonus = ability_mod + prof_bonus
        save_dc = 8 + ability_mod + prof_bonus

        spells_known = player.get("spells_known", [])
        spells_prepared = player.get("spells_prepared", [])
        spell_slots = player.get("spell_slots", {})
        spell_slots_max = player.get("spell_slots_max", {})

        return {
            "spellcasting_ability": spellcasting_ability,
            "ability_score": ability_score,
            "ability_modifier": ability_mod,
            "proficiency_bonus": prof_bonus,
            "spell_attack_bonus": attack_bonus,
            "spell_save_dc": save_dc,
            "spells_known_count": len(spells_known),
            "spells_prepared_count": len(spells_prepared),
            "spell_slots": spell_slots,
            "spell_slots_max": spell_slots_max,
            "concentration": player.get("concentration", None),
        }

    # ----------------------------------------------------------------
    # 已知法术
    # ----------------------------------------------------------------

    def list_known(self) -> List[str]:
        """已知法术列表"""
        player = self.state.get("player") or {}
        return player.get("spells_known", [])

    def add_known(self, spell_id: str, spell_name: str = "") -> Dict[str, Any]:
        """学习一个新法术"""
        player = self.state.get("player") or {}
        known = player.setdefault("spells_known", [])

        if spell_id in known:
            return {"success": False, "error": f"已经学会 {spell_name or spell_id} 了"}

        known.append(spell_id)
        self.state.update(
            {"player": player},
            reason=f"学习法术: {spell_name or spell_id}",
            actor="系统"
        )
        return {"success": True, "spell_id": spell_id, "name": spell_name or spell_id}

    def remove_known(self, spell_id: str) -> Dict[str, Any]:
        """遗忘一个法术（已知型：直接删除；准备型：从 known+prepared 同步移除）"""
        player = self.state.get("player") or {}
        class_name = player.get("class", "")
        known = player.get("spells_known", [])

        if spell_id not in known:
            return {"success": False, "error": f"未知法术: {spell_id}"}

        known.remove(spell_id)
        # 如果是准备型施法者，同步从 prepared 移除
        if _is_prepared_caster(class_name):
            prepared = player.get("spells_prepared", [])
            if spell_id in prepared:
                prepared.remove(spell_id)

        self.state.update(
            {"player": player},
            reason=f"遗忘法术: {spell_id}",
            actor="系统"
        )
        return {"success": True, "spell_id": spell_id}

    # ----------------------------------------------------------------
    # 准备法术
    # ----------------------------------------------------------------

    def list_prepared(self) -> List[str]:
        """准备的法术列表"""
        player = self.state.get("player") or {}
        return player.get("spells_prepared", [])

    def prepare(self, spell_id: str) -> Dict[str, Any]:
        """准备一个法术（仅准备型施法者需要：牧师/德鲁伊/圣武士/法师/游侠）"""
        player = self.state.get("player") or {}
        class_name = player.get("class", "")
        if _is_known_caster(class_name):
            return {
                "success": False,
                "error": f"{class_name}是已知型施法者，无需准备（已知即能施放）",
            }

        known = player.get("spells_known", [])
        prepared = player.setdefault("spells_prepared", [])

        if spell_id not in known:
            return {"success": False, "error": f"你不会这个法术: {spell_id}"}
        if spell_id in prepared:
            return {"success": False, "error": f"已经准备了: {spell_id}"}

        prepared.append(spell_id)
        self.state.update(
            {"player": player},
            reason=f"准备法术: {spell_id}",
            actor="玩家"
        )
        return {"success": True, "spell_id": spell_id, "prepared_count": len(prepared)}

    def unprepare(self, spell_id: str) -> Dict[str, Any]:
        """取消准备"""
        player = self.state.get("player") or {}
        prepared = player.get("spells_prepared", [])

        if spell_id not in prepared:
            return {"success": False, "error": f"未准备此法术: {spell_id}"}

        prepared.remove(spell_id)
        self.state.update(
            {"player": player},
            reason=f"取消准备: {spell_id}",
            actor="玩家"
        )
        return {"success": True, "spell_id": spell_id}

    # ----------------------------------------------------------------
    # 法术位
    # ----------------------------------------------------------------

    def get_slots(self) -> Dict[str, Dict]:
        """法术位状态"""
        player = self.state.get("player") or {}
        current = player.get("spell_slots", {})
        max_slots = player.get("spell_slots_max", {})
        result = {}
        for level in sorted(set(list(current.keys()) + list(max_slots.keys())),
                            key=lambda x: int(x) if str(x).isdigit() else 99):
            result[str(level)] = {
                "current": current.get(level, 0),
                "max": max_slots.get(level, 0),
            }
        return result

    def set_max_slots(self, slots: Dict[str, int]) -> Dict[str, Any]:
        """设置法术位上限（升级时用）"""
        player = self.state.get("player") or {}
        player["spell_slots_max"] = slots
        # 恢复满
        player["spell_slots"] = dict(slots)
        self.state.update(
            {"player": player},
            reason="法术位上限更新",
            actor="系统"
        )
        return {"success": True, "slots": slots}

    # ----------------------------------------------------------------
    # 施放法术
    # ----------------------------------------------------------------

    def cast_spell(self, spell_id: str, spell_level: int = None,
                   target: str = "", spell_data: Dict = None) -> Dict[str, Any]:
        """施放法术

        D&D 5e 规则（按职业类型区分）:
        - 已知型施法者（术士/吟游诗人/邪术师）: 仅需在 spells_known
        - 准备型施法者（牧师/德鲁伊/圣武士/法师/游侠）: 必须在 spells_prepared
        - 戏法 (cantrip): 永远不消耗法术位，无需准备
        - 0 等级法术视为戏法

        Args:
            spell_id: 法术 ID 或名称
            spell_level: 使用的法术位等级（None 则用最低可用）
            target: 目标
            spell_data: 法术数据（伤害/效果/是否需要专注等）

        Returns:
            施放结果
        """
        player = self.state.get("player") or {}
        prepared = player.get("spells_prepared", [])
        known = player.get("spells_known", [])
        slots = player.get("spell_slots", {})
        slots_max = player.get("spell_slots_max", {})
        class_name = player.get("class", "")

        # 检查是否已知/已准备（戏法不需要准备）
        is_cantrip = bool(
            spell_level == 0 or (spell_data and spell_data.get("level") == 0)
        )

        if not is_cantrip:
            if _is_known_caster(class_name):
                # 已知型：只查 spells_known（如邪术师戏法外都是从已知列表里施）
                if spell_id not in known:
                    return {
                        "success": False,
                        "error": f"{class_name}（已知型施法者）不会这个法术: {spell_id}",
                    }
            elif _is_prepared_caster(class_name):
                # 准备型：必须在 prepared 里，且必须 known（法师从法术书 → 已知 → 准备）
                if spell_id not in known:
                    return {
                        "success": False,
                        "error": f"{class_name}（准备型施法者）尚未习得此法术: {spell_id}",
                    }
                if spell_id not in prepared:
                    return {
                        "success": False,
                        "error": f"{class_name}今天没有准备这个法术: {spell_id}",
                    }
            else:
                # 未识别职业：保守走准备流程（避免破坏既有数据）
                if spell_id not in known and spell_id not in prepared:
                    return {"success": False, "error": f"你还不会这个法术: {spell_id}"}
                if spell_id not in prepared:
                    return {"success": False, "error": f"你没有准备这个法术: {spell_id}"}

        # 确定使用的法术位等级
        if is_cantrip:
            used_level = 0
            slot_used = False
        else:
            used_level = self._find_slot(spell_level, slots, slots_max)
            if used_level is None:
                return {"success": False, "error": "没有可用的法术位"}
            # 消耗法术位
            slots[str(used_level)] = slots.get(str(used_level), 1) - 1
            slot_used = True

        # 专注处理
        concentration = False
        if spell_data and spell_data.get("concentration"):
            # 结束当前专注法术
            old_concentration = player.get("concentration")
            if old_concentration:
                # 触发专注结束效果
                pass
            player["concentration"] = spell_id
            concentration = True

        # 效果处理
        effect_result = self._apply_spell_effect(spell_data, target, player)

        # 保存
        if slot_used:
            player["spell_slots"] = slots
        self.state.update(
            {"player": player},
            reason=f"施放法术: {spell_id} ({used_level}环)" if not is_cantrip else f"施展戏法: {spell_id}",
            actor="玩家"
        )

        return {
            "success": True,
            "spell_id": spell_id,
            "level_used": used_level,
            "is_cantrip": is_cantrip,
            "caster_type": (
                "known" if _is_known_caster(class_name)
                else "prepared" if _is_prepared_caster(class_name)
                else "unknown"
            ),
            "concentration": concentration,
            "slot_level": used_level,
            "slots_remaining": slots.get(str(used_level), 0) if not is_cantrip else "∞",
            "effect": effect_result,
            **self._rule_id_for_spell(spell_id),
        }

    def _rule_id_for_spell(self, spell_id: str) -> Dict[str, Any]:
        """从 RulesBook 查 rule_id。

        返回 dict，包含 rule_id（可能为 None）和 phb_page（可能为 None）。
        用 ** 合并到施法返回值里。
        """
        try:
            from .app_context import get_app
            rules = get_app().rules
            if not rules or not rules.is_loaded("dnd5e"):
                return {}
            # spell_id 通常是 "Fireball" 这种英文名
            # RulesBook 里 name 是 slug（"fireball"）
            slug = spell_id.lower().replace(" ", "_")
            rule = rules.get("dnd5e", "spells", slug)
            if not rule:
                # 再用 name_en 试
                results = rules.search(spell_id, system="dnd5e", category="spells", top_k=1)
                if results:
                    rule = results[0]
            if rule:
                return {
                    "rule_id": rule.get("rule_id"),
                    "phb_page": rule.get("phb_page"),
                }
        except Exception:
            pass
        return {}

    def _find_slot(self, requested_level, current_slots: Dict, max_slots: Dict) -> Optional[int]:
        """找一个可用的法术位（委托给 domain.spells.find_slot）"""
        return _find_slot_from_domain(requested_level, current_slots, max_slots)

    def _apply_spell_effect(self, spell_data: Dict, target: str,
                            player: Dict) -> Dict[str, Any]:
        """应用法术效果（简化）

        支持：
        - 治疗 (heal)
        - 伤害 (damage)
        - 状态效果 (condition/buff)
        """
        if not spell_data:
            return {"note": "无法术数据，效果需 DM 描述"}

        effect = {}

        # 治疗
        if "heal" in spell_data:
            heal_info = spell_data["heal"]
            heal_dice = heal_info.get("dice", "")
            heal_mod = heal_info.get("modifier", 0)

            if heal_dice:
                # 掷治疗骰
                heal_result = roll_healing(heal_dice, modifier=heal_mod)
                if heal_result["rolls"]:
                    total = heal_result["total"]
                    hp = player.get("hp", {})
                    old_hp = hp.get("current", 0)
                    max_hp = hp.get("max", old_hp)
                    new_hp = min(max_hp, old_hp + total)
                    actual = new_hp - old_hp
                    hp["current"] = new_hp
                    player["hp"] = hp
                    effect["healed"] = actual
                    effect["heal_roll"] = total
                    effect["heal_dice"] = heal_dice

        # 伤害（对玩家自己造成伤害的法术极少见，一般是对敌人的）
        # 这里主要用于反冲/反噬等自伤效果
        if "self_damage" in spell_data:
            pass  # 一般不在这处理

        # 获得状态
        if "condition" in spell_data:
            cond = spell_data["condition"]
            conditions = player.setdefault("conditions", [])
            conditions.append({
                "name": cond.get("name", spell_data.get("name", "法术效果")),
                "type": cond.get("type", "buff"),
                "duration": cond.get("duration", ""),
                "source": spell_data.get("name", ""),
            })
            effect["condition_added"] = cond.get("name")

        return effect

    # ----------------------------------------------------------------
    # 专注
    # ----------------------------------------------------------------

    def get_concentration(self) -> Optional[Dict]:
        """当前专注法术"""
        player = self.state.get("player") or {}
        return player.get("concentration")

    def end_concentration(self, reason: str = "专注结束") -> Dict[str, Any]:
        """结束专注"""
        player = self.state.get("player") or {}
        current = player.get("concentration")
        if not current:
            return {"success": False, "error": "当前没有维持的专注法术"}

        spell_name = current if isinstance(current, str) else current.get("spell", "")
        player["concentration"] = None

        self.state.update(
            {"player": player},
            reason=f"专注结束: {spell_name}（{reason}）",
            actor="系统"
        )
        return {"success": True, "spell": spell_name, "reason": reason}

    def concentration_check(self, damage: int) -> Dict[str, Any]:
        """专注豁免检定

        受到伤害时进行体质豁免，DC 为 max(10, damage/2)
        失败则失去专注。
        """
        player = self.state.get("player") or {}
        if not player.get("concentration"):
            return {"success": True, "check_needed": False,
                    "message": "没有专注法术"}

        dc = max(10, damage // 2)
        con_score = player.get("abilities", {}).get("con", 10)
        con_mod = (con_score - 10) // 2

        # 如果有 check engine，用它；否则自己骰
        d20 = roll_d20()
        roll = d20["nat_roll"]
        total = roll + con_mod
        success = total >= dc

        if not success:
            self.end_concentration(reason=f"受到 {damage} 点伤害，专注豁免失败")

        return {
            "success": True,
            "check_needed": True,
            "dc": dc,
            "roll": roll,
            "modifier": con_mod,
            "total": total,
            "concentration_maintained": success,
            "result": "成功" if success else "失败",
        }

    # ----------------------------------------------------------------
    # 法术位恢复（休息时调用）
    # ----------------------------------------------------------------

    def restore_all_slots(self) -> Dict[str, Any]:
        """恢复所有法术位（长休）"""
        player = self.state.get("player") or {}
        max_slots = player.get("spell_slots_max", {})
        player["spell_slots"] = dict(max_slots)

        self.state.update(
            {"player": player},
            reason="长休：恢复所有法术位",
            actor="系统"
        )
        return {"success": True, "slots_restored": max_slots}
