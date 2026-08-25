"""遭遇管理器（Encounter Manager）

管理预设遭遇，支持一键启动战斗、获取奖励。
遭遇数据存在 state.world.encounters 里，也可以从模组导入。
"""

import json
from typing import Any, Dict, List, Optional


class EncounterManager:
    """遭遇管理器"""

    def __init__(self, state_mgr, combat_tracker=None, bestiary=None):
        self.state = state_mgr
        self.combat = combat_tracker
        self.bestiary = bestiary

    # ----------------------------------------------------------------
    # 遭遇 CRUD
    # ----------------------------------------------------------------

    def list_encounters(self, location: str = "",
                        encounter_type: str = "") -> List[Dict[str, Any]]:
        """列出遭遇"""
        world = self.state.get("world") or {}
        encounters = world.get("encounters", {})

        result = []
        for eid, enc in encounters.items():
            if location and enc.get("location", "").lower() not in location.lower():
                continue
            if encounter_type and enc.get("type", "") != encounter_type:
                continue
            result.append({"id": eid, **enc})

        return result

    def get_encounter(self, encounter_id: str) -> Optional[Dict[str, Any]]:
        """获取遭遇详情"""
        world = self.state.get("world") or {}
        encounters = world.get("encounters", {})
        return encounters.get(encounter_id)

    def add_encounter(self, encounter_id: str, name: str,
                      description: str = "", encounter_type: str = "combat",
                      location: str = "", creatures: List[Dict] = None,
                      dc_info: Dict = None, rewards: str = "") -> Dict[str, Any]:
        """添加遭遇"""
        world = self.state.get("world") or {}
        encounters = world.setdefault("encounters", {})

        encounters[encounter_id] = {
            "name": name,
            "type": encounter_type,
            "description": description,
            "location": location,
            "creatures": creatures or [],
            "dc_info": dc_info or {},
            "rewards": rewards,
        }

        self.state.update(
            {"world": world},
            reason=f"添加遭遇: {name}",
            actor="DM"
        )
        return {"success": True, "encounter_id": encounter_id, "name": name}

    # ----------------------------------------------------------------
    # 启动遭遇
    # ----------------------------------------------------------------

    def start_encounter(self, encounter_id: str) -> Dict[str, Any]:
        """启动遭遇

        对于战斗遭遇：实例化怪物 → 开始战斗 → 返回描述+战场状态
        对于非战斗遭遇：只返回描述和 DC 信息
        """
        enc = self.get_encounter(encounter_id)
        if not enc:
            return {"success": False, "error": f"遭遇不存在: {encounter_id}"}

        enc_type = enc.get("type", "combat")

        if enc_type == "combat" and self.combat:
            return self._start_combat_encounter(encounter_id, enc)
        else:
            return self._start_social_encounter(encounter_id, enc)

    def _start_combat_encounter(self, enc_id: str, enc: Dict) -> Dict[str, Any]:
        """启动战斗遭遇"""
        creatures = enc.get("creatures", [])
        if not creatures:
            return {
                "success": False,
                "error": "战斗遭遇没有怪物列表",
                "description": enc.get("description", ""),
            }

        # 构造 monster_data_list 给 start_combat
        # 注意：combat.start_combat 的 monster_data_list 每个 entry 期望
        # {template_data, count, display_prefix, initiative_bonus}，缺 template_data
        # 会导致怪物 0 实例化（此前是隐性 bug）。
        monster_list = []
        skipped = 0
        for creature_data in creatures:
            ref = creature_data.get("ref", "")
            name = creature_data.get("name", ref)
            count = creature_data.get("count", 1)
            stats = creature_data.get("stats", {}) or {}

            template_data = None
            if self.bestiary:
                template_data = self.bestiary.get_monster(ref)
            if not template_data and stats:
                # 无 bestiary 但有内联 stats，用 stats 当模板
                template_data = dict(stats)
                template_data.setdefault("id", ref)
            if not template_data:
                skipped += 1
                continue  # 查不到跳过，避免空战斗

            if stats and isinstance(template_data, dict):
                # 内联 stats 覆盖 bestiary 模板
                template_data = {**template_data, **stats}

            monster_list.append({
                "template_data": template_data,
                "count": count,
                "display_prefix": name,
                "initiative_bonus": creature_data.get("initiative_bonus", 0),
            })

        if not monster_list:
            return {
                "success": False,
                "error": f"遭遇 {enc_id} 的怪物无法实例化（ref 不在图鉴且无内联 stats）",
                "description": enc.get("description", ""),
            }

        # 开始战斗
        result = self.combat.start_combat(
            name=enc.get("name", enc_id),
            monster_data_list=monster_list,
        )

        if not result.get("success"):
            return result

        # 标记遭遇已启动
        world = self.state.get("world") or {}
        encounters = world.get("encounters", {})
        if enc_id in encounters:
            encounters[enc_id]["status"] = "active"
            self.state.update(
                {"world": world},
                reason=f"遭遇启动: {enc.get('name', enc_id)}",
                actor="DM"
            )

        return {
            "success": True,
            "encounter_id": enc_id,
            "name": enc.get("name", enc_id),
            "type": "combat",
            "description": enc.get("description", ""),
            "creatures_count": sum(e.get("count", 1) for e in monster_list),
            "combat_status": result,
            "rewards": enc.get("rewards", ""),
            "xp_reward": enc.get("xp", 0),
        }

    def _start_social_encounter(self, enc_id: str, enc: Dict) -> Dict[str, Any]:
        """启动非战斗遭遇（社交/探索/陷阱等）"""
        # 标记为 active
        world = self.state.get("world") or {}
        encounters = world.get("encounters", {})
        if enc_id in encounters:
            encounters[enc_id]["status"] = "active"
            self.state.update(
                {"world": world},
                reason=f"遭遇启动: {enc.get('name', enc_id)}",
                actor="DM"
            )

        return {
            "success": True,
            "encounter_id": enc_id,
            "name": enc.get("name", enc_id),
            "type": enc.get("type", "other"),
            "description": enc.get("description", ""),
            "dc_info": enc.get("dc_info", {}),
            "rewards": enc.get("rewards", ""),
        }

    # ----------------------------------------------------------------
    # 结束遭遇
    # ----------------------------------------------------------------

    def end_encounter(self, encounter_id: str,
                      outcome: str = "victory") -> Dict[str, Any]:
        """结束遭遇，标记状态，返回奖励信息"""
        world = self.state.get("world") or {}
        encounters = world.get("encounters", {})
        if encounter_id not in encounters:
            return {"success": False, "error": f"遭遇不存在: {encounter_id}"}

        enc = encounters[encounter_id]
        enc["status"] = "completed"
        enc["outcome"] = outcome

        self.state.update(
            {"world": world},
            reason=f"遭遇结束: {enc.get('name', encounter_id)} ({outcome})",
            actor="DM"
        )

        # 如果在战斗中，也结束战斗
        if self.combat and enc.get("type") == "combat":
            try:
                self.combat.end_combat()
            except Exception:
                pass

        return {
            "success": True,
            "encounter_id": encounter_id,
            "name": enc.get("name", encounter_id),
            "outcome": outcome,
            "rewards": enc.get("rewards", ""),
            "xp_reward": enc.get("xp", 0),
        }

    # ----------------------------------------------------------------
    # 生成遭遇描述
    # ----------------------------------------------------------------

    def describe_encounter(self, encounter_id: str) -> str:
        """生成遭遇描述文本（给玩家看的）"""
        enc = self.get_encounter(encounter_id)
        if not enc:
            return f"（遭遇不存在: {encounter_id}）"

        lines = [f"⚔️  遭遇：{enc.get('name', encounter_id)}"]
        lines.append("=" * 40)

        if enc.get("description"):
            lines.append(enc["description"])
            lines.append("")

        creatures = enc.get("creatures", [])
        if creatures and enc.get("type") == "combat":
            lines.append("敌人：")
            for c in creatures:
                name = c.get("name", c.get("ref", "未知"))
                count = c.get("count", 1)
                count_str = f"×{count}" if count > 1 else ""
                lines.append(f"  • {name}{count_str}")
            lines.append("")

        dc_info = enc.get("dc_info", {})
        if dc_info:
            lines.append("检定：")
            for skill, dc in dc_info.items():
                if isinstance(dc, (int, str)) and str(dc).isdigit():
                    lines.append(f"  • {skill}: DC {dc}")
                else:
                    lines.append(f"  • {skill}: {dc}")
            lines.append("")

        if enc.get("rewards"):
            lines.append(f"奖励（成功后）：{enc['rewards']}")

        return "\n".join(lines)
