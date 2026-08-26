"""规则书查询工具（主动查询，非自动注入）"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}

# 分类 → 中文名
_CATEGORY_ZH = {
    "spells": "法术", "creatures": "怪物", "classes": "职业",
    "conditions": "状态", "items": "魔法物品", "checks": "技能/豁免",
    "combat": "战斗规则", "rest": "休息规则", "equipment": "起始装备",
    "spell_slots": "法术位表",
}


def _cat_from_rule_id(rule_id: str) -> str:
    """从 rule_id（rules.dnd5e.creatures.aboleth）提取分类"""
    parts = str(rule_id).split(".")
    if len(parts) >= 3:
        return parts[2]
    return ""


def _cat_zh(cat: str) -> str:
    return _CATEGORY_ZH.get(cat, cat)


def register(reg: ToolRegistry, rules_book):
    @reg.tool(
        name="trpg_rules_search",
        description=(
            "搜索本地规则书。按关键词查找法术/怪物/职业/状态/魔法物品/技能等规则条目。"
            "查规则、查怪物数据、查法术效果时用这个。"
        ),
        schema={
            "name": "trpg_rules_search",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（中文或英文）"},
                    "category": {"type": "string", "description": "限定分类：spells/creatures/classes/conditions/items/checks/combat/rest，留空搜索全部", "default": ""},
                    "edition": {"type": "string", "description": "规则版本：2024/2014", "default": "2024"},
                    "limit": {"type": "integer", "description": "最多返回条数", "default": 5},
                },
                "required": ["query"],
            },
        },
        emoji="📖",
    )
    def search(args):
        results = rules_book.search(
            args.get("query", ""),
            category=args.get("category") or None,
            top_k=args.get("limit", 5),
            edition=args.get("edition", "2024"),
        )
        if not results:
            return f"（没有找到和「{args.get('query', '')}」相关的规则）"
        lines = [f"📖 找到 {len(results)} 条规则:", ""]
        for r in results:
            cat = _cat_from_rule_id(r.get("rule_id", ""))
            name = r.get("name_zh") or r.get("name_en") or "?"
            lines.append(f"  • [{_cat_zh(cat)}] {name}")
            summary = r.get("summary") or r.get("description") or ""
            if summary:
                lines.append(f"    {summary[:100]}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_rules_get",
        description="获取单条规则完整内容。按分类+名称精确查询（名称用中文或英文均可）。",
        schema={
            "name": "trpg_rules_get",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "分类：spells/creatures/classes/conditions/items/checks/combat/rest"},
                    "name": {"type": "string", "description": "规则名称（中文或英文）"},
                    "edition": {"type": "string", "description": "规则版本：2024/2014", "default": "2024"},
                },
                "required": ["category", "name"],
            },
        },
        emoji="📄",
    )
    def get(args):
        category = args.get("category", "")
        name = args.get("name", "")
        edition = args.get("edition", "2024")
        r = rules_book.get("dnd5e", category, name, edition=edition)
        if not r:
            # 精确 key 查不到（key 是英文 slug）→ 用搜索找中文名匹配
            results = rules_book.search(
                name, category=category or None, top_k=1, edition=edition,
            )
            if results:
                r = results[0]
        if not r:
            return f"❌ 未找到: {category}/{name}"
        return _format_rule(r)

    @reg.tool(
        name="trpg_rules_categories",
        description="列出规则书已加载的分类和条目数。",
        schema={
            "name": "trpg_rules_categories",
            "parameters": {
                "type": "object",
                "properties": {"edition": {"type": "string", "description": "规则版本：2024/2014", "default": "2024"}},
                "required": [],
            },
        },
        emoji="🗂",
    )
    def categories(args):
        edition = args.get("edition", "2024")
        cats = rules_book.list_categories("dnd5e", edition=edition)
        if not cats:
            return f"（{edition} 规则书未加载）"
        lines = [f"🗂 {edition} 规则书分类（{len(cats)} 个）:", ""]
        for c in sorted(cats):
            names = rules_book.list_names("dnd5e", c, edition=edition)
            lines.append(f"  • {_cat_zh(c)} ({c}): {len(names)} 条")
        return "\n".join(lines)


def _format_rule(r: dict) -> str:
    """格式化单条规则为可读文本"""
    name = r.get("name_zh") or r.get("name_en") or "?"
    lines = [f"📄 {name}"]
    if r.get("name_en") and r.get("name_en") != name:
        lines.append(f"  ({r['name_en']})")
    if r.get("cr") is not None:
        lines.append(f"  CR {r['cr']}")
    if r.get("type"):
        lines.append(f"  类型: {r['type']}")
    if r.get("ac") is not None:
        lines.append(f"  AC {r['ac']} | HP {r.get('hp_average', '?')}（{r.get('hp_formula', '')}）| 速度 {r.get('speed', '?')}")
    if r.get("abilities"):
        ab = r["abilities"]
        lines.append("  属性: " + " ".join(f"{k.upper()} {ab.get(k, '?')}" for k in ("str", "dex", "con", "int", "wis", "cha")))
    for label, key in [("伤害抗性", "damage_resistances"), ("伤害免疫", "damage_immunities"), ("伤害易伤", "damage_vulnerabilities")]:
        if r.get(key):
            lines.append(f"  {label}: {', '.join(r[key])}")
    if r.get("level") is not None:
        lines.append(f"  环位: {r['level']} | 学派: {r.get('school', '?')}")
    if r.get("casting_time"):
        lines.append(f"  施法时间: {r['casting_time']} | 射程: {r.get('range', '?')} | 持续时间: {r.get('duration', '?')}")
    if r.get("description"):
        lines.append(f"  描述: {r['description'][:300]}")
    if r.get("summary"):
        lines.append(f"  摘要: {r['summary'][:200]}")
    if r.get("actions_summary"):
        lines.append("  动作:")
        for a in r["actions_summary"][:5]:
            lines.append(f"    • {a.get('name', '?')}: {a.get('desc', '')[:100]}")
    if r.get("phb_page"):
        lines.append(f"  PHB p.{r['phb_page']}")
    return "\n".join(lines)
