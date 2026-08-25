"""法术系统工具"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


def register(reg: ToolRegistry, spell_mgr):
    @reg.tool(
        name="trpg_spell_info",
        description="查看玩家法术整体状态：施法属性、攻击加值、豁免 DC、法术位、专注等。",
        schema={"name": "trpg_spell_info", "parameters": _NO_PARAMS},
        emoji="✨",
    )
    def info(args):
        i = spell_mgr.get_spell_info()
        ab_names = {"str": "力量", "dex": "敏捷", "con": "体质", "int": "智力", "wis": "感知", "cha": "魅力"}
        ab = ab_names.get(i["spellcasting_ability"], i["spellcasting_ability"])
        lines = [
            "✨ 法术状态", "=" * 30,
            f"施法属性: {ab} ({i['ability_score']}, {i['ability_modifier']:+d})",
            f"法术攻击: +{i['spell_attack_bonus']} | DC {i['spell_save_dc']}",
            f"已知: {i['spells_known_count']} | 已准备: {i['spells_prepared_count']}",
            f"当前专注: {i.get('concentration') or '无'}",
        ]
        return "\n".join(lines)

    @reg.tool(
        name="trpg_spell_list",
        description="列出已知或已准备的法术列表。",
        schema={
            "name": "trpg_spell_list",
            "parameters": {
                "type": "object",
                "properties": {"list_type": {"type": "string", "description": "类型：known/prepared/all", "default": "all"}},
                "required": [],
            },
        },
        emoji="📖",
    )
    def list_s(args):
        lt = args.get("list_type", "all")
        lines = []
        if lt in ("all", "known"):
            known = spell_mgr.list_known()
            lines.append(f"📚 已知法术（{len(known)} 个）:")
            lines += [f"  • {s}" for s in known] if known else ["  （还没学会任何法术）"]
            lines.append("")
        if lt in ("all", "prepared"):
            prepared = spell_mgr.list_prepared()
            lines.append(f"📖 已准备（{len(prepared)} 个）:")
            lines += [f"  ✓ {s}" for s in prepared] if prepared else ["  （没有准备法术）"]
        return "\n".join(lines)

    @reg.tool(
        name="trpg_spell_prepare",
        description="准备一个法术（从已知法术中选择今天准备用的）。",
        schema={
            "name": "trpg_spell_prepare",
            "parameters": {
                "type": "object",
                "properties": {"spell_id": {"type": "string", "description": "法术 ID 或名称"}},
                "required": ["spell_id"],
            },
        },
        emoji="📖",
    )
    def prep(args):
        r = spell_mgr.prepare(args.get("spell_id", ""))
        if not r.get("success"):
            return f"❌ {r.get('error', '准备失败')}"
        return f"📖 已准备：{args.get('spell_id', '')}\n（共准备 {r['prepared_count']} 个）"

    @reg.tool(
        name="trpg_spell_cast",
        description="施放一个法术，消耗对应等级的法术位。如果是专注法术会开始专注。",
        schema={
            "name": "trpg_spell_cast",
            "parameters": {
                "type": "object",
                "properties": {
                    "spell_id": {"type": "string", "description": "法术 ID 或名称"},
                    "spell_level": {"type": "integer", "description": "使用的法术位等级（0=戏法）", "default": -1},
                    "target": {"type": "string", "description": "目标", "default": ""},
                },
                "required": ["spell_id"],
            },
        },
        emoji="✨",
    )
    def cast(args):
        r = spell_mgr.cast_spell(
            args.get("spell_id", ""),
            spell_level=args.get("spell_level", -1),
            target=args.get("target", ""),
        )
        if not r.get("success"):
            return f"❌ 施放失败: {r.get('error', '未知错误')}"
        lines = [f"✨ 施放：{args.get('spell_id', '')}"]
        if r.get("is_cantrip"):
            lines.append("（戏法，不消耗法术位）")
        else:
            lines.append(f"使用 {r['slot_level']} 环法术位 | 剩余 {r.get('slots_remaining', '?')}")
        if r.get("concentration"):
            lines.append("🎯 开始专注")
        eff = r.get("effect", {})
        if eff.get("healed"):
            lines.append(f"❤️ 恢复 {eff['healed']} HP")
        if eff.get("condition_added"):
            lines.append(f"✨ 获得状态：{eff['condition_added']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_spell_slots",
        description="查看各等级法术位剩余情况。",
        schema={"name": "trpg_spell_slots", "parameters": _NO_PARAMS},
        emoji="🔮",
    )
    def slots(args):
        s = spell_mgr.get_slots()
        lines = ["🔮 法术位", ""]
        any_slot = False
        for level, info in sorted(s.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 99):
            mx = info.get("max", 0)
            if mx > 0:
                any_slot = True
                cur = info.get("current", 0)
                lines.append(f"  {level}环: {'●' * cur}{'○' * (mx - cur)}  {cur}/{mx}")
        if not any_slot:
            lines.append("（没有法术位 — 你可能不是施法者）")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_concentration_end",
        description="手动结束当前专注法术。",
        schema={
            "name": "trpg_concentration_end",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string", "description": "结束原因", "default": "主动结束"}},
                "required": [],
            },
        },
        emoji="💫",
    )
    def conc_end(args):
        r = spell_mgr.end_concentration(args.get("reason", "主动结束"))
        if not r.get("success"):
            return f"❌ {r.get('error', '结束失败')}"
        return f"💫 专注结束：{r['spell']}\n原因: {args.get('reason', '主动结束')}"
