"""剧情编年史管理（Chronicle）

记录冒险中发生的重要事件，按章节组织，提供前情提要。
所有数据通过 StateManager 存储，走同一套版本/回滚机制。
"""

import time
from typing import Any, Dict, List, Optional


class ChronicleManager:
    """剧情编年史管理器"""

    def __init__(self, state_mgr):
        self.state = state_mgr

    def _ensure_chronicle(self) -> dict:
        """确保 chronicle 结构存在（内部用）"""
        chron = self.state.get("chronicle")
        if chron is None:
            chron = {
                "chapters": [],
                "current_chapter": None,
                "highlights": [],
            }
            self.state.update({"chronicle": chron}, reason="初始化编年史", actor="系统")
            return chron
        return chron

    def get_chronicle(self) -> dict:
        """获取编年史结构（公共只读访问）"""
        return self._ensure_chronicle()

    def is_current_chapter(self, chapter_id: str) -> bool:
        """判断指定章节是否当前章节（供外部只读判断）"""
        return chapter_id == self._ensure_chronicle().get("current_chapter")

    # ----------------------------------------------------------------
    # 章节管理
    # ----------------------------------------------------------------

    def new_chapter(self, title: str, description: str = "") -> Dict[str, Any]:
        """开启新章节"""
        chron = self._ensure_chronicle()

        # 如果有当前章节，先结束
        if chron.get("current_chapter"):
            self.end_chapter("（自动结束，开启新章节）")
            chron = self._ensure_chronicle()

        chapter_id = f"ch{len(chron['chapters']) + 1}"
        chapter = {
            "id": chapter_id,
            "title": title,
            "description": description,
            "start_time": time.time(),
            "end_time": None,
            "summary": "",
            "highlights": [],
            "milestones": [],        # 章节里程碑
            "npcs_changed": [],      # NPC 态度/状态变化
            "items_obtained": [],    # 获得的重要物品
            "world_changes": [],     # 世界变化（新区域解锁、势力变化等）
            "level_ups": [],         # 升级记录
            "choices_made": [],      # 重大选择
            "status": "in_progress",
        }
        chron["chapters"].append(chapter)
        chron["current_chapter"] = chapter_id

        self.state.update({"chronicle": chron},
                         reason=f"新章节：{title}", actor="DM")
        return {"success": True, "chapter_id": chapter_id, "title": title}

    def end_chapter(self, summary: str = "") -> Dict[str, Any]:
        """结束当前章节"""
        chron = self._ensure_chronicle()
        current_id = chron.get("current_chapter")
        if not current_id:
            return {"success": False, "error": "没有进行中的章节"}

        for ch in chron["chapters"]:
            if ch["id"] == current_id:
                ch["status"] = "completed"
                ch["end_time"] = time.time()
                ch["summary"] = summary or ch.get("summary", "")
                break

        chron["current_chapter"] = None

        self.state.update({"chronicle": chron},
                         reason=f"章节结束：{current_id}", actor="DM")
        return {"success": True, "chapter_id": current_id, "summary": summary}

    def list_chapters(self) -> List[Dict]:
        """列出所有章节"""
        chron = self._ensure_chronicle()
        return chron.get("chapters", [])

    def get_current_chapter(self) -> Optional[Dict]:
        """获取当前章节"""
        chron = self._ensure_chronicle()
        current_id = chron.get("current_chapter")
        if not current_id:
            return None
        for ch in chron["chapters"]:
            if ch["id"] == current_id:
                return ch
        return None

    # ----------------------------------------------------------------
    # 大事记
    # ----------------------------------------------------------------

    def add_event(self, event: str, importance: str = "normal") -> Dict[str, Any]:
        """记录一件大事

        importance: trivial / normal / important / major
        """
        chron = self._ensure_chronicle()

        entry = {
            "time": time.time(),
            "event": event,
            "importance": importance,
        }

        # 添加到当前章节
        current_id = chron.get("current_chapter")
        if current_id:
            for ch in chron["chapters"]:
                if ch["id"] == current_id:
                    ch["highlights"].append(entry)
                    break

        chron.setdefault("highlights", []).append(entry)
        # 全局保留最近 100 条
        if len(chron["highlights"]) > 100:
            chron["highlights"] = chron["highlights"][-100:]

        self.state.update({"chronicle": chron},
                         reason=f"记录事件：{event[:30]}", actor="DM")
        return {"success": True, "event": event, "importance": importance}

    # ----------------------------------------------------------------
    # 前情提要
    # ----------------------------------------------------------------

    def recap(self, include_current: bool = True,
              max_chapters: int = 3, max_highlights: int = 10) -> str:
        """生成前情提要文本"""
        chron = self._ensure_chronicle()
        chapters = chron.get("chapters", [])

        if not chapters:
            return "（冒险尚未开始）"

        lines = ["📜 前情提要", "=" * 30, ""]

        # 取最近几个完成的章节 + 当前章节
        completed = [ch for ch in chapters if ch["status"] == "completed"]
        current = self.get_current_chapter()

        recent_completed = completed[-(max_chapters - 1):] if include_current else completed[-max_chapters:]

        for ch in recent_completed:
            lines.append(f"【{ch['title']}】（已完成）")
            if ch.get("summary"):
                lines.append(f"  {ch['summary']}")
            else:
                # 没有摘要就列大事记
                for hl in ch.get("highlights", [])[-5:]:
                    icon = "⭐" if hl["importance"] in ("important", "major") else "•"
                    lines.append(f"  {icon} {hl['event']}")
            lines.append("")

        if include_current and current:
            lines.append(f"【{current['title']}】（进行中）")
            if current.get("description"):
                lines.append(f"  {current['description']}")
            if current.get("highlights"):
                lines.append("  关键事件：")
                for hl in current["highlights"][-max_highlights:]:
                    icon = "⭐" if hl["importance"] in ("important", "major") else "•"
                    lines.append(f"    {icon} {hl['event']}")
            lines.append("")

        return "\n".join(lines)

    def search_events(self, keyword: str) -> List[Dict]:
        """在编年史中搜索关键词"""
        chron = self._ensure_chronicle()
        keyword_lower = keyword.lower()
        results = []
        for ch in chron.get("chapters", []):
            for hl in ch.get("highlights", []):
                if keyword_lower in hl["event"].lower():
                    results.append({
                        "chapter": ch["title"],
                        "chapter_id": ch["id"],
                        "event": hl["event"],
                        "importance": hl["importance"],
                        "time": hl["time"],
                    })
        return results

    # ----------------------------------------------------------------
    # 章节里程碑
    # ----------------------------------------------------------------

    def add_milestone(self, title: str, description: str = "",
                      milestone_type: str = "objective") -> Dict[str, Any]:
        """添加章节里程碑（阶段目标/关键节点）

        milestone_type: objective / turning_point / climax / resolution
        """
        chron = self._ensure_chronicle()
        current = self.get_current_chapter()
        if not current:
            return {"success": False, "error": "没有进行中的章节"}

        mid = f"ms{len(current.get('milestones', [])) + 1}"
        milestone = {
            "id": mid,
            "title": title,
            "description": description,
            "type": milestone_type,
            "status": "pending",  # pending / in_progress / completed / failed
            "completed_at": None,
        }
        current["milestones"].append(milestone)

        # 存回 chron
        for ch in chron["chapters"]:
            if ch["id"] == current["id"]:
                ch["milestones"] = current["milestones"]
                break

        self.state.update({f"chronicle": chron},
                         reason=f"添加里程碑：{title}", actor="DM")
        return {"success": True, "milestone_id": mid, "title": title}

    def update_milestone(self, milestone_id: str, status: str = "completed",
                         note: str = "") -> Dict[str, Any]:
        """更新里程碑状态

        status: pending / in_progress / completed / failed
        """
        chron = self._ensure_chronicle()
        current = self.get_current_chapter()
        if not current:
            return {"success": False, "error": "没有进行中的章节"}

        for ms in current.get("milestones", []):
            if ms["id"] == milestone_id:
                ms["status"] = status
                if status in ("completed", "failed"):
                    ms["completed_at"] = time.time()
                    ms["completion_note"] = note
                break
        else:
            return {"success": False, "error": f"里程碑不存在：{milestone_id}"}

        # 存回
        for ch in chron["chapters"]:
            if ch["id"] == current["id"]:
                ch["milestones"] = current["milestones"]
                break

        self.state.update({f"chronicle": chron},
                         reason=f"里程碑更新：{milestone_id} → {status}", actor="DM")
        return {"success": True, "milestone_id": milestone_id, "status": status}

    # ----------------------------------------------------------------
    # 章节结构化记录（用于生成阶段总结）
    # ----------------------------------------------------------------

    def record_npc_change(self, npc_name: str, change: str,
                          attitude_shift: int = 0) -> Dict[str, Any]:
        """记录 NPC 在本章中的变化"""
        chron = self._ensure_chronicle()
        current = self.get_current_chapter()
        if not current:
            return {"success": False, "error": "没有进行中的章节"}

        entry = {
            "npc": npc_name,
            "change": change,
            "attitude_shift": attitude_shift,
            "time": time.time(),
        }
        current.setdefault("npcs_changed", []).append(entry)

        for ch in chron["chapters"]:
            if ch["id"] == current["id"]:
                ch["npcs_changed"] = current["npcs_changed"]
                break

        self.state.update({f"chronicle": chron},
                         reason=f"NPC变化：{npc_name}", actor="DM")
        return {"success": True, "npc": npc_name, "change": change}

    def record_item_obtained(self, item_name: str, source: str = "",
                             importance: str = "normal") -> Dict[str, Any]:
        """记录本章获得的重要物品"""
        chron = self._ensure_chronicle()
        current = self.get_current_chapter()
        if not current:
            return {"success": False, "error": "没有进行中的章节"}

        entry = {
            "item": item_name,
            "source": source,
            "importance": importance,
            "time": time.time(),
        }
        current.setdefault("items_obtained", []).append(entry)

        for ch in chron["chapters"]:
            if ch["id"] == current["id"]:
                ch["items_obtained"] = current["items_obtained"]
                break

        self.state.update({f"chronicle": chron},
                         reason=f"获得物品：{item_name}", actor="DM")
        return {"success": True, "item": item_name}

    def record_world_change(self, change: str,
                            change_type: str = "other") -> Dict[str, Any]:
        """记录世界状态变化（新区域解锁、势力变化、灾难等）

        change_type: location_unlocked / faction_shift / disaster / discovery / other
        """
        chron = self._ensure_chronicle()
        current = self.get_current_chapter()
        if not current:
            return {"success": False, "error": "没有进行中的章节"}

        entry = {
            "change": change,
            "type": change_type,
            "time": time.time(),
        }
        current.setdefault("world_changes", []).append(entry)

        for ch in chron["chapters"]:
            if ch["id"] == current["id"]:
                ch["world_changes"] = current["world_changes"]
                break

        self.state.update({f"chronicle": chron},
                         reason=f"世界变化：{change[:30]}", actor="DM")
        return {"success": True, "change": change}

    def record_level_up(self, character: str, from_level: int,
                        to_level: int, details: str = "") -> Dict[str, Any]:
        """记录升级"""
        chron = self._ensure_chronicle()
        current = self.get_current_chapter()
        if not current:
            return {"success": False, "error": "没有进行中的章节"}

        entry = {
            "character": character,
            "from_level": from_level,
            "to_level": to_level,
            "details": details,
            "time": time.time(),
        }
        current.setdefault("level_ups", []).append(entry)

        for ch in chron["chapters"]:
            if ch["id"] == current["id"]:
                ch["level_ups"] = current["level_ups"]
                break

        self.state.update({f"chronicle": chron},
                         reason=f"升级：{character} Lv{from_level}→{to_level}", actor="DM")
        return {"success": True, "character": character, "to_level": to_level}

    def record_chapter_choice(self, choice: str, consequence: str,
                              importance: str = "major") -> Dict[str, Any]:
        """记录本章中的重大选择（和剧情因果链联动，但存在章节里方便总结）"""
        chron = self._ensure_chronicle()
        current = self.get_current_chapter()
        if not current:
            return {"success": False, "error": "没有进行中的章节"}

        entry = {
            "choice": choice,
            "consequence": consequence,
            "importance": importance,
            "time": time.time(),
        }
        current.setdefault("choices_made", []).append(entry)

        for ch in chron["chapters"]:
            if ch["id"] == current["id"]:
                ch["choices_made"] = current["choices_made"]
                break

        self.state.update({f"chronicle": chron},
                         reason=f"重大选择：{choice[:30]}", actor="DM")
        return {"success": True, "choice": choice}

    # ----------------------------------------------------------------
    # 章节总结（结构化回顾）
    # ----------------------------------------------------------------

    def chapter_review(self, chapter_id: str = None) -> str:
        """生成章节结构化回顾（阶段总结）

        包含：章节概述 / 关键事件 / 里程碑 / NPC变化 / 物品 / 世界变化 / 升级 / 重大选择
        """
        chron = self._ensure_chronicle()

        # 指定章节或当前章节
        target = None
        if chapter_id:
            for ch in chron.get("chapters", []):
                if ch["id"] == chapter_id:
                    target = ch
                    break
        else:
            target = self.get_current_chapter()

        if not target:
            return "（找不到该章节）"

        status_label = "进行中" if target["status"] == "in_progress" else "已完成"
        lines = [
            f"📖 章节回顾：{target['title']}",
            f"{'=' * 40}",
            f"状态：{status_label}",
        ]

        if target.get("description"):
            lines.append(f"简介：{target['description']}")
        lines.append("")

        # 里程碑
        milestones = target.get("milestones", [])
        if milestones:
            lines.append(f"🏁 章节目标（{sum(1 for m in milestones if m['status']=='completed')}/{len(milestones)} 完成）")
            for ms in milestones:
                icon = {"completed": "✅", "failed": "❌",
                        "in_progress": "🔄", "pending": "⬜"}.get(ms["status"], "⬜")
                lines.append(f"  {icon} [{ms['id']}] {ms['title']}")
                if ms.get("description"):
                    lines.append(f"     {ms['description']}")
            lines.append("")

        # 关键事件
        highlights = target.get("highlights", [])
        if highlights:
            major_events = [h for h in highlights if h["importance"] in ("important", "major")]
            if major_events:
                lines.append(f"⭐ 关键事件")
                for hl in major_events:
                    lines.append(f"  • {hl['event']}")
                lines.append("")

        # 重大选择
        choices = target.get("choices_made", [])
        if choices:
            lines.append(f"🔀 重大选择（{len(choices)}）")
            for c in choices:
                imp = "" if c["importance"] == "normal" else f" [{c['importance']}]"
                lines.append(f"  选择：{c['choice']}{imp}")
                lines.append(f"  后果：{c['consequence']}")
                lines.append("")

        # NPC 变化
        npcs = target.get("npcs_changed", [])
        if npcs:
            lines.append(f"👤 NPC 关系变化（{len(npcs)}）")
            for n in npcs:
                shift = ""
                if n.get("attitude_shift"):
                    shift = f" ({'+' if n['attitude_shift'] > 0 else ''}{n['attitude_shift']})"
                lines.append(f"  • {n['npc']}{shift}：{n['change']}")
            lines.append("")

        # 重要物品
        items = target.get("items_obtained", [])
        if items:
            important_items = [i for i in items if i["importance"] in ("important", "major")]
            if important_items:
                lines.append(f"🎒 重要物品获得（{len(important_items)}）")
                for i in important_items:
                    src = f"（来自{i['source']}）" if i.get("source") else ""
                    lines.append(f"  • {i['item']} {src}")
                lines.append("")

        # 世界变化
        world = target.get("world_changes", [])
        if world:
            lines.append(f"🌍 世界变化（{len(world)}）")
            for w in world:
                lines.append(f"  • [{w['type']}] {w['change']}")
            lines.append("")

        # 升级
        level_ups = target.get("level_ups", [])
        if level_ups:
            lines.append(f"📈 成长（{len(level_ups)}）")
            for lu in level_ups:
                lines.append(f"  • {lu['character']}：Lv{lu['from_level']} → Lv{lu['to_level']}")
                if lu.get("details"):
                    lines.append(f"    {lu['details']}")
            lines.append("")

        # 章节总结（如果有的话）
        if target.get("summary") and target["status"] == "completed":
            lines.append("📝 章节总结")
            lines.append(f"  {target['summary']}")
            lines.append("")

        return "\n".join(lines)
