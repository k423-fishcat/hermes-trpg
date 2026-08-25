"""NPC 关系与动态系统

NPC 不只是木桩——有态度值、互动历史、日程、已知信息、个人目标。
"""

import time
from typing import Any, Dict, List, Optional


ATTITUDE_LEVELS = [
    (-100, -70, "敌对", "💀"),
    (-69, -30, "冷淡", "😒"),
    (-29, 29, "中立", "😐"),
    (30, 69, "友善", "😊"),
    (70, 100, "亲密", "💚"),
]


def get_attitude_level(attitude: int) -> tuple:
    """根据态度值返回等级和表情"""
    for lo, hi, label, icon in ATTITUDE_LEVELS:
        if lo <= attitude <= hi:
            return label, icon
    return "中立", "😐"


class NPCManager:
    """NPC 管理器"""

    def __init__(self, state_mgr):
        self.state = state_mgr

    def _get_npc(self, name: str) -> Optional[Dict]:
        npcs = self.state.get("npcs") or {}
        return npcs.get(name)

    def _save_npc(self, name: str, npc_data: dict, reason: str) -> None:
        npcs = self.state.get("npcs") or {}
        npcs[name] = npc_data
        self.state.update({"npcs": npcs}, reason=reason, actor="DM")

    def _ensure_npc(self, name: str) -> dict:
        """确保 NPC 存在，没有则创建"""
        npc = self._get_npc(name)
        if npc is None:
            npc = {
                "name": name,
                "location": "",
                "alive": True,
                "attitude": 0,
                "reputation": 0,
                "interactions": [],
                "schedule": {},
                "known_info": [],
                "goals": [],
                "statblock": None,  # 怪物 statblock 引用
            }
            self._save_npc(name, npc, f"新增 NPC 记录: {name}")
        # 确保所有字段都有
        npc.setdefault("attitude", 0)
        npc.setdefault("reputation", 0)
        npc.setdefault("interactions", [])
        npc.setdefault("schedule", {})
        npc.setdefault("known_info", [])
        npc.setdefault("goals", [])
        npc.setdefault("alive", True)
        npc.setdefault("statblock", None)
        return npc

    # ----------------------------------------------------------------
    # 基础信息
    # ----------------------------------------------------------------

    def list_npcs(self) -> List[Dict]:
        """列出所有 NPC"""
        npcs = self.state.get("npcs") or {}
        result = []
        for name, data in npcs.items():
            att = data.get("attitude", 0)
            level, icon = get_attitude_level(att)
            result.append({
                "name": name,
                "location": data.get("location", ""),
                "alive": data.get("alive", True),
                "attitude": att,
                "attitude_level": level,
                "attitude_icon": icon,
            })
        return result

    def get_npc(self, name: str) -> Optional[Dict]:
        """获取 NPC 完整档案"""
        npc = self._get_npc(name)
        if not npc:
            return None
        att = npc.get("attitude", 0)
        level, icon = get_attitude_level(att)
        result = dict(npc)
        result["attitude_level"] = level
        result["attitude_icon"] = icon
        return result

    def set_location(self, name: str, location: str) -> Dict[str, Any]:
        """设置 NPC 位置"""
        npc = self._ensure_npc(name)
        old_loc = npc.get("location", "")
        npc["location"] = location
        self._save_npc(name, npc, f"NPC 移动: {name} {old_loc} → {location}")
        return {"success": True, "name": name, "location": location}

    def set_alive(self, name: str, alive: bool = True) -> Dict[str, Any]:
        """设置 NPC 存活状态"""
        npc = self._ensure_npc(name)
        npc["alive"] = alive
        status = "存活" if alive else "死亡"
        self._save_npc(name, npc, f"NPC 状态变更: {name} → {status}")
        return {"success": True, "name": name, "alive": alive}

    def set_statblock(self, name: str, ref: str = "",
                      source: str = "bestiary",
                      custom_stats: Dict = None) -> Dict[str, Any]:
        """设置 NPC 的战斗 statblock 引用

        Args:
            name: NPC 名字
            ref: 怪物引用 ID（bestiary 里的 ID 或 SRD 怪物名）
            source: 来源 - "bestiary"（本地图鉴）或 "srd"（dnd-rules）
            custom_stats: 自定义属性覆盖（如血量不同、属性调整等）
        """
        npc = self._ensure_npc(name)
        statblock = {
            "ref": ref,
            "source": source,
            "custom_stats": custom_stats or {},
        }
        npc["statblock"] = statblock
        self._save_npc(name, npc, f"NPC 设置 statblock: {name} → {ref} ({source})")
        return {
            "success": True,
            "name": name,
            "statblock": statblock,
        }

    def get_statblock(self, name: str, bestiary=None) -> Optional[Dict]:
        """获取 NPC 的完整 statblock 数据

        如果有 bestiary 引用，会从图鉴里加载完整数据。
        """
        npc = self._get_npc(name)
        if not npc:
            return None

        sb = npc.get("statblock")
        if not sb:
            return None

        ref = sb.get("ref", "")
        source = sb.get("source", "bestiary")
        custom = sb.get("custom_stats", {})

        base_stats = {}
        if source == "bestiary" and bestiary and ref:
            monster = bestiary.get_monster(ref)
            if monster:
                base_stats = monster

        # 合并自定义属性
        result = {**base_stats, **custom}
        result["npc_name"] = name
        result["ref"] = ref
        result["source"] = source
        return result

    # ----------------------------------------------------------------
    # 态度与关系
    # ----------------------------------------------------------------

    def change_attitude(self, name: str, delta: int, reason: str = "") -> Dict[str, Any]:
        """改变 NPC 对玩家的态度"""
        npc = self._ensure_npc(name)
        old_att = npc.get("attitude", 0)
        new_att = max(-100, min(100, old_att + delta))
        npc["attitude"] = new_att

        old_level = get_attitude_level(old_att)[0]
        new_level, icon = get_attitude_level(new_att)
        level_changed = old_level != new_level

        self._save_npc(name, npc,
                       f"态度变化: {name} {old_att:+d} → {new_att:+d}（{reason}）")
        return {
            "success": True,
            "name": name,
            "old_attitude": old_att,
            "new_attitude": new_att,
            "delta": delta,
            "level": new_level,
            "icon": icon,
            "level_changed": level_changed,
        }

    def get_attitude(self, name: str) -> Dict[str, Any]:
        """获取 NPC 态度信息"""
        npc = self._get_npc(name)
        if not npc:
            return {"success": False, "error": f"NPC 不存在: {name}"}
        att = npc.get("attitude", 0)
        level, icon = get_attitude_level(att)
        return {"success": True, "attitude": att, "level": level, "icon": icon}

    # ----------------------------------------------------------------
    # 互动记录
    # ----------------------------------------------------------------

    def add_interaction(self, name: str, itype: str, summary: str,
                        attitude_delta: int = 0) -> Dict[str, Any]:
        """记录一次互动

        itype: conversation / combat / trade / favor / betrayal / quest_give / quest_complete
        """
        npc = self._ensure_npc(name)

        interaction = {
            "time": time.time(),
            "type": itype,
            "summary": summary,
            "attitude_delta": attitude_delta,
        }
        npc.setdefault("interactions", []).append(interaction)
        # 只保留最近 50 条
        if len(npc["interactions"]) > 50:
            npc["interactions"] = npc["interactions"][-50:]

        # 应用态度变化
        if attitude_delta != 0:
            old_att = npc.get("attitude", 0)
            npc["attitude"] = max(-100, min(100, old_att + attitude_delta))

        self._save_npc(name, npc, f"互动记录: {name} - {summary[:30]}")
        return {"success": True, "name": name, "interaction": interaction}

    def list_interactions(self, name: str, limit: int = 10) -> List[Dict]:
        """列出最近互动"""
        npc = self._get_npc(name)
        if not npc:
            return []
        interactions = npc.get("interactions", [])
        return list(reversed(interactions[-limit:]))

    # ----------------------------------------------------------------
    # 已知信息
    # ----------------------------------------------------------------

    def add_known_info(self, name: str, info: str) -> Dict[str, Any]:
        """记录 NPC 知道了什么信息"""
        npc = self._ensure_npc(name)
        known = npc.setdefault("known_info", [])
        if info in known:
            return {"success": False, "error": "NPC 已经知道了"}
        known.append(info)
        self._save_npc(name, npc, f"NPC 获知信息: {name} 得知 {info[:30]}")
        return {"success": True, "name": name, "info": info}

    # ----------------------------------------------------------------
    # 个人目标
    # ----------------------------------------------------------------

    def add_goal(self, name: str, goal_text: str, priority: int = 50) -> Dict[str, Any]:
        """添加 NPC 个人目标"""
        npc = self._ensure_npc(name)
        goal_id = f"g{len(npc.get('goals', [])) + 1}"
        goal = {
            "id": goal_id,
            "text": goal_text,
            "priority": priority,
            "status": "active",   # active / completed / abandoned
            "created_time": time.time(),
        }
        npc.setdefault("goals", []).append(goal)
        self._save_npc(name, npc, f"NPC 目标: {name} - {goal_text[:30]}")
        return {"success": True, "goal_id": goal_id, "text": goal_text}

    def complete_goal(self, name: str, goal_id: str) -> Dict[str, Any]:
        """标记目标完成"""
        npc = self._ensure_npc(name)
        for g in npc.get("goals", []):
            if g["id"] == goal_id:
                g["status"] = "completed"
                g["completed_time"] = time.time()
                self._save_npc(name, npc, f"NPC 目标完成: {name} - {g['text'][:30]}")
                return {"success": True, "goal_id": goal_id}
        return {"success": False, "error": f"未找到目标: {goal_id}"}

    # ----------------------------------------------------------------
    # 日程
    # ----------------------------------------------------------------

    def set_schedule(self, name: str, time_slot: str, activity: str) -> Dict[str, Any]:
        """设置 NPC 日程

        time_slot: morning / afternoon / evening / night
        """
        npc = self._ensure_npc(name)
        npc.setdefault("schedule", {})[time_slot] = activity
        self._save_npc(name, npc, f"NPC 日程更新: {name} - {time_slot}")
        return {"success": True, "time_slot": time_slot, "activity": activity}

    def get_schedule(self, name: str) -> Dict[str, str]:
        """获取 NPC 日程"""
        npc = self._get_npc(name)
        if not npc:
            return {}
        return npc.get("schedule", {})
