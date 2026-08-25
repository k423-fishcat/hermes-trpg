"""叙事层工具（编年史 / 任务 / NPC / 时间）— 18 个工具"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


def register(reg: ToolRegistry, chron, quests, npcs, clock):
    # ================================================================
    # 编年史（chron）
    # ================================================================
    @reg.tool(
        name="trpg_recap",
        description="获取前情提要，返回目前为止的剧情摘要和当前章节关键事件。",
        schema={"name": "trpg_recap", "parameters": _NO_PARAMS},
        emoji="📜",
    )
    def recap(args):
        return chron.recap()

    @reg.tool(
        name="trpg_log_event",
        description="记录一件大事到编年史。重要事件要记录，普通对话不用。",
        schema={
            "name": "trpg_log_event",
            "parameters": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "description": "事件描述"},
                    "importance": {"type": "string", "description": "重要程度：normal/important/major", "default": "normal"},
                },
                "required": ["event"],
            },
        },
        emoji="📝",
    )
    def log_event(args):
        r = chron.add_event(args.get("event", ""), args.get("importance", "normal"))
        icon = {"important": "⭐", "major": "🌟"}.get(args.get("importance", "normal"), "•")
        return f"{icon} 已记录: {args.get('event', '')}"

    @reg.tool(
        name="trpg_new_chapter",
        description="开启新章节。进入新的大场景/新阶段时调用，会自动结束当前章节。",
        schema={
            "name": "trpg_new_chapter",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "章节标题，如 '第二章：迷雾森林'"},
                    "description": {"type": "string", "description": "章节简介", "default": ""},
                },
                "required": ["title"],
            },
        },
        emoji="📖",
    )
    def new_chapter(args):
        r = chron.new_chapter(args.get("title", ""), args.get("description", ""))
        if not r.get("success"):
            return f"❌ {r.get('error')}"
        return f"📖 新章节开启：{r['title']}\n  ID: {r['chapter_id']}"

    @reg.tool(
        name="trpg_chapter_review",
        description="生成章节结构化回顾（阶段总结）。章节结束时必须调用。",
        schema={
            "name": "trpg_chapter_review",
            "parameters": {
                "type": "object",
                "properties": {"chapter_id": {"type": "string", "description": "章节ID，为空则返回当前章节", "default": ""}},
                "required": [],
            },
        },
        emoji="📊",
    )
    def chapter_review(args):
        return chron.chapter_review(args.get("chapter_id", "") or None)

    @reg.tool(
        name="trpg_milestone_add",
        description="添加章节里程碑（阶段目标/关键节点）。开新章节时设定好本章的几个关键目标。",
        schema={
            "name": "trpg_milestone_add",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "里程碑标题"},
                    "description": {"type": "string", "description": "详细描述", "default": ""},
                    "milestone_type": {"type": "string", "description": "类型：objective/turning_point/climax/resolution", "default": "objective"},
                },
                "required": ["title"],
            },
        },
        emoji="🏁",
    )
    def add_milestone(args):
        r = chron.add_milestone(args.get("title", ""), args.get("description", ""), args.get("milestone_type", "objective"))
        if not r.get("success"):
            return f"❌ {r.get('error')}"
        return f"🏁 里程碑: {r.get('title', '')}"

    @reg.tool(
        name="trpg_milestone_update",
        description="更新里程碑状态（完成/失败/进行中）。",
        schema={
            "name": "trpg_milestone_update",
            "parameters": {
                "type": "object",
                "properties": {
                    "milestone_id": {"type": "string", "description": "里程碑ID"},
                    "status": {"type": "string", "description": "状态：pending/in_progress/completed/failed", "default": "completed"},
                    "note": {"type": "string", "description": "完成/失败说明", "default": ""},
                },
                "required": ["milestone_id"],
            },
        },
        emoji="✅",
    )
    def update_milestone(args):
        r = chron.update_milestone(args.get("milestone_id", ""), args.get("status", "completed"), args.get("note", ""))
        if not r.get("success"):
            return f"❌ {r.get('error')}"
        return f"✅ 里程碑 {args.get('milestone_id', '')} → {args.get('status', 'completed')}"

    @reg.tool(
        name="trpg_record_npc_change",
        description="记录 NPC 在本章中的关系/状态变化。",
        schema={
            "name": "trpg_record_npc_change",
            "parameters": {
                "type": "object",
                "properties": {
                    "npc_name": {"type": "string", "description": "NPC 名字"},
                    "change": {"type": "string", "description": "变化描述"},
                    "attitude_shift": {"type": "integer", "description": "态度变化值（正=友好，负=敌对）", "default": 0},
                },
                "required": ["npc_name", "change"],
            },
        },
        emoji="👤",
    )
    def record_npc_change(args):
        r = chron.record_npc_change(args.get("npc_name", ""), args.get("change", ""), args.get("attitude_shift", 0))
        if not r.get("success"):
            return f"❌ {r.get('error')}"
        return f"👤 {args.get('npc_name', '')}: {args.get('change', '')}"

    @reg.tool(
        name="trpg_record_world_change",
        description="记录世界状态变化。新区域解锁、势力变化、灾难、重大发现等。",
        schema={
            "name": "trpg_record_world_change",
            "parameters": {
                "type": "object",
                "properties": {
                    "change": {"type": "string", "description": "变化描述"},
                    "change_type": {"type": "string", "description": "类型：location_unlocked/faction_shift/disaster/discovery/other", "default": "other"},
                },
                "required": ["change"],
            },
        },
        emoji="🌍",
    )
    def record_world_change(args):
        r = chron.record_world_change(args.get("change", ""), args.get("change_type", "other"))
        if not r.get("success"):
            return f"❌ {r.get('error')}"
        return f"🌍 世界变化: {args.get('change', '')}"

    @reg.tool(
        name="trpg_record_level_up",
        description="记录角色升级。玩家升级时调用，记入章节成长记录。",
        schema={
            "name": "trpg_record_level_up",
            "parameters": {
                "type": "object",
                "properties": {
                    "character": {"type": "string", "description": "角色名"},
                    "from_level": {"type": "integer", "description": "升级前等级"},
                    "to_level": {"type": "integer", "description": "升级后等级"},
                    "details": {"type": "string", "description": "升级详情", "default": ""},
                },
                "required": ["character", "from_level", "to_level"],
            },
        },
        emoji="📈",
    )
    def record_level_up(args):
        r = chron.record_level_up(args.get("character", ""), args.get("from_level", 1), args.get("to_level", 2), args.get("details", ""))
        if not r.get("success"):
            return f"❌ {r.get('error')}"
        return f"📈 {args.get('character', '')} 升级: Lv{args.get('from_level', 1)} → Lv{args.get('to_level', 2)}"

    # ================================================================
    # 任务（quests）
    # ================================================================
    @reg.tool(
        name="trpg_quest_list",
        description="列出任务。可按状态过滤。",
        schema={
            "name": "trpg_quest_list",
            "parameters": {
                "type": "object",
                "properties": {"status": {"type": "string", "description": "状态过滤：in_progress/completed/available/failed", "default": ""}},
                "required": [],
            },
        },
        emoji="📋",
    )
    def list_quests(args):
        qs = quests.list_quests(args.get("status", ""))
        if not qs:
            return "（没有任务）"
        lines = [f"📋 任务列表（共 {len(qs)} 个）", ""]
        for q in qs:
            icon = "⭐" if q.get("type") == "main" else "📜"
            lines.append(f"  {icon} [{q.get('status', '?')}] {q.get('title', '?')}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_quest_advance",
        description="推进任务到下一步。玩家完成当前步骤时调用。",
        schema={
            "name": "trpg_quest_advance",
            "parameters": {
                "type": "object",
                "properties": {"quest_id": {"type": "string", "description": "任务 ID"}},
                "required": ["quest_id"],
            },
        },
        emoji="➡️",
    )
    def advance_quest(args):
        r = quests.advance_step(args.get("quest_id", ""))
        if not r.get("success"):
            return f"❌ {r.get('error', '推进失败')}"
        if r.get("all_done"):
            return f"🎉 所有步骤已完成！用 trpg_quest_complete 收尾。"
        return f"➡️ 推进: {r.get('step_title', '?')}"

    @reg.tool(
        name="trpg_quest_complete",
        description="完成任务。全部步骤完成或提前完成时调用。",
        schema={
            "name": "trpg_quest_complete",
            "parameters": {
                "type": "object",
                "properties": {
                    "quest_id": {"type": "string", "description": "任务 ID"},
                    "notes": {"type": "string", "description": "完成备注", "default": ""},
                },
                "required": ["quest_id"],
            },
        },
        emoji="🎉",
    )
    def complete_quest(args):
        r = quests.complete_quest(args.get("quest_id", ""), args.get("notes", ""))
        if not r.get("success"):
            return f"❌ {r.get('error', '完成失败')}"
        return f"🎉 任务完成: {r.get('title', '?')}"

    # ================================================================
    # NPC
    # ================================================================
    @reg.tool(
        name="trpg_npc_attitude_change",
        description="改变 NPC 对玩家的态度值（-100 到 +100）。",
        schema={
            "name": "trpg_npc_attitude_change",
            "parameters": {
                "type": "object",
                "properties": {
                    "npc_name": {"type": "string", "description": "NPC 名字"},
                    "delta": {"type": "integer", "description": "态度变化量（正=友好，负=敌对）"},
                    "reason": {"type": "string", "description": "变化原因", "default": ""},
                },
                "required": ["npc_name", "delta"],
            },
        },
        emoji="💬",
    )
    def npc_attitude(args):
        r = npcs.change_attitude(args.get("npc_name", ""), args.get("delta", 0), args.get("reason", ""))
        if not r.get("success"):
            return f"❌ {r.get('error', '操作失败')}"
        return f"💬 {args.get('npc_name', '')} 态度: {r.get('old_attitude', 0):+d} → {r.get('new_attitude', 0):+d}"

    @reg.tool(
        name="trpg_npc_log_interaction",
        description="记录一次与 NPC 的重要互动。",
        schema={
            "name": "trpg_npc_log_interaction",
            "parameters": {
                "type": "object",
                "properties": {
                    "npc_name": {"type": "string", "description": "NPC 名字"},
                    "interaction_type": {"type": "string", "description": "类型：conversation/trade/favor/combat/quest_give/quest_complete/betrayal"},
                    "summary": {"type": "string", "description": "互动摘要"},
                    "attitude_delta": {"type": "integer", "description": "态度变化量（可选）", "default": 0},
                },
                "required": ["npc_name", "interaction_type", "summary"],
            },
        },
        emoji="🗣",
    )
    def npc_log(args):
        r = npcs.add_interaction(
            args.get("npc_name", ""), args.get("interaction_type", ""),
            args.get("summary", ""), args.get("attitude_delta", 0),
        )
        if not r.get("success"):
            return f"❌ {r.get('error', '记录失败')}"
        return f"🗣 已记录: {args.get('npc_name', '')} - {args.get('summary', '')[:50]}"

    @reg.tool(
        name="trpg_npc_info",
        description="查看 NPC 完整档案。",
        schema={
            "name": "trpg_npc_info",
            "parameters": {
                "type": "object",
                "properties": {"npc_name": {"type": "string", "description": "NPC 名字"}},
                "required": ["npc_name"],
            },
        },
        emoji="👤",
    )
    def npc_info(args):
        n = npcs.get_npc(args.get("npc_name", ""))
        if not n:
            return f"❌ NPC 不存在: {args.get('npc_name', '')}"
        lines = [
            f"👤 {n['name']}",
            f"位置: {n.get('location', '?')} | 状态: {'存活' if n.get('alive', True) else '死亡'}",
            f"态度: {n.get('attitude', 0):+d} | 声望: {n.get('reputation', 0)}",
        ]
        if n.get("goals"):
            lines.append("目标: " + ", ".join(g["text"] for g in n["goals"]))
        if n.get("known_info"):
            lines.append("已知信息: " + "; ".join(n["known_info"][-3:]))
        return "\n".join(lines)

    # ================================================================
    # 时间（clock）
    # ================================================================
    @reg.tool(
        name="trpg_time_now",
        description="获取当前游戏内时间、天气、季节、时段。",
        schema={"name": "trpg_time_now", "parameters": _NO_PARAMS},
        emoji="🕐",
    )
    def time_now(args):
        return clock.format_time()

    @reg.tool(
        name="trpg_time_advance",
        description="推进游戏时间。会自动触发到时间的事件。",
        schema={
            "name": "trpg_time_advance",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "description": "时间数量"},
                    "unit": {"type": "string", "description": "单位：minute/hour/day", "default": "minute"},
                    "reason": {"type": "string", "description": "时间流逝的原因", "default": ""},
                },
                "required": ["amount", "unit"],
            },
        },
        emoji="⏰",
    )
    def time_advance(args):
        amt = args.get("amount", 0)
        unit = args.get("unit", "minute")
        reason = args.get("reason", "")
        method = {"minute": clock.advance_minutes, "hour": clock.advance_hours, "day": clock.advance_days}.get(unit)
        if not method:
            return f"❌ 未知单位: {unit}"
        r = method(amt, reason)
        lines = [f"⏰ {r.get('old_time', '?')} → {r.get('new_time', '?')}"]
        if r.get("events_triggered"):
            lines.append("🔔 事件触发:")
            for ev in r["events_triggered"]:
                lines.append(f"  • {ev['description']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_time_set_weather",
        description="设置当前天气。",
        schema={
            "name": "trpg_time_set_weather",
            "parameters": {
                "type": "object",
                "properties": {"weather": {"type": "string", "description": "天气描述，如 '晴朗' '下雨'"}},
                "required": ["weather"],
            },
        },
        emoji="🌤",
    )
    def time_weather(args):
        r = clock.set_weather(args.get("weather", ""))
        if not r.get("success"):
            return f"❌ {r.get('error')}"
        return f"🌤 天气: {r.get('old_weather', '?')} → {r.get('weather', '?')}"
