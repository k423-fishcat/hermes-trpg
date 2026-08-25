"""场次管理与剧情选择工具"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


def register(reg: ToolRegistry, session_mgr):
    @reg.tool(
        name="trpg_session_start",
        description="开始一个新场次。每场结束时用 end_session 写小结，下一场开场自动注入前情提要。",
        schema={
            "name": "trpg_session_start",
            "parameters": {"type": "object", "properties": {"title": {"type": "string", "description": "场次标题", "default": ""}}, "required": []},
        },
        emoji="🎬",
    )
    def start(args):
        r = session_mgr.start_session(args.get("title", ""))
        if not r.get("success"):
            return f"❌ {r.get('error', '')}"
        return f"🎬 第 {r['session_number']} 场开始: {r['title']}\n  开始时间: {r['start_time']}"

    @reg.tool(
        name="trpg_session_end",
        description="结束当前场次，写小结。关键事件、获得的物品/经验、下一场开场提示都会保存。",
        schema={
            "name": "trpg_session_end",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "本场小结", "default": ""},
                    "key_events": {"type": "array", "items": {"type": "string"}},
                    "end_location": {"type": "string", "description": "结束地点", "default": ""},
                    "next_hook": {"type": "string", "description": "下一场开场提示", "default": ""},
                    "xp_gained": {"type": "integer", "description": "本场获得经验", "default": 0},
                    "gold_gained": {"type": "integer", "description": "本场获得金币", "default": 0},
                    "loot": {"type": "array", "items": {"type": "string"}},
                },
                "required": [],
            },
        },
        emoji="🏁",
    )
    def end(args):
        r = session_mgr.end_session(
            summary=args.get("summary", ""),
            key_events=args.get("key_events", []),
            end_location=args.get("end_location", ""),
            next_hook=args.get("next_hook", ""),
            xp_gained=args.get("xp_gained", 0),
            gold_gained=args.get("gold_gained", 0),
            loot=args.get("loot", []),
        )
        if not r.get("success"):
            return f"❌ {r.get('error', '结束失败')}"
        return (
            f"🏁 第 {r['session_number']} 场结束\n"
            f"  关键事件: {r.get('key_events_count', 0)} 条"
        )

    @reg.tool(
        name="trpg_session_recap",
        description="获取前情提要：最近几场的小结 + 上次结束位置 + 开场提示。",
        schema={
            "name": "trpg_session_recap",
            "parameters": {"type": "object", "properties": {"sessions_back": {"type": "integer", "description": "回顾多少场", "default": 3}}, "required": []},
        },
        emoji="📖",
    )
    def recap(args):
        return session_mgr.get_recap(args.get("sessions_back", 3))

    @reg.tool(
        name="trpg_session_list",
        description="列出所有场次。",
        schema={
            "name": "trpg_session_list",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "description": "最近多少场", "default": 10}}, "required": []},
        },
        emoji="📋",
    )
    def list_s(args):
        sessions = session_mgr.list_sessions(args.get("limit", 10))
        if not sessions:
            return "（还没有场次）"
        lines = [f"📋 场次列表（最近 {len(sessions)} 场）", ""]
        for s in sessions:
            lines.append(f"  第 {s['number']} 场 | {s.get('title', '?')}")
            if s.get("end_location"):
                lines.append(f"    结束于: {s['end_location']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_choice_add",
        description="记录玩家的重大选择及其后果。",
        schema={
            "name": "trpg_choice_add",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "玩家做了什么决定"},
                    "consequences": {"type": "string", "description": "直接后果", "default": ""},
                    "impact_tags": {"type": "array", "items": {"type": "string"}},
                    "related_quest": {"type": "string", "description": "相关任务 ID", "default": ""},
                    "related_npcs": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "string", "description": "重要程度: trivial/normal/major/critical", "default": "normal"},
                },
                "required": ["description"],
            },
        },
        emoji="🔀",
    )
    def add_choice(args):
        r = session_mgr.add_choice(
            args.get("description", ""),
            args.get("consequences", ""),
            args.get("impact_tags", []),
            args.get("related_quest", ""),
            args.get("related_npcs", []),
            args.get("importance", "normal"),
        )
        if not r.get("success"):
            return f"❌ {r.get('error', '记录失败')}"
        return f"🔀 已记录选择: {args.get('description', '')}\n  ID: {r['choice_id']}"

    @reg.tool(
        name="trpg_choice_timeline",
        description="查看剧情选择时间线：玩家做过的重要决定及其后果。",
        schema={"name": "trpg_choice_timeline", "parameters": _NO_PARAMS},
        emoji="⏳",
    )
    def timeline(args):
        return session_mgr.get_choice_timeline()
