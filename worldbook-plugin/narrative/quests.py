"""任务推进系统（Quest Engine）

结构化管理任务，支持多步骤、触发条件、任务依赖。
"""

import time
from typing import Any, Dict, List, Optional


STATUS_ORDER = {
    "hidden": 0,      # 隐藏（还没发现）
    "available": 1,   # 可接取
    "in_progress": 2, # 进行中
    "completed": 3,   # 已完成
    "failed": 4,      # 已失败
}

STATUS_LABEL = {
    "hidden": "隐藏",
    "available": "可接取",
    "in_progress": "进行中",
    "completed": "已完成",
    "failed": "已失败",
}


class QuestManager:
    """任务管理器"""

    def __init__(self, state_mgr):
        self.state = state_mgr

    def _get_quests(self) -> dict:
        quests = self.state.get("quests")
        return quests or {}

    def _save_quests(self, quests: dict, reason: str) -> None:
        self.state.update({"quests": quests}, reason=reason, actor="DM")

    # ----------------------------------------------------------------
    # 任务管理
    # ----------------------------------------------------------------

    def add_quest(self, quest_id: str, title: str, description: str = "",
                  quest_type: str = "side", giver: str = "",
                  rewards: str = "", steps: List[Dict] = None,
                  prerequisites: List[str] = None,
                  triggers: List[Dict] = None) -> Dict[str, Any]:
        """添加新任务"""
        quests = self._get_quests()
        if quest_id in quests:
            return {"success": False, "error": f"任务 {quest_id} 已存在"}

        step_list = steps or []
        # 如果有步骤，第一个为当前步骤
        current_step = step_list[0]["id"] if step_list else None

        quest = {
            "id": quest_id,
            "title": title,
            "description": description,
            "type": quest_type,       # main / side / hidden / personal
            "status": "available",    # hidden / available / in_progress / completed / failed
            "giver": giver,
            "rewards": rewards,
            "steps": step_list,
            "current_step": current_step,
            "prerequisites": prerequisites or [],
            "triggers": triggers or [],
            "started_time": None,
            "completed_time": None,
            "notes": [],
        }

        quests[quest_id] = quest
        self._save_quests(quests, f"新增任务: {title}")
        return {"success": True, "quest_id": quest_id, "title": title}

    def start_quest(self, quest_id: str) -> Dict[str, Any]:
        """开始任务"""
        quests = self._get_quests()
        if quest_id not in quests:
            return {"success": False, "error": f"任务不存在: {quest_id}"}

        q = quests[quest_id]
        if q["status"] == "in_progress":
            return {"success": False, "error": f"任务已在进行中"}
        if q["status"] == "completed":
            return {"success": False, "error": f"任务已经完成了"}

        # 检查前置
        for pre in q.get("prerequisites", []):
            pre_q = quests.get(pre)
            if not pre_q or pre_q.get("status") != "completed":
                return {"success": False, "error": f"前置任务未完成: {pre}"}

        q["status"] = "in_progress"
        q["started_time"] = time.time()
        # 如果有步骤，第一步设为进行中
        if q.get("steps"):
            q["steps"][0]["status"] = "in_progress"
            q["current_step"] = q["steps"][0]["id"]

        self._save_quests(quests, f"开始任务: {q['title']}")
        return {"success": True, "quest_id": quest_id, "title": q["title"]}

    def advance_step(self, quest_id: str) -> Dict[str, Any]:
        """推进到下一步"""
        quests = self._get_quests()
        if quest_id not in quests:
            return {"success": False, "error": f"任务不存在: {quest_id}"}

        q = quests[quest_id]
        if q["status"] != "in_progress":
            return {"success": False, "error": f"任务不在进行中（当前: {q['status']}）"}

        steps = q.get("steps", [])
        if not steps:
            return {"success": False, "error": "此任务没有步骤设置"}

        current_id = q.get("current_step")
        # 找到当前步骤的索引
        current_idx = -1
        for i, s in enumerate(steps):
            if s["id"] == current_id:
                current_idx = i
                break

        if current_idx < 0:
            # 没找到，从第一步开始
            current_idx = 0

        # 完成当前步骤
        steps[current_idx]["status"] = "completed"

        # 推进到下一步
        next_idx = current_idx + 1
        if next_idx >= len(steps):
            # 没有下一步了，任务完成
            q["current_step"] = None
            self._save_quests(quests, f"任务步骤完成（最后一步）: {q['title']}")
            return {"success": True, "all_done": True, "message": "所有步骤已完成！"}

        steps[next_idx]["status"] = "in_progress"
        q["current_step"] = steps[next_idx]["id"]

        self._save_quests(quests,
                         f"任务推进: {q['title']} → {steps[next_idx]['title']}")
        return {
            "success": True,
            "all_done": False,
            "step_id": steps[next_idx]["id"],
            "step_title": steps[next_idx]["title"],
            "step_description": steps[next_idx].get("description", ""),
        }

    def set_step(self, quest_id: str, step_id: str) -> Dict[str, Any]:
        """跳转到指定步骤（不按顺序）"""
        quests = self._get_quests()
        if quest_id not in quests:
            return {"success": False, "error": f"任务不存在: {quest_id}"}

        q = quests[quest_id]
        steps = q.get("steps", [])

        for s in steps:
            if s["id"] == step_id:
                s["status"] = "in_progress"
                q["current_step"] = step_id
                self._save_quests(quests, f"任务跳转: {q['title']} → {s['title']}")
                return {"success": True, "step_id": step_id, "title": s["title"]}

        return {"success": False, "error": f"步骤不存在: {step_id}"}

    def complete_quest(self, quest_id: str, notes: str = "") -> Dict[str, Any]:
        """完成任务"""
        quests = self._get_quests()
        if quest_id not in quests:
            return {"success": False, "error": f"任务不存在: {quest_id}"}

        q = quests[quest_id]
        q["status"] = "completed"
        q["completed_time"] = time.time()
        # 所有步骤标为完成
        for s in q.get("steps", []):
            s["status"] = "completed"
        if notes:
            q.setdefault("notes", []).append({
                "time": time.time(),
                "text": notes,
                "type": "completion",
            })

        self._save_quests(quests, f"完成任务: {q['title']}")
        return {
            "success": True,
            "quest_id": quest_id,
            "title": q["title"],
            "rewards": q.get("rewards", ""),
        }

    def fail_quest(self, quest_id: str, reason: str = "") -> Dict[str, Any]:
        """任务失败"""
        quests = self._get_quests()
        if quest_id not in quests:
            return {"success": False, "error": f"任务不存在: {quest_id}"}

        q = quests[quest_id]
        q["status"] = "failed"
        if reason:
            q.setdefault("notes", []).append({
                "time": time.time(),
                "text": f"失败原因: {reason}",
                "type": "failure",
            })

        self._save_quests(quests, f"任务失败: {q['title']} — {reason}")
        return {"success": True, "quest_id": quest_id, "reason": reason}

    def list_quests(self, status_filter: str = "") -> List[Dict]:
        """列出任务，可选按状态过滤"""
        quests = self._get_quests()
        result = list(quests.values())
        if status_filter:
            result = [q for q in result if q.get("status") == status_filter]
        # 按状态优先级 + 类型排序
        result.sort(key=lambda q: (
            STATUS_ORDER.get(q.get("status", ""), 99),
            0 if q.get("type") == "main" else 1,
        ))
        return result

    def get_quest(self, quest_id: str) -> Optional[Dict]:
        """获取任务详情"""
        quests = self._get_quests()
        return quests.get(quest_id)

    # ----------------------------------------------------------------
    # 触发检查
    # ----------------------------------------------------------------

    def check_triggers(self) -> List[Dict]:
        """检查所有任务的触发条件，返回新解锁的任务"""
        quests = self._get_quests()
        newly_available = []

        for qid, q in quests.items():
            if q.get("status") != "hidden":
                continue

            triggers = q.get("triggers", [])
            if not triggers:
                continue

            # 任意一个触发条件满足就算触发
            triggered = False
            for t in triggers:
                ttype = t.get("type", "")

                if ttype == "flag":
                    flag = t.get("flag", "")
                    expected = t.get("value", True)
                    actual = self.state.get(f"world.{flag}")
                    if actual == expected:
                        triggered = True
                        break

                elif ttype == "quest_completed":
                    req_id = t.get("quest_id", "")
                    req_q = quests.get(req_id)
                    if req_q and req_q.get("status") == "completed":
                        triggered = True
                        break

                elif ttype == "item_in_inventory":
                    item_name = t.get("item", "")
                    inv = self.state.get("inventory") or []
                    if any(i.get("name") == item_name for i in inv):
                        triggered = True
                        break

                elif ttype == "npc_attitude":
                    npc_name = t.get("npc", "")
                    min_att = t.get("min_attitude", 0)
                    npc = self.state.get(f"npcs.{npc_name}") or {}
                    att = npc.get("attitude", 0)
                    if att >= min_att:
                        triggered = True
                        break

            if triggered:
                q["status"] = "available"
                newly_available.append({
                    "quest_id": qid,
                    "title": q["title"],
                    "type": q.get("type", ""),
                })

        if newly_available:
            self._save_quests(quests, f"新任务解锁: {[q['title'] for q in newly_available]}")

        return newly_available
