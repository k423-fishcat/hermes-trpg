"""战斗追踪器（Combat Tracker）

管理一场战斗的状态：先攻顺序、回合、怪物实例、伤害、状态效果。
和 State 系统集成，数据存在 state.combat 里。

数据结构：
combat:
  active: false
  name: ""
  round: 0
  turn: 0                         # 当前行动单位索引
  initiative_order:               # 先攻顺序（从高到低）
    - { name: "玩家", initiative: 15, is_player: true, is_alive: true }
    - { name: "哥布林1", initiative: 12, is_player: false, creature_ref: "goblin#1", is_alive: true }
  creatures:                      # 参战怪物实例（战斗结束后保留日志用）
    goblin#1:
      template_id: "goblin"
      display_name: "哥布林1"
      hp: { max: 7, current: 7, temp: 0 }
      ac: 15
      conditions: []
      ...
  log: []                         # 战斗日志
"""

import time
from typing import Any, Dict, List, Optional

from .dice import roll_initiative
from .domain.combat import (
    apply_damage_modifiers,
    build_rule_reference,
    add_condition_to_creature,
    remove_condition_from_creature,
)


class CombatTracker:
    """战斗追踪器"""

    def __init__(self, state_mgr, bestiary=None):
        self.state = state_mgr
        self.bestiary = bestiary

    def _get_combat(self) -> dict:
        combat = self.state.get("combat")
        if combat is None:
            combat = {
                "active": False,
                "name": "",
                "round": 0,
                "turn": 0,
                "initiative_order": [],
                "creatures": {},
                "log": [],
            }
            self.state.update({"combat": combat}, reason="初始化战斗追踪器", actor="系统")
        return combat

    def _save_combat(self, combat: dict, reason: str, snapshot: bool = False) -> None:
        """保存战斗状态。

        Args:
            combat: 战斗状态 dict
            reason: 变更原因
            snapshot: 是否写版本快照。战斗中高频数值变更默认 False（只保存
                      state.json 不写快照）；战斗开始/结束传 True。
        """
        self.state.update({"combat": combat}, reason=reason, actor="系统", snapshot=snapshot)

    # ----------------------------------------------------------------
    # 战斗开始 / 结束
    # ----------------------------------------------------------------

    def start_combat(self, name: str = "",
                     monsters: List[Dict] = None,
                     srd_monsters: List[Dict] = None,
                     player_initiative: int = 10,
                     monster_data_list: List[Dict] = None) -> Dict[str, Any]:
        """开始战斗

        Args:
            name: 战斗名称
            monsters: 本地图鉴怪物列表 [{monster_id, count, display_prefix, initiative_bonus}]
            srd_monsters: SRD怪物列表 [{srd_key, count, display_prefix, initiative_bonus, srd_data}]
            player_initiative: 玩家先攻值
            monster_data_list: 已转换好的怪物数据列表 [{template_data, count, ...}]（预转换用）

        Returns:
            战斗开始结果
        """
        combat = self._get_combat()
        if combat.get("active"):
            return {"success": False, "error": "已有进行中的战斗"}

        # 战斗开始前保存命名快照（方便回滚）
        try:
            self.state.save_named_snapshot(
                f"pre_combat_{name or 'encounter'}",
                reason="战斗开始前"
            )
        except Exception:
            pass  # 快照失败不影响战斗开始

        combat["active"] = True
        combat["name"] = name or "遭遇战"
        combat["round"] = 1
        combat["turn"] = 0
        combat["initiative_order"] = []
        combat["creatures"] = {}
        combat["log"] = []

        # 添加玩家
        player_info = {
            "name": "玩家",
            "initiative": player_initiative,
            "is_player": True,
            "is_alive": True,
        }
        combat["initiative_order"].append(player_info)

        # 添加怪物
        if monsters and self.bestiary:
            idx = 0
            for mspec in monsters:
                mid = mspec.get("monster_id") or mspec.get("template_id")
                count = mspec.get("count", 1)
                prefix = mspec.get("display_prefix", "")
                init_bonus = mspec.get("initiative_bonus", 0)

                template = self.bestiary.get_template_stats(mid)
                if not template:
                    continue

                for i in range(count):
                    idx += 1
                    # 先攻 = 1d20 + 调整值
                    initiative = roll_initiative(dex_modifier=init_bonus)["total"]
                    display_name = f"{prefix or template['name']}{idx}"
                    ref_id = f"{mid}#{idx}"

                    # 实例化怪物
                    instance = self.bestiary.instantiate(mid, display_name)
                    if instance:
                        instance.pop("_template", None)  # 不存模板引用
                        combat["creatures"][ref_id] = instance

                    combat["initiative_order"].append({
                        "name": display_name,
                        "initiative": initiative,
                        "is_player": False,
                        "creature_ref": ref_id,
                        "is_alive": True,
                    })

        # 添加 SRD 怪物（从 dnd-rules 数据转换）
        if srd_monsters:
            for mspec in srd_monsters:
                srd_data = mspec.get("srd_data")
                if not srd_data:
                    continue
                count = mspec.get("count", 1)
                prefix = mspec.get("display_prefix", "")
                init_bonus = mspec.get("initiative_bonus", 0)

                # 转换 SRD 数据为模板格式
                template = self._convert_srd_to_template(srd_data)
                if not template:
                    continue

                for i in range(count):
                    idx = len(combat["creatures"]) + 1
                    initiative = roll_initiative(dex_modifier=init_bonus)["total"]
                    display_name = f"{prefix or template['name']}{idx}"
                    ref_id = f"srd:{template['id']}#{idx}"

                    # 实例化
                    instance = self._instantiate_from_template(template, display_name)
                    combat["creatures"][ref_id] = instance

                    combat["initiative_order"].append({
                        "name": display_name,
                        "initiative": initiative,
                        "is_player": False,
                        "creature_ref": ref_id,
                        "is_alive": True,
                    })

        # 添加预转换好的怪物数据
        if monster_data_list:
            for mspec in monster_data_list:
                template_data = mspec.get("template_data")
                if not template_data:
                    continue
                count = mspec.get("count", 1)
                prefix = mspec.get("display_prefix", template_data.get("name", ""))
                init_bonus = mspec.get("initiative_bonus", 0)

                for i in range(count):
                    idx = len(combat["creatures"]) + 1
                    initiative = roll_initiative(dex_modifier=init_bonus)["total"]
                    display_name = f"{prefix}{idx}" if count > 1 else prefix
                    ref_id = f"custom:{template_data.get('id', 'monster')}#{idx}"

                    instance = self._instantiate_from_template(template_data, display_name)
                    combat["creatures"][ref_id] = instance

                    combat["initiative_order"].append({
                        "name": display_name,
                        "initiative": initiative,
                        "is_player": False,
                        "creature_ref": ref_id,
                        "is_alive": True,
                    })

        # 按先攻排序（高的在前）
        combat["initiative_order"].sort(key=lambda x: -x["initiative"])

        # 记录日志
        self._log(combat, f"战斗开始：{name or '遭遇战'}")
        self._log(combat, f"先攻顺序：" +
                  " → ".join(f"{u['name']}(+{u['initiative']})"
                             for u in combat["initiative_order"]))

        self._save_combat(combat, f"战斗开始: {name or '遭遇战'}", snapshot=True)
        return {
            "success": True,
            "name": name or "遭遇战",
            "initiative_order": combat["initiative_order"],
            "creature_count": len(combat["creatures"]),
        }

    def add_creature(self, name: str, initiative: int,
                     template_id: str = None,
                     is_player: bool = False) -> Dict[str, Any]:
        """中途加入战斗单位"""
        combat = self._get_combat()
        if not combat.get("active"):
            return {"success": False, "error": "没有进行中的战斗"}

        ref_id = None
        if template_id and self.bestiary:
            instance = self.bestiary.instantiate(template_id, name)
            if instance:
                ref_id = f"{template_id}#{len(combat['creatures']) + 1}"
                instance.pop("_template", None)
                combat["creatures"][ref_id] = instance

        unit = {
            "name": name,
            "initiative": initiative,
            "is_player": is_player,
            "creature_ref": ref_id,
            "is_alive": True,
        }

        # 插入正确位置
        order = combat["initiative_order"]
        inserted = False
        for i, u in enumerate(order):
            if u["initiative"] < initiative:
                order.insert(i, unit)
                inserted = True
                break
        if not inserted:
            order.append(unit)

        # 如果插入位置在当前回合之前，当前回合数 +1（保持当前单位不变）
        insert_pos = order.index(unit)
        if insert_pos <= combat.get("turn", 0):
            combat["turn"] = combat.get("turn", 0) + 1

        self._log(combat, f"{name} 加入战斗（先攻 {initiative}）")
        self._save_combat(combat, f"{name} 加入战斗")
        return {"success": True, "name": name, "initiative": initiative}

    def end_combat(self, result: str = "胜利") -> Dict[str, Any]:
        """结束战斗"""
        combat = self._get_combat()
        if not combat.get("active"):
            return {"success": False, "error": "没有进行中的战斗"}

        combat["active"] = False
        self._log(combat, f"战斗结束：{result}")
        self._save_combat(combat, f"战斗结束: {result}", snapshot=True)
        return {
            "success": True,
            "result": result,
            "rounds": combat.get("round", 0),
            "log_entries": len(combat.get("log", [])),
        }

    # ----------------------------------------------------------------
    # 回合推进
    # ----------------------------------------------------------------

    def next_turn(self) -> Dict[str, Any]:
        """下一个行动单位"""
        combat = self._get_combat()
        if not combat.get("active"):
            return {"success": False, "error": "没有进行中的战斗"}

        order = combat["initiative_order"]
        if not order:
            return {"success": False, "error": "战斗中没有单位"}

        turn = combat.get("turn", 0)
        turn += 1

        # 跳过已死亡的单位
        skipped = 0
        while turn < len(order) and not order[turn].get("is_alive", True):
            turn += 1
            skipped += 1

        if turn >= len(order):
            # 新一回合
            turn = 0
            combat["round"] = combat.get("round", 0) + 1
            # 新一回合重置一些东西（反应次数等）
            for ref_id, cre in combat.get("creatures", {}).items():
                cre["reactions_used"] = 0
            # 找第一个活着的
            while turn < len(order) and not order[turn].get("is_alive", True):
                turn += 1

        combat["turn"] = turn
        current = order[turn]

        is_new_round = turn == 0
        if is_new_round:
            self._log(combat, f"第 {combat['round']} 回合开始")

        self._log(combat, f"轮到 {current['name']} 行动")
        self._save_combat(combat, f"回合推进: {current['name']}")

        return {
            "success": True,
            "current": current["name"],
            "is_player": current.get("is_player", False),
            "round": combat["round"],
            "turn_index": turn,
            "is_new_round": is_new_round,
        }

    def current_turn(self) -> Optional[Dict]:
        """当前行动单位"""
        combat = self._get_combat()
        if not combat.get("active"):
            return None
        order = combat["initiative_order"]
        turn = combat.get("turn", 0)
        if turn >= len(order):
            return None
        return order[turn]

    # ----------------------------------------------------------------
    # 伤害与治疗（怪物）
    # ----------------------------------------------------------------

    def damage_creature(self, creature_ref: str, amount: int,
                        damage_type: str = "", source: str = "",
                        critical: bool = False) -> Dict[str, Any]:
        """对怪物造成伤害（带规则引用和详细计算过程）

        D&D 5e 伤害规则（PHB p.197）：
        - 免疫 → 0 伤害
        - 易伤 → 翻倍
        - 抗性 → 减半（向下取整）
        - 多种抗/免/易伤独立应用（不累乘）
        - 暴击（critical=True）→ 伤害骰翻倍（不含调整值），抗/免/易伤正常应用
        - 临时 HP 优先抵消
        - HP 归零 → 死亡
        """
        combat = self._get_combat()
        if creature_ref not in combat.get("creatures", {}):
            # 试试按名字找
            for ref, cre in combat.get("creatures", {}).items():
                if cre.get("name") == creature_ref:
                    creature_ref = ref
                    break
            else:
                return {"success": False, "error": f"找不到怪物: {creature_ref}"}

        cre = combat["creatures"][creature_ref]
        hp = cre.get("hp", {})
        current = hp.get("current", 0)
        temp = hp.get("temp", 0)

        # 委托给 domain.combat.damage
        template = self._get_template(cre.get("template_id", ""))
        calc = apply_damage_modifiers(
            creature=cre,
            template=template,
            amount=amount,
            damage_type=damage_type,
            critical=critical,
        )

        # 写回 HP（按 calc.actual_damage 减扣）
        new_current = current
        if temp > 0:
            if calc.actual_damage == 0:
                hp["temp"] = temp - calc.temp_absorbed
            else:
                hp["temp"] = 0
                new_current = max(0, current - calc.actual_damage)
        else:
            new_current = max(0, current - calc.actual_damage)
        hp["current"] = new_current
        cre["hp"] = hp

        # 日志：抗/免/易伤
        if calc.immunities_applied:
            self._log(combat, f"{cre['name']} 免疫 {damage_type} 伤害！")
        if calc.vulnerabilities_applied:
            self._log(combat, f"{cre['name']} 对 {damage_type} 易伤（翻倍）")
        if calc.resistances_applied:
            self._log(combat, f"{cre['name']} 抵抗 {damage_type} 伤害（减半）")
        if critical:
            self._log(combat, f"💥 {cre['name']} 受到暴击！")

        killed = False
        if calc.killed and hp["current"] <= 0 and cre.get("is_alive", True):
            cre["is_alive"] = False
            killed = True
            for u in combat["initiative_order"]:
                if u.get("creature_ref") == creature_ref:
                    u["is_alive"] = False
                    break
            self._log(combat, f"💀 {cre['name']} 倒下了！")
            calc.calc_steps.append("💀 HP 归零，目标倒下！")

        self._log(combat,
                  f"{cre['name']} 受到 {calc.final_amount} 点{damage_type}伤害（{source}），"
                  f"HP: {hp['current']}/{hp['max']}")
        self._save_combat(combat, f"{cre['name']} 受伤 {calc.final_amount}")

        rule_reference = build_rule_reference(
            damage_type=damage_type,
            res_applied=calc.resistances_applied,
            vuln_applied=calc.vulnerabilities_applied,
            imm_applied=calc.immunities_applied,
            had_temp_hp=temp > 0,
            critical=critical,
            killed=killed,
        )

        return {
            "success": True,
            "name": cre["name"],
            "damage": calc.actual_damage,
            "initial_damage": calc.initial_amount,
            "damage_type": damage_type,
            "hp_current": hp["current"],
            "hp_max": hp["max"],
            "temp_hp": hp.get("temp", 0),
            "killed": killed,
            "vulnerabilities_applied": calc.vulnerabilities_applied,
            "resistances_applied": calc.resistances_applied,
            "immunities_applied": calc.immunities_applied,
            "critical": critical,
            "calc_steps": calc.calc_steps,
            "rule_reference": rule_reference,
            "source": source,
        }

    def heal_creature(self, creature_ref: str, amount: int,
                      source: str = "") -> Dict[str, Any]:
        """治疗怪物"""
        combat = self._get_combat()
        if creature_ref not in combat.get("creatures", {}):
            return {"success": False, "error": f"找不到怪物: {creature_ref}"}

        cre = combat["creatures"][creature_ref]
        hp = cre.get("hp", {})
        old_hp = hp.get("current", 0)
        new_hp = min(hp.get("max", 0), old_hp + amount)
        hp["current"] = new_hp
        cre["hp"] = hp

        # 复活
        if old_hp <= 0 and new_hp > 0 and not cre.get("is_alive", True):
            cre["is_alive"] = True
            for u in combat["initiative_order"]:
                if u.get("creature_ref") == creature_ref:
                    u["is_alive"] = True
                    break
            self._log(combat, f"✨ {cre['name']} 恢复意识！")

        actual = new_hp - old_hp
        self._log(combat, f"{cre['name']} 恢复 {actual} HP（{source}），HP: {new_hp}/{hp['max']}")
        self._save_combat(combat, f"{cre['name']} 恢复 {actual} HP")
        return {
            "success": True,
            "name": cre["name"],
            "healed": actual,
            "hp_current": new_hp,
            "hp_max": hp["max"],
        }

    # ----------------------------------------------------------------
    # 状态效果
    # ----------------------------------------------------------------

    def add_condition(self, creature_ref: str, condition_name: str,
                      display_name: str = "", duration: str = "") -> Dict[str, Any]:
        """给怪物添加状态效果"""
        combat = self._get_combat()
        if creature_ref not in combat.get("creatures", {}):
            return {"success": False, "error": f"找不到怪物: {creature_ref}"}

        cre = combat["creatures"][creature_ref]
        result = add_condition_to_creature(
            cre, condition_name, display_name, duration,
            start_round=combat.get("round", 1),
        )
        if not result["ok"]:
            return {"success": False, "error": f"已有状态: {condition_name}"}

        self._log(combat, f"{cre['name']} 获得状态：{display_name or condition_name}")
        self._save_combat(combat, f"{cre['name']} 获得状态 {condition_name}")
        return {"success": True, "name": cre["name"], "condition": condition_name}

    def remove_condition(self, creature_ref: str, condition_name: str) -> Dict[str, Any]:
        """移除怪物状态"""
        combat = self._get_combat()
        if creature_ref not in combat.get("creatures", {}):
            return {"success": False, "error": f"找不到怪物: {creature_ref}"}

        cre = combat["creatures"][creature_ref]
        result = remove_condition_from_creature(cre, condition_name)
        if not result["ok"]:
            return {"success": False, "error": f"没有状态: {condition_name}"}

        self._log(combat, f"{cre['name']} 移除状态：{condition_name}")
        self._save_combat(combat, f"{cre['name']} 移除状态 {condition_name}")
        return {"success": True, "name": cre["name"], "condition": condition_name}

    # ----------------------------------------------------------------
    # 状态查看
    # ----------------------------------------------------------------

    def status(self) -> str:
        """战斗状态总览"""
        combat = self._get_combat()
        if not combat.get("active"):
            return "（没有进行中的战斗）"

        order = combat["initiative_order"]
        turn = combat.get("turn", 0)

        lines = [
            f"⚔️ {combat.get('name', '遭遇战')}",
            f"第 {combat.get('round', 1)} 回合",
            "=" * 30,
        ]

        for i, unit in enumerate(order):
            marker = "→ " if i == turn else "  "
            status = "💀" if not unit.get("is_alive", True) else ("🧙" if unit.get("is_player") else "👹")
            hp_info = ""
            if unit.get("creature_ref"):
                cre = combat["creatures"].get(unit["creature_ref"], {})
                hp = cre.get("hp", {})
                hp_info = f" HP:{hp.get('current', '?')}/{hp.get('max', '?')}"
                conds = cre.get("conditions", [])
                if conds:
                    hp_info += " [" + ",".join(c.get("display_name", c.get("name","")) for c in conds) + "]"

            lines.append(f"{marker}{status} {unit['name']} (先攻 {unit['initiative']}){hp_info}")

        # 存活统计
        alive_monsters = sum(1 for u in order if not u.get("is_player") and u.get("is_alive", True))
        lines.append("")
        lines.append(f"存活怪物: {alive_monsters} 只")

        return "\n".join(lines)

    def creature_status(self, creature_ref: str) -> Optional[str]:
        """查看单个怪物详细状态"""
        combat = self._get_combat()
        cre = combat.get("creatures", {}).get(creature_ref)
        if not cre:
            return None

        lines = [
            f"👹 {cre.get('name', creature_ref)}",
            f"模板: {cre.get('template_id', '?')}",
            f"HP: {cre['hp']['current']}/{cre['hp']['max']}" +
                (f" (+{cre['hp']['temp']} 临时)" if cre['hp'].get("temp") else ""),
            f"AC: {cre.get('ac', '?')}",
            f"状态: {'存活' if cre.get('is_alive', True) else '死亡'}",
        ]
        if cre.get("conditions"):
            lines.append("状态效果:")
            for c in cre["conditions"]:
                lines.append(f"  • {c.get('display_name', c.get('name',''))} ({c.get('duration', '?')})")

        # 从模板拉攻击数据
        template = self._get_template(cre.get("template_id", ""))
        if template and template.get("attacks"):
            lines.append("攻击:")
            for atk in template["attacks"]:
                lines.append(f"  • {atk['name']}: +{atk.get('hit_bonus','?')} / {atk.get('damage','?')} {atk.get('damage_type','')}")

        return "\n".join(lines)

    def get_log(self, limit: int = 20) -> List[str]:
        """获取战斗日志"""
        combat = self._get_combat()
        log = combat.get("log", [])
        return log[-limit:]

    # ----------------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------------

    def _log(self, combat: dict, message: str) -> None:
        """写战斗日志"""
        entry = {
            "time": time.time(),
            "round": combat.get("round", 0),
            "message": message,
        }
        combat.setdefault("log", []).append(entry)
        # 最多保留 200 条
        if len(combat["log"]) > 200:
            combat["log"] = combat["log"][-200:]

    def _get_template(self, template_id: str) -> Optional[dict]:
        """从图鉴获取模板数据（带缓存）"""
        if not self.bestiary or not template_id:
            return None
        return self.bestiary.get_template_stats(template_id)

    def _convert_srd_to_template(self, srd_data: dict) -> Optional[dict]:
        """把 dnd-rules 的 SRD 怪物数据转成战斗用模板格式

        这是轻量版转换，只提取战斗需要的字段。
        """
        try:
            from bestiary_import import convert_creature_to_bestiary
            return convert_creature_to_bestiary(srd_data)
        except ImportError:
            # 回退：手动提取关键字段
            name = srd_data.get("name", "Unknown")
            key = srd_data.get("key", "")
            mid = key.replace("srd-2024_", "").replace("wotc-srd_", "")
            abilities = {}
            for full, abbr in [("strength","str"),("dexterity","dex"),("constitution","con"),
                              ("intelligence","int"),("wisdom","wis"),("charisma","cha")]:
                abilities[abbr] = srd_data.get("ability_scores", {}).get(full, 10)
            attacks = []
            for action in srd_data.get("actions", []):
                for atk in action.get("attacks", []):
                    dmg_die = atk.get("damage_die_type", "d6").lower()
                    dmg_str = f"{atk.get('damage_die_count', 1)}{dmg_die}"
                    if atk.get("damage_bonus"):
                        dmg_str += f"+{atk['damage_bonus']}"
                    dmg_type = ""
                    dt = atk.get("damage_type")
                    if isinstance(dt, dict):
                        dmg_type = dt.get("name", "")
                    attacks.append({
                        "name": action.get("name", ""),
                        "hit_bonus": atk.get("to_hit_mod", 0),
                        "damage": dmg_str,
                        "damage_type": dmg_type,
                    })
            return {
                "id": mid,
                "name": name,
                "hp_average": srd_data.get("hit_points", 0),
                "hp_formula": srd_data.get("hit_dice", ""),
                "ac": srd_data.get("armor_class", 10),
                "speed": srd_data.get("speed", {}).get("walk", 30),
                "abilities": abilities,
                "attacks": attacks,
                "special_abilities": [],
            }

    def _instantiate_from_template(self, template: dict, display_name: str) -> dict:
        """从模板数据生成战斗实例"""
        hp_avg = template.get("hp_average", template.get("stats", {}).get("hp_average", 0))
        ac = template.get("ac", template.get("stats", {}).get("ac", 10))
        return {
            "template_id": template.get("id", ""),
            "name": display_name,
            "hp": {
                "max": hp_avg,
                "current": hp_avg,
                "temp": 0,
            },
            "ac": ac,
            "conditions": [],
            "is_alive": True,
            "reactions_used": 0,
        }
