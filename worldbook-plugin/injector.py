"""上下文自动注入器（Context Injector）

pre_llm_call 钩子实现：每次 LLM 调用前，自动注入相关上下文。

注入内容包括（可配置开关）：
1. 世界书相关条目（基于对话内容检索）
2. 前情提要（编年史）
3. 当前任务状态
4. NPC 关系简要
5. 游戏时间与天气

所有注入组合成一段 Markdown 文本，追加到用户消息。
"""

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from .retriever import WorldBookRetriever
from .narrative import ChronicleManager, QuestManager, NPCManager, WorldClock
from .state import StateManager

logger = logging.getLogger(__name__)


class ContextInjector:
    """上下文自动注入器"""

    def __init__(self, retriever: WorldBookRetriever, state_mgr: StateManager,
                 config: Dict):
        self.retriever = retriever
        self.state_mgr = state_mgr
        self.config = config
        self._cache: Dict[str, tuple] = {}  # 世界书缓存

    # 叙事层 manager 统一从 app_context 获取（不再自建实例，杜绝与工具路径两套实例）

    @property
    def chronicle(self):
        from .app_context import get_app
        return get_app().chronicle

    @property
    def quests(self):
        from .app_context import get_app
        return get_app().quests

    @property
    def npcs(self):
        from .app_context import get_app
        return get_app().npcs

    @property
    def clock(self):
        from .app_context import get_app
        return get_app().clock

    @property
    def sessions(self):
        from .app_context import get_app
        return get_app().sessions

    def on_pre_llm_call(self, **kwargs) -> Optional[Dict]:
        """
        pre_llm_call 钩子回调

        Returns:
            {"context": "要注入的文本"} 或 None（不注入）
        """
        if not self.config.get("enabled", True):
            return None
        if not self.config.get("auto_inject", True):
            return None

        try:
            return self._do_inject(**kwargs)
        except Exception as e:
            logger.warning(f"[worldbook] 自动注入失败: {e}")
            return None

    def _do_inject(self, **kwargs) -> Optional[Dict]:
        user_message = kwargs.get("user_message", "")
        conversation_history = kwargs.get("conversation_history", [])

        query = self._build_search_query(user_message, conversation_history)
        max_chars = self.config.get("max_chars", 5000)

        # 按优先级从高到低排列（priority 越小越重要）
        # 每个 section: (priority, name, content_generator, max_share)
        # max_share 是该类别最多占用的字符数（占总配额的比例或绝对值）
        sections = []

        # P0: 战斗硬约束（战斗激活时，最高优先级的行为规范）
        combat_constraint = self._inject_combat_constraint()
        if combat_constraint:
            sections.append({"priority": 0, "name": "战斗约束",
                             "content": combat_constraint, "max_ratio": 0.10})

        # P0: 意图触发（行为约束：该检定/该攻击，多命中按规则顺序）
        try:
            from .intent import detect_intent
            intent_text = detect_intent(user_message, self.state_mgr.template_name)
            if intent_text:
                sections.append({"priority": 0, "name": "规则触发",
                                 "content": intent_text, "max_ratio": 0.10})
        except Exception as e:
            logger.debug(f"[worldbook] 意图触发注入失败: {e}")

        # P1: 当前任务状态（最精简，必须完整）
        if self.config.get("inject_quests", True):
            quest_text = self._inject_quests()
            if quest_text:
                sections.append({"priority": 1, "name": "任务",
                                 "content": quest_text, "max_ratio": 0.15})

        # P2: 世界书相关条目（当前场景信息，必须有）
        if self.config.get("inject_worldbook", True) and query:
            worldbook_text = self._inject_worldbook(query)
            if worldbook_text:
                sections.append({"priority": 2, "name": "世界书",
                                 "content": worldbook_text, "max_ratio": 0.40})

        # P3: 最近场次小结（3 场以内，必须有）
        if self.config.get("inject_recap", True):
            recap_text = self._inject_session_recap()
            if recap_text:
                sections.append({"priority": 3, "name": "前情提要",
                                 "content": recap_text, "max_ratio": 0.25})

        # P4: 剧情选择时间线（精简版）
        if self.config.get("inject_choices", True):
            choices_text = self._inject_choices()
            if choices_text:
                sections.append({"priority": 4, "name": "选择时间线",
                                 "content": choices_text, "max_ratio": 0.15})

        # P5: NPC 关系摘要
        if self.config.get("inject_npcs", False) and query:
            npc_text = self._inject_npcs(query)
            if npc_text:
                sections.append({"priority": 5, "name": "NPC 关系",
                                 "content": npc_text, "max_ratio": 0.15})

        # P6: 游戏时间与天气（最短，不占多少）
        if self.config.get("inject_time", False):
            time_text = self._inject_time()
            if time_text:
                sections.append({"priority": 6, "name": "时间",
                                 "content": time_text, "max_ratio": 0.05})

        if not sections:
            return None

        # 按优先级排序（高优先级在前）
        sections.sort(key=lambda s: s["priority"])

        # 智能分配配额：
        # 1. 先按 max_ratio 给每类分配上限
        # 2. 从高到低依次填入，剩余空间分给后面的
        remaining = max_chars
        output_parts = []
        used = 0

        for sec in sections:
            content = sec["content"]
            max_for_sec = int(max_chars * sec["max_ratio"])
            # 实际可用空间：上限和剩余空间中的较小值
            available = min(max_for_sec, remaining)

            if len(content) <= available:
                # 内容装得下，全放
                output_parts.append(content)
                used += len(content)
                remaining -= len(content)
            else:
                # 装不下，按句子边界截断（避免截在词中间产生幻觉），末尾加标记
                truncated = self._truncate_by_sentence(content, available - 15)
                output_parts.append(truncated + "\n...（已截断）")
                used += len(truncated)
                remaining = 0
                # 低优先级的就跳过了

        full_text = "\n\n".join(output_parts)

        logger.debug(f"[context-injector] 注入 {len(output_parts)}/{len(sections)} 段，"
                     f"{len(full_text)}/{max_chars} 字符")
        return {"context": full_text}

    @staticmethod
    def _truncate_by_sentence(content: str, max_len: int) -> str:
        """按句子边界截断，避免截断在词中间（减少 AI 因半句话产生的幻觉）

        在 max_len 范围内找最后一个句子边界（句号/问号/感叹号/换行/分号/逗号）。
        若边界太靠前（< 一半），说明单句本身超长，退化为硬切。
        """
        if len(content) <= max_len:
            return content
        head = content[:max_len]
        best = -1
        for ch in "。！？\n；;，,":
            pos = head.rfind(ch)
            if pos > best:
                best = pos
        if best >= int(max_len * 0.5):
            return content[:best + 1]  # 含边界符，句子完整
        return head  # 单句超长，退化为硬切

    # ----------------------------------------------------------------
    # 各 section 的注入方法
    # ----------------------------------------------------------------

    def _inject_worldbook(self, query: str) -> Optional[str]:
        """注入世界书相关条目"""
        cache_key = self._make_cache_key(query)
        cached = self._cache.get(cache_key)
        if cached:
            result_text, timestamp = cached
            if time.time() - timestamp < self.config.get("cache_ttl", 60):
                return result_text if result_text else None

        entries = self.retriever.search(
            query,
            worldbooks=self.config.get("enabled_books"),
            categories=self.config.get("categories") or None,
            limit=self.config.get("max_entries", 5),
        )

        if not entries:
            self._cache[cache_key] = ("", time.time())
            return None

        header = self.config.get("inject_header", "## 世界书相关设定")
        result = self.retriever.format_for_injection(entries, header=header)
        self._cache[cache_key] = (result, time.time())
        return result

    def _inject_recap(self) -> Optional[str]:
        """注入前情提要"""
        try:
            chron = self.chronicle
            chapters = chron.list_chapters()
            if not chapters:
                return None

            # 只在有完成章节或当前章节有事件时才注入
            has_content = False
            for ch in chapters:
                if ch.get("summary") or ch.get("highlights"):
                    has_content = True
                    break
            if not has_content:
                return None

            # 生成精简版前情（比 /chronicle recap 更短）
            lines = ["## 前情提要", ""]

            completed = [ch for ch in chapters if ch["status"] == "completed"]
            current = chron.get_current_chapter()

            # 已完成章节：只列标题 + 摘要（如果有）
            for ch in completed[-2:]:  # 最多最近 2 章
                lines.append(f"**{ch['title']}**（已完成）")
                if ch.get("summary"):
                    lines.append(f"  {ch['summary']}")
                elif ch.get("highlights"):
                    # 没有摘要就列 3 条最重要的
                    majors = [h for h in ch["highlights"] if h.get("importance") in ("important", "major")]
                    for hl in (majors + ch["highlights"])[:3]:
                        lines.append(f"  • {hl['event']}")
                lines.append("")

            # 当前章节：列关键事件
            if current and current.get("highlights"):
                lines.append(f"**当前：{current['title']}**")
                for hl in current["highlights"][-5:]:
                    icon = "⭐" if hl["importance"] in ("important", "major") else "•"
                    lines.append(f"  {icon} {hl['event']}")
                lines.append("")

            return "\n".join(lines).strip()
        except Exception as e:
            logger.debug(f"[recap] 注入失败: {e}")
            return None

    def _inject_combat_constraint(self) -> Optional[str]:
        """战斗硬约束（战斗激活时注入）

        最高优先级的行为规范：战斗数值必须走工具，不能口述。
        只在战斗激活时注入，非战斗不注入避免干扰。
        """
        try:
            state = self.state_mgr.get()
            if not isinstance(state, dict):
                return None
            combat = state.get("combat", {})
            if not isinstance(combat, dict) or not combat.get("active"):
                return None

            combat_name = combat.get("name", "遭遇战")
            round_num = combat.get("round", 1)
            turn = combat.get("current_turn", "?")

            constraint = f"""## ⚔️ 战斗进行中：{combat_name}（第 {round_num} 回合）

【战斗硬约束 — 必须遵守】
1. 所有战斗数值（伤害/HP/命中/豁免）必须通过 trpg_combat_* 工具或 trpg_check 工具完成，绝不可以直接口述数字。
2. 正确流程：先调用工具 → 拿到结果 → 用自然语言描述结果。
3. 如果玩家只是说话/移动/观察，没有数值变化，可以直接描述。
4. 回复末尾如有 [战斗数值校验警告]，说明上一轮疑似漏了工具调用，请立即补调用。

当前回合：{turn}
"""
            return constraint
        except Exception as e:
            logger.debug(f"[injector] 战斗约束注入失败: {e}")
            return None

    def _inject_quests(self) -> Optional[str]:
        """注入当前任务状态"""
        try:
            quests = self.quests
            active = quests.list_quests("in_progress")
            if not active:
                return None

            lines = ["## 当前任务", ""]
            for q in active[:5]:  # 最多 5 个进行中任务
                icon = "⭐" if q.get("type") == "main" else "📜"
                step_info = ""
                if q.get("current_step"):
                    for s in q.get("steps", []):
                        if s["id"] == q["current_step"]:
                            step_info = f"（当前: {s['title']}）"
                            break
                lines.append(f"{icon} **{q['title']}** {step_info}")

            return "\n".join(lines)
        except Exception as e:
            logger.debug(f"[quests] 注入失败: {e}")
            return None

    def _inject_time(self) -> Optional[str]:
        """注入游戏时间与天气"""
        try:
            clock = self.clock
            now = clock.now()
            return f"**游戏时间**：{now['formatted']}（{now['time_slot']}）｜天气：{now['weather']}｜季节：{now['season']}"
        except Exception as e:
            logger.debug(f"[time] 注入失败: {e}")
            return None

    def _inject_npcs(self, query: str) -> Optional[str]:
        """注入提到的 NPC 的态度和关系摘要"""
        try:
            npcs = self.npcs
            npc_list = npcs.list_npcs()
            if not npc_list:
                return None

            # 从查询中找提到的 NPC 名字
            query_lower = query.lower()
            mentioned = []
            for n in npc_list:
                name = n["name"]
                if name in query or name[:2] in query or name[-2:] in query:
                    mentioned.append(n)

            if not mentioned:
                return None

            lines = ["## NPC 关系", ""]
            for n in mentioned[:5]:
                lines.append(f"- **{n['name']}**：{n['attitude_icon']} {n['attitude_level']}（{n['attitude']:+d}），在 {n.get('location', '?')}")

            return "\n".join(lines)
        except Exception as e:
            logger.debug(f"[npcs] 注入失败: {e}")
            return None

    # ----------------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------------

    def _build_search_query(self, user_message: str,
                            conversation_history: List[Any]) -> str:
        """构造检索查询"""
        lookback = self.config.get("lookback_messages", 3)
        queries = []

        if user_message and user_message.strip():
            queries.append(user_message.strip())

        count = 0
        for msg in reversed(conversation_history):
            if count >= lookback - 1:
                break
            role = msg.get("role", "") if isinstance(msg, dict) else ""
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            if role == "user" and content and content.strip():
                if len(content.strip()) > 5:
                    queries.append(content.strip())
                    count += 1

        full_query = " ".join(queries)
        if len(full_query) > 500:
            full_query = full_query[:500]
        return full_query

    def _make_cache_key(self, query: str) -> str:
        """生成世界书缓存 key"""
        enabled_books = ",".join(self.config.get("enabled_books", []))
        raw = f"{query}|{enabled_books}|{self.config.get('max_entries', 5)}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def _inject_session_recap(self) -> Optional[str]:
        """注入场次前情提要（长团首选）"""
        try:
            sessions = self.sessions
            recap = sessions.get_recap(
                sessions_back=self.config.get("recap_sessions_back", 3))
            if not recap:
                # 没有场次记录时，退回到编年史 recap
                chron = self.chronicle
                chron_recap = chron.recap()
                if chron_recap and isinstance(chron_recap, str):
                    return self._format_section("📖 剧情前情", chron_recap)
                return None
            return self._format_section("📖 场次前情", recap)
        except Exception as e:
            logger.warning(f"[worldbook] 场次前情注入失败: {e}")
            return None

    def _inject_choices(self) -> Optional[str]:
        """注入剧情选择时间线"""
        try:
            sessions = self.sessions
            timeline = sessions.get_choice_timeline()
            if not timeline:
                return None
            return self._format_section("🔀 剧情选择", timeline)
        except Exception as e:
            logger.warning(f"[worldbook] 选择时间线注入失败: {e}")
            return None
