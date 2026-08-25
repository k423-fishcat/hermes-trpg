"""遭遇管理工具"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


def register(reg: ToolRegistry, enc):
    @reg.tool(
        name="trpg_encounter_list",
        description="列出所有可用遭遇，或按地点/类型过滤。",
        schema={
            "name": "trpg_encounter_list",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "按地点过滤（可选）"},
                    "encounter_type": {"type": "string", "description": "按类型过滤：combat/social/exploration/trap/other"},
                },
                "required": [],
            },
        },
        emoji="📋",
    )
    def list_enc(args):
        encounters = enc.list_encounters(location=args.get("location", ""), encounter_type=args.get("encounter_type", ""))
        if not encounters:
            return "（没有符合条件的遭遇）"
        lines = [f"📋 遭遇列表（共 {len(encounters)} 个）", ""]
        for e in encounters:
            si = "🟢" if e.get("status") == "active" else ("✅" if e.get("status") == "completed" else "⬜")
            ti = {"combat": "⚔️", "social": "💬", "exploration": "🔍", "trap": "💣"}.get(e.get("type", ""), "❓")
            lines.append(f"  {si} {ti} [{e['id']}] {e.get('name', '?')}")
            if e.get("location"):
                lines.append(f"       地点: {e['location']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_encounter_start",
        description="启动一个遭遇。战斗遭遇会自动开始战斗并实例化怪物。",
        schema={
            "name": "trpg_encounter_start",
            "parameters": {
                "type": "object",
                "properties": {"encounter_id": {"type": "string", "description": "遭遇 ID"}},
                "required": ["encounter_id"],
            },
        },
        emoji="▶️",
    )
    def start(args):
        r = enc.start_encounter(args.get("encounter_id", ""))
        if not r.get("success"):
            return f"❌ 启动失败: {r.get('error', '未知错误')}"
        lines = [f"▶️  遭遇启动：{r.get('name', args.get('encounter_id', ''))}", "=" * 40, ""]
        desc = r.get("description", "")
        if desc:
            lines += [desc, ""]
        if r.get("type") == "combat":
            lines.append(f"敌人数量: {r.get('creatures_count', 0)}")
            lines.append("（战斗已开始，使用 trpg_combat_status 查看战场）")
        else:
            for skill, dc in r.get("dc_info", {}).items():
                lines.append(f"  • {skill}: DC {dc}")
        if r.get("rewards"):
            lines.append(f"\n奖励: {r['rewards']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_encounter_end",
        description="结束遭遇，标记结果并显示奖励。",
        schema={
            "name": "trpg_encounter_end",
            "parameters": {
                "type": "object",
                "properties": {
                    "encounter_id": {"type": "string", "description": "遭遇 ID"},
                    "outcome": {"type": "string", "description": "结果：victory/defeat/neutral/flee", "default": "victory"},
                },
                "required": ["encounter_id"],
            },
        },
        emoji="🏁",
    )
    def end(args):
        r = enc.end_encounter(args.get("encounter_id", ""), args.get("outcome", "victory"))
        if not r.get("success"):
            return f"❌ {r.get('error', '结束失败')}"
        ot = {"victory": "胜利！", "defeat": "失败...", "neutral": "和平解决", "flee": "逃跑了"}.get(args.get("outcome", "victory"), args.get("outcome", ""))
        lines = [f"🏁 遭遇结束：{r.get('name', '')} — {ot}", ""]
        if r.get("rewards") and args.get("outcome", "victory") == "victory":
            lines.append(f"🎉 获得奖励：{r['rewards']}")
        if r.get("xp_reward"):
            lines.append(f"⭐ XP: +{r['xp_reward']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_encounter_describe",
        description="获取遭遇的描述文本（给玩家看的），包括怪物列表、DC、奖励等。",
        schema={
            "name": "trpg_encounter_describe",
            "parameters": {
                "type": "object",
                "properties": {"encounter_id": {"type": "string", "description": "遭遇 ID"}},
                "required": ["encounter_id"],
            },
        },
        emoji="📝",
    )
    def describe(args):
        return enc.describe_encounter(args.get("encounter_id", ""))
