"""场次管理（Session Management）

长团辅助：
1. 场次小结 — 每场结束归档，下一场开场注入
2. 剧情因果链 — 记录玩家重大选择及其后果
"""

import logging
import time
import json
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """场次管理器"""

    def __init__(self, state_mgr):
        self.state = state_mgr

    def _get_sessions(self) -> dict:
        data = self.state.get("sessions")
        if data is None:
            data = {
                "current_session": 0,
                "sessions": [],
                "choices": [],  # 剧情因果链
            }
            self.state.update({"sessions": data}, reason="初始化场次管理", actor="系统")
        return data

    def _save_sessions(self, data: dict, reason: str) -> None:
        self.state.update({"sessions": data}, reason=reason, actor="系统")

    # ================================================================
    # 场次管理
    # ================================================================

    def start_session(self, title: str = "") -> Dict[str, Any]:
        """开始一个新场次

        返回本场的基本信息
        """
        sessions = self._get_sessions()
        current = sessions.get("current_session", 0)
        next_num = current + 1

        session = {
            "number": next_num,
            "title": title or f"第 {next_num} 场",
            "start_time": time.strftime("%Y-%m-%d %H:%M"),
            "start_location": "",
            "end_time": "",
            "end_location": "",
            "summary": "",
            "key_events": [],
            "npc_changes": [],
            "quest_progress": [],
            "loot_gained": [],
            "xp_gained": 0,
            "gold_gained": 0,
            "next_session_hook": "",
        }

        sessions["current_session"] = next_num
        sessions["sessions"].append(session)
        self._save_sessions(sessions, f"开始第 {next_num} 场")

        return {
            "success": True,
            "session_number": next_num,
            "title": session["title"],
            "start_time": session["start_time"],
        }

    def end_session(self, summary: str = "", key_events: List[str] = None,
                   end_location: str = "", next_hook: str = "",
                   xp_gained: int = 0, gold_gained: int = 0,
                   loot: List[str] = None) -> Dict[str, Any]:
        """结束当前场次，填写小结

        Args:
            summary: 本场小结正文
            key_events: 关键事件列表（3-5条）
            end_location: 结束地点
            next_hook: 下一场开场提示
            xp_gained: 本场获得经验
            gold_gained: 本场获得金币
            loot: 获得的物品列表
        """
        sessions = self._get_sessions()
        current_num = sessions.get("current_session", 0)
        if current_num == 0 or not sessions.get("sessions"):
            return {"success": False, "error": "没有进行中的场次"}

        session = sessions["sessions"][-1]
        session["end_time"] = time.strftime("%Y-%m-%d %H:%M")
        session["end_location"] = end_location
        session["summary"] = summary
        session["key_events"] = key_events or []
        session["next_session_hook"] = next_hook
        session["xp_gained"] = xp_gained
        session["gold_gained"] = gold_gained
        session["loot_gained"] = loot or []

        self._save_sessions(sessions, f"结束第 {current_num} 场")

        # 场次结束保存命名快照（失败不阻塞场次标记，但记录以便排查）
        try:
            self.state.save_named_snapshot(
                f"session_end_{current_num}",
                reason=f"第{current_num}场结束"
            )
        except Exception as e:
            logger.warning(
                f"[sessions] 第{current_num}场结束快照保存失败: {type(e).__name__}: {e}"
            )

        return {
            "success": True,
            "session_number": current_num,
            "title": session["title"],
            "key_events_count": len(session["key_events"]),
        }

    def add_key_event(self, event: str) -> Dict[str, Any]:
        """给当前场次添加一条关键事件"""
        sessions = self._get_sessions()
        if not sessions.get("sessions"):
            return {"success": False, "error": "没有进行中的场次"}
        session = sessions["sessions"][-1]
        session.setdefault("key_events", []).append(event)
        self._save_sessions(sessions, f"添加场次事件: {event[:30]}")
        return {"success": True, "event": event}

    def get_current_session(self) -> Optional[Dict]:
        """获取当前场次"""
        sessions = self._get_sessions()
        if not sessions.get("sessions"):
            return None
        return sessions["sessions"][-1]

    def get_session(self, number: int) -> Optional[Dict]:
        """获取指定场次"""
        sessions = self._get_sessions()
        for s in sessions.get("sessions", []):
            if s["number"] == number:
                return s
        return None

    def list_sessions(self, limit: int = 10) -> List[Dict]:
        """列出最近场次"""
        sessions = self._get_sessions()
        all_sessions = sessions.get("sessions", [])
        return all_sessions[-limit:]

    def get_recap(self, sessions_back: int = 3) -> str:
        """生成前情提要（用于开场注入）

        包含：最近 N 场的小结 + 当前任务进度 + 上次结束位置
        """
        sessions = self._get_sessions()
        all_sessions = sessions.get("sessions", [])
        if not all_sessions:
            return ""

        recent = all_sessions[-sessions_back:]
        lines = []

        # 上一场结束位置 & 开场提示
        last = all_sessions[-1]
        if last.get("end_location"):
            lines.append(f"📍 上次结束位置: {last['end_location']}")
        if last.get("next_session_hook"):
            lines.append(f"📖 开场提示: {last['next_session_hook']}")
        lines.append("")

        # 最近场次摘要
        lines.append(f"📜 前情提要（最近 {len(recent)} 场）:")
        for s in recent:
            lines.append(f"  第{s['number']}场 - {s['title']}")
            if s.get("key_events"):
                for ev in s["key_events"][:3]:  # 每场最多 3 条
                    lines.append(f"    • {ev}")
            if s.get("summary") and not s.get("key_events"):
                lines.append(f"    {s['summary'][:80]}...")

        # 总场次
        lines.append("")
        lines.append(f"总计: {len(all_sessions)} 场")

        return "\n".join(lines)

    def session_count(self) -> int:
        """总场次"""
        sessions = self._get_sessions()
        return len(sessions.get("sessions", []))

    # ================================================================
    # 剧情因果链
    # ================================================================

    def add_choice(self, description: str, consequences: str = "",
                   impact_tags: List[str] = None,
                   related_quest: str = "",
                   related_npcs: List[str] = None,
                   importance: str = "normal") -> Dict[str, Any]:
        """记录一个重大选择及其后果

        Args:
            description: 玩家做了什么决定
            consequences: 直接后果
            impact_tags: 长期影响标签（如 "老比尔-敌对", "获得银护符"）
            related_quest: 相关任务 ID
            related_npcs: 相关 NPC 列表
            importance: trivial / normal / major / critical
        """
        sessions = self._get_sessions()
        choices = sessions.setdefault("choices", [])

        choice_id = f"ch-{len(choices) + 1}"
        entry = {
            "id": choice_id,
            "session": sessions.get("current_session", 0),
            "timestamp": time.strftime("%Y-%m-%d %H:%M"),
            "description": description,
            "consequences": consequences,
            "impact_tags": impact_tags or [],
            "related_quest": related_quest,
            "related_npcs": related_npcs or [],
            "importance": importance,
        }
        choices.append(entry)

        self._save_sessions(sessions, f"记录选择: {description[:30]}")
        return {"success": True, "choice_id": choice_id}

    def list_choices(self, importance_filter: str = "",
                     quest_filter: str = "",
                     limit: int = 20) -> List[Dict]:
        """列出选择记录"""
        sessions = self._get_sessions()
        choices = sessions.get("choices", [])

        result = choices
        if importance_filter:
            result = [c for c in result if c.get("importance") == importance_filter]
        if quest_filter:
            result = [c for c in result if c.get("related_quest") == quest_filter]

        return result[-limit:]

    def get_choice_timeline(self) -> str:
        """生成选择时间线（用于注入/回顾）"""
        sessions = self._get_sessions()
        choices = sessions.get("choices", [])
        if not choices:
            return ""

        lines = ["🔀 剧情选择时间线:"]
        # 只列 major 和 critical 的，避免太啰嗦
        important = [c for c in choices if c.get("importance") in ("major", "critical")]
        # 如果重要的太少，就把 normal 的也列上
        if len(important) < 3:
            important = choices[-5:]

        for c in important[-8:]:  # 最多 8 条
            marker = "⭐" if c.get("importance") == "critical" else ("⚡" if c.get("importance") == "major" else "•")
            lines.append(f"  {marker} 第{c['session']}场: {c['description']}")
            if c.get("consequences"):
                lines.append(f"     → {c['consequences']}")
            if c.get("impact_tags"):
                lines.append(f"     标签: {', '.join(c['impact_tags'])}")

        return "\n".join(lines)

    def get_impact_status(self) -> Dict[str, List[str]]:
        """获取当前影响状态汇总（按标签分组）

        返回 {"关系变化": [...], "物品获得": [...], "世界状态": [...]}
        """
        sessions = self._get_sessions()
        choices = sessions.get("choices", [])

        # 收集所有 impact_tag
        tags = []
        for c in choices:
            for tag in c.get("impact_tags", []):
                tags.append(tag)

        # 简单分类
        result = {"relationships": [], "items": [], "world": [], "other": []}
        for tag in tags:
            if any(kw in tag for kw in ["敌对", "友好", "关系", "结仇", "结盟"]):
                result["relationships"].append(tag)
            elif any(kw in tag for kw in ["获得", "失去", "物品", "护符"]):
                result["items"].append(tag)
            elif any(kw in tag for kw in ["开启", "关闭", "解锁", "触发"]):
                result["world"].append(tag)
            else:
                result["other"].append(tag)

        return result
