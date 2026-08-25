"""休息与恢复系统（Short Rest / Long Rest）

DnD 5e 休息规则：
- 短休（Short Rest）：至少 1 小时，可用命中骰恢复 HP，不恢复法术位
- 长休（Long Rest）：至少 8 小时睡眠，HP 回满，恢复所有命中骰，恢复所有法术位
  - 长休 24 小时内只能一次
  - 长休恢复的命中骰数量 = 总命中骰数的一半（向下取整），最少 1 个
"""

import time
from typing import Any, Dict, List, Optional

from .dice import roll_hit_dice_total


class RestManager:
    """休息恢复管理器"""

    def __init__(self, state_mgr, clock=None):
        self.state = state_mgr
        self.clock = clock

    # ----------------------------------------------------------------
    # 短休
    # ----------------------------------------------------------------

    def short_rest(self, hit_dice_count: int = 1) -> Dict[str, Any]:
        """短休

        D&D 5e 规则（PHB p. 186）：
        - 至少 1 小时
        - 起始 HP 必须 >= 1（0 HP 不能短休，要做死亡豁免）
        - 邪术师（Warlock）短休恢复所有 Pact Magic 法术位
        - 可用 1+ 命中骰恢复 HP（按 die 实际结果 + CON 调整）
        - 不恢复常规法术位

        Args:
            hit_dice_count: 使用几个命中骰恢复 HP

        Returns:
            休息结果字典
        """
        player = self.state.get("player") or {}
        if not player:
            return {"success": False, "error": "没有玩家状态"}

        hp = player.get("hp", {})
        current_hp = hp.get("current", 0)
        max_hp = hp.get("max", current_hp)

        # PHB 规则：起始 HP 必须 >= 1 才能短休
        if current_hp <= 0:
            return {
                "success": False,
                "error": "HP 为 0（濒死），不能进行短休，需进行死亡豁免",
            }

        hit_dice = player.get("hit_dice", {})
        total_dice = hit_dice.get("total", "1d8")
        used_dice = hit_dice.get("used", 0)

        # 计算可用命中骰
        try:
            num, sides = self._parse_hit_dice(total_dice)
        except Exception:
            return {"success": False, "error": f"无法解析命中骰: {total_dice}"}

        available_dice = max(0, num - used_dice)

        # 实际使用数量（不超过可用）
        use_count = min(hit_dice_count, available_dice) if available_dice > 0 else 0
        # 短休也可以不使用命中骰（如邪术师仅想恢复 Pact Magic）
        if available_dice == 0 and hit_dice_count > 0:
            return {"success": False, "error": "没有可用的命中骰了，需要长休恢复"}

        # 掷命中骰 + 体质调整
        con_score = player.get("abilities", {}).get("con", 10)
        con_mod = (con_score - 10) // 2

        # 用 dice.roll_hit_dice_total 一次性掷 N 颗
        result = roll_hit_dice_total(f"{use_count}d{sides}", con_modifier=con_mod)
        rolls = result["rolls"]
        heal_total = result["heal_total"]

        new_hp = min(max_hp, current_hp + heal_total)
        actual_heal = new_hp - current_hp

        # PHB 规则：邪术师短休恢复所有 Pact Magic slots
        pact_restored = {}
        pact_slots = player.get("pact_magic_slots", {})
        pact_max = player.get("pact_magic_max", {})
        class_name = player.get("class", "")
        is_warlock = class_name in ("邪术师", "warlock", "Warlock")
        if is_warlock and pact_max:
            for level, max_val in pact_max.items():
                before = pact_slots.get(level, 0)
                pact_slots[level] = max_val
                pact_restored[level] = max_val - before
            player["pact_magic_slots"] = pact_slots

        # 更新状态
        player["hp"]["current"] = new_hp
        player["hit_dice"]["used"] = used_dice + use_count
        self.state.update(
            {"player": player},
            reason=(
                f"短休：恢复 {actual_heal} HP"
                + (f"（{use_count} 个命中骰）" if use_count > 0 else "（未使用命中骰）")
                + (f"；邪术师 Pact Magic 恢复 {pact_restored}" if pact_restored else "")
            ),
            actor="系统"
        )

        # 推进时间（1 小时）
        if self.clock:
            self.clock.advance_hours(1)

        return {
            "success": True,
            "rest_type": "short",
            "hit_dice_used": use_count,
            "hit_dice_rolls": rolls,
            "con_modifier": con_mod,
            "healed": actual_heal,
            "hp_before": current_hp,
            "hp_after": new_hp,
            "hp_max": max_hp,
            "hit_dice_remaining": available_dice - use_count,
            "hit_dice_total": num,
            "pact_magic_restored": pact_restored,
            "warlock": is_warlock,
        }

    # ----------------------------------------------------------------
    # 长休
    # ----------------------------------------------------------------

    def long_rest(self) -> Dict[str, Any]:
        """长休

        D&D 5e 规则（PHB p. 186）：
        - 至少 8 小时（含 6 小时睡眠 + 最多 2 小时轻活动）
        - 起始 HP 必须 >= 1（濒死不能长休，要先救活）
        - HP 恢复至满
        - 恢复所有法术位
        - 恢复 1/2 命中骰（向下取整），但 0 命中骰的角色不获骰
        - 清空临时 HP
        - 清空死亡豁免计数
        - Exhaustion 等级 -1
        - 24 小时内只能长休一次（且只能获一次收益）

        注意：PHB 实际规则是"不能获得超过一次长休的收益"，但这里
        我们用硬拒绝（24h 内）以避免误用。
        """
        player = self.state.get("player") or {}
        if not player:
            return {"success": False, "error": "没有玩家状态"}

        hp = player.get("hp", {})
        current_hp = hp.get("current", 0)
        max_hp = hp.get("max", current_hp)

        # PHB 规则：起始 HP 必须 >= 1
        if current_hp <= 0:
            return {
                "success": False,
                "error": "HP 为 0（濒死），不能进行长休，需先被救活（如魔法治疗）",
            }

        # 检查 24 小时限制
        last_rest = player.get("last_long_rest", 0)
        now = time.time()
        if last_rest and (now - last_rest) < 86400:  # 24 小时 = 86400 秒
            hours_left = int((86400 - (now - last_rest)) / 3600)
            return {
                "success": False,
                "error": f"距离上次长休不足 24 小时（还有约 {hours_left} 小时）",
                "can_rest": False,
            }

        # 计算命中骰恢复
        hit_dice = player.get("hit_dice", {})
        total_dice = hit_dice.get("total", "1d8")
        used_dice = hit_dice.get("used", 0)

        try:
            num_dice, _ = self._parse_hit_dice(total_dice)
        except Exception:
            num_dice = 1

        # 0 命中骰的角色不获骰（PHB 规则）
        if num_dice <= 0:
            restore_dice = 0
        else:
            # 恢复一半命中骰，向下取整，最少 1 个
            restore_dice = max(1, num_dice // 2)
        new_used = max(0, min(num_dice, used_dice - restore_dice))

        # 恢复 HP
        actual_heal = max_hp - current_hp

        # 恢复法术位
        spell_slots_restore = {}
        spell_slots = player.get("spell_slots", {})
        spell_slots_max = player.get("spell_slots_max", {})
        if spell_slots_max:
            for level, max_val in spell_slots_max.items():
                before = spell_slots.get(level, 0)
                spell_slots[level] = max_val
                spell_slots_restore[level] = max_val - before
        elif spell_slots:
            # 没有 max 信息就跳过（不知道上限）
            pass

        # 恢复邪术师 Pact Magic slots
        pact_restored = {}
        pact_slots = player.get("pact_magic_slots", {})
        pact_max = player.get("pact_magic_max", {})
        if pact_max:
            for level, max_val in pact_max.items():
                before = pact_slots.get(level, 0)
                pact_slots[level] = max_val
                pact_restored[level] = max_val - before
            player["pact_magic_slots"] = pact_slots

        # 清空临时 HP
        hp["temp"] = 0

        # 重置死亡豁免
        death_saves = player.setdefault("death_saves", {})
        death_saves["successes"] = 0
        death_saves["failures"] = 0

        # PHB 规则：长休减少 exhaustion 等级 1
        exhaustion_before = player.get("exhaustion", 0)
        exhaustion_after = max(0, exhaustion_before - 1)

        # 更新
        hp["current"] = max_hp
        hit_dice["used"] = new_used
        player["hp"] = hp
        player["hit_dice"] = hit_dice
        player["spell_slots"] = spell_slots
        player["death_saves"] = death_saves
        player["exhaustion"] = exhaustion_after
        player["last_long_rest"] = now

        self.state.update(
            {"player": player},
            reason=(
                f"长休：恢复所有 HP 和法术位，恢复 {restore_dice} 个命中骰"
                + (f"；exhaustion {exhaustion_before}→{exhaustion_after}" if exhaustion_before else "")
            ),
            actor="系统"
        )

        # 推进时间（8 小时）
        if self.clock:
            self.clock.advance_hours(8)

        return {
            "success": True,
            "rest_type": "long",
            "healed": actual_heal,
            "hp_before": current_hp,
            "hp_after": max_hp,
            "hp_max": max_hp,
            "hit_dice_restored": restore_dice,
            "hit_dice_used_before": used_dice,
            "hit_dice_used_after": new_used,
            "hit_dice_total": num_dice,
            "spell_slots_restored": spell_slots_restore,
            "pact_magic_restored": pact_restored,
            "temp_hp_cleared": True,
            "death_saves_reset": True,
            "exhaustion_before": exhaustion_before,
            "exhaustion_after": exhaustion_after,
        }

    # ----------------------------------------------------------------
    # 辅助
    # ----------------------------------------------------------------

    def rest_status(self) -> Dict[str, Any]:
        """查看休息相关状态"""
        player = self.state.get("player") or {}
        hp = player.get("hp", {})
        hit_dice = player.get("hit_dice", {})
        total_dice = hit_dice.get("total", "1d8")
        used = hit_dice.get("used", 0)

        try:
            num, sides = self._parse_hit_dice(total_dice)
        except Exception:
            num, sides = 1, 8

        available = num - used
        spell_slots = player.get("spell_slots", {})
        spell_max = player.get("spell_slots_max", {})

        return {
            "hp": f"{hp.get('current', 0)}/{hp.get('max', 0)}",
            "temp_hp": hp.get("temp", 0),
            "hit_dice": {
                "total": total_dice,
                "used": used,
                "available": available,
                "dice_per_level": f"1d{sides}",
            },
            "spell_slots": {
                level: {
                    "current": spell_slots.get(level, 0),
                    "max": spell_max.get(level, "未知"),
                }
                for level in sorted(spell_max.keys(), key=lambda x: int(x) if x.isdigit() else 0)
            } if spell_max else "（无法术位数据）",
            "last_long_rest": player.get("last_long_rest", 0),
        }

    def _parse_hit_dice(self, dice_str: str) -> tuple:
        """解析命中骰格式，如 '2d10' → (2, 10)"""
        dice_str = str(dice_str).lower().strip()
        if 'd' not in dice_str:
            return (1, int(dice_str))
        parts = dice_str.split('d')
        num = int(parts[0]) if parts[0] else 1
        sides = int(parts[1])
        return (num, sides)
