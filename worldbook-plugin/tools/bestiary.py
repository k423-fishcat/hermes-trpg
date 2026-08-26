"""怪物图鉴工具"""

import json

from .registry import ToolRegistry


def register(reg: ToolRegistry, bestiary):
    @reg.tool(
        name="trpg_monster_search",
        description="搜索怪物图鉴。输入关键词，返回匹配的怪物列表（精简信息）。",
        schema={
            "name": "trpg_monster_search",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（名称/类型/标签）"},
                    "limit": {"type": "integer", "description": "最多返回多少条", "default": 10},
                },
                "required": ["query"],
            },
        },
        emoji="🔍",
    )
    def search(args):
        results = bestiary.search(args.get("query", ""), args.get("limit", 10))
        if not results:
            return f"（没有找到和「{args.get('query', '')}」相关的怪物）"
        lines = [f"找到 {len(results)} 个怪物:", ""]
        for r in results:
            lines.append(f"  • [{r['id']}] {r['name']} | CR {r['cr']} | {r['type']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_monster_list",
        description="列出怪物图鉴中的怪物，可按 CR 范围或类型过滤。",
        schema={
            "name": "trpg_monster_list",
            "parameters": {
                "type": "object",
                "properties": {
                    "type_filter": {"type": "string", "description": "怪物类型过滤，如 '类人生物' '野兽'"},
                    "cr_min": {"type": "number", "description": "最低 CR"},
                    "cr_max": {"type": "number", "description": "最高 CR"},
                },
                "required": [],
            },
        },
        emoji="📋",
    )
    def list_m(args):
        ms = bestiary.list_monsters(
            type_filter=args.get("type_filter", ""),
            cr_min=args.get("cr_min"),
            cr_max=args.get("cr_max"),
        )
        if not ms:
            return "（没有符合条件的怪物）"
        lines = [f"怪物列表（共 {len(ms)} 个）:", ""]
        for m in ms:
            lines.append(f"  • [{m['id']}] {m['name']} | CR {m['cr']} | {m['size']} {m['type']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_monster_get",
        description="获取怪物完整数据卡：属性、技能、攻击、特性、抗性等。",
        schema={
            "name": "trpg_monster_get",
            "parameters": {
                "type": "object",
                "properties": {"monster_id": {"type": "string", "description": "怪物 ID（从搜索或列表中获取）"}},
                "required": ["monster_id"],
            },
        },
        emoji="👹",
    )
    def get_m(args):
        m = bestiary.get_monster(args.get("monster_id", ""))
        if not m:
            return f"❌ 怪物不存在: {args.get('monster_id', '')}"
        return _format_monster_card(m)

    @reg.tool(
        name="trpg_monster_stats",
        description="获取怪物战斗相关精简数据：HP/AC/速度/攻击/抗性。战斗时用这个就够了。",
        schema={
            "name": "trpg_monster_stats",
            "parameters": {
                "type": "object",
                "properties": {"monster_id": {"type": "string", "description": "怪物 ID"}},
                "required": ["monster_id"],
            },
        },
        emoji="⚔️",
    )
    def stats(args):
        s = bestiary.get_template_stats(args.get("monster_id", ""))
        if not s:
            return f"❌ 怪物不存在: {args.get('monster_id', '')}"
        return _format_monster_stats(s)

    @reg.tool(
        name="trpg_monster_import",
        description="把一只 SRD 怪物导入本地图鉴（从 dnd-rules 查询到的数据）。",
        schema={
            "name": "trpg_monster_import",
            "parameters": {
                "type": "object",
                "properties": {
                    "srd_data_json": {"type": "string", "description": "dnd-rules 返回的怪物结构化数据（JSON 字符串）"},
                    "overwrite": {"type": "boolean", "description": "已存在是否覆盖", "default": False},
                },
                "required": ["srd_data_json"],
            },
        },
        emoji="📥",
    )
    def import_m(args):
        try:
            srd_data = json.loads(args.get("srd_data_json", ""))
        except Exception as e:
            return f"❌ JSON 解析失败: {e}"
        from ..bestiary_import import convert_creature_to_bestiary
        template = convert_creature_to_bestiary(srd_data)
        if not template:
            return "❌ 无法转换为 bestiary 格式"
        mid = template["id"]
        existing = bestiary.get_monster(mid)
        if existing and not args.get("overwrite", False):
            return f"⚠️ 怪物 {mid} 已存在（不覆盖）。如需覆盖请传 overwrite=true"
        r = bestiary.add_monster(template) if not existing else bestiary.update_monster(mid, template)
        return f"📥 已导入: {template.get('name', mid)} (id: {mid})" if r.get("success") else f"❌ 导入失败: {r.get('error')}"


def _format_monster_card(m: dict) -> str:
    """格式化怪物完整数据卡"""
    ab = m.get("abilities", {})
    lines = [
        f"👹 {m.get('name', '')} ({m.get('name_en', '')})",
        f"{m.get('size', '')} {m.get('type', '')}，{m.get('alignment', '')}",
        f"CR {m.get('cr', 0)} | XP {m.get('xp', 0)}",
        "─" * 30,
        f"AC {m['stats'].get('ac', '?')} | HP {m['stats'].get('hp', '?')}（均值 {m['stats'].get('hp_average', 0)}）",
        f"速度 {m['stats'].get('speed', 0)} 尺",
        "─" * 30,
        "STR DEX CON INT WIS CHA",
        " ".join(f"{ab.get(k, 10):>3}" for k in ("str", "dex", "con", "int", "wis", "cha")),
        "─" * 30,
    ]
    if m.get("skills"):
        lines.append(f"技能: {', '.join(f'{k} +{v}' for k, v in m['skills'].items())}")
    for label, key in [("伤害抗性", "damage_resistances"), ("伤害免疫", "damage_immunities"), ("状态免疫", "condition_immunities")]:
        if m.get(key):
            lines.append(f"{label}: {', '.join(m[key])}")
    if m.get("attacks"):
        lines.append("─" * 30)
        lines.append("攻击:")
        for atk in m["attacks"]:
            lines.append(f"  • {atk.get('name', '?')}: {atk.get('description', '?')}")
    if m.get("special_abilities"):
        lines.append("特性:")
        for sa in m["special_abilities"]:
            lines.append(f"  • {sa.get('name', '?')}: {sa.get('description', '?')[:200]}")
    return "\n".join(lines)


def _format_monster_stats(s: dict) -> str:
    """格式化怪物战斗数据"""
    ab = s.get("abilities", {})
    lines = [
        f"⚔️ {s.get('name', '?')}",
        f"AC {s.get('ac', '?')} | HP 均值 {s.get('hp_average', '?')} | 速度 {s.get('speed', 30)}",
        f"CR {s.get('cr', 0)} | {s.get('size', '')}",
        "─" * 30,
        " ".join(f"{ab.get(k, 10):>3}" for k in ("str", "dex", "con", "int", "wis", "cha")),
    ]
    if s.get("attacks"):
        lines.append("攻击:")
        for atk in s["attacks"]:
            lines.append(f"  • {atk.get('name', '?')}: {atk.get('description', '?')[:150]}")
    return "\n".join(lines)
