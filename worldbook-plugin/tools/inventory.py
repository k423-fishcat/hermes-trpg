"""背包物品工具"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


_TYPE_NAMES = {
    "weapon": "⚔️ 武器", "armor": "🛡️ 护甲", "shield": "🛡️ 盾牌",
    "potion": "💊 药水", "scroll": "📜 卷轴", "tool": "🔧 工具",
    "wondrous": "✨ 奇物", "treasure": "💎 财宝", "consumable": "📦 消耗品",
    "misc": "📦 杂物",
}

_SLOT_NAMES = {
    "main_hand": "主手", "off_hand": "副手", "body": "护甲",
    "head": "头部", "feet": "脚部", "hands": "手部",
    "neck": "颈部", "back": "背部", "waist": "腰部",
    "ring_right": "右指", "ring_left": "左指",
}


def register(reg: ToolRegistry, inv):
    @reg.tool(
        name="trpg_inventory_list",
        description="列出背包里的所有物品，或按类型过滤。",
        schema={
            "name": "trpg_inventory_list",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "description": "物品类型：weapon/armor/shield/potion/scroll/tool/misc", "default": ""},
                    "equipped_only": {"type": "boolean", "description": "只显示已装备的物品", "default": False},
                },
                "required": [],
            },
        },
        emoji="🎒",
    )
    def list_inv(args):
        items = inv.list_items(item_type=args.get("item_type", ""), equipped_only=args.get("equipped_only", False))
        if not items:
            return "（背包是空的）"
        weight = inv.total_weight()
        lines = [f"🎒 背包（{len(items)} 件，{weight} 磅）", ""]
        by_type = {}
        for it in items:
            by_type.setdefault(it.get("type", "misc"), []).append(it)
        for itype, group in sorted(by_type.items()):
            lines.append(f"{_TYPE_NAMES.get(itype, f'📦 {itype}')} ({len(group)}):")
            for item in group:
                qty = item.get("quantity", 1)
                qty_str = f" ×{qty}" if qty > 1 else ""
                eq_str = " [已装备]" if item.get("equipped") else ""
                lines.append(f"  • {item.get('name', '?')}{qty_str}{eq_str}")
                if item.get("value"):
                    lines.append(f"    价值 {item['value']} 金币")
                if item.get("description") and len(item["description"]) < 80:
                    lines.append(f"    {item['description']}")
            lines.append("")
        return lines[0] + "\n" + "\n".join(lines[1:]).rstrip()

    @reg.tool(
        name="trpg_inventory_add",
        description="添加物品到背包。给予玩家战利品、奖励时调用。",
        schema={
            "name": "trpg_inventory_add",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "物品名称"},
                    "item_type": {"type": "string", "description": "物品类型", "default": "misc"},
                    "quantity": {"type": "integer", "description": "数量", "default": 1},
                    "item_id": {"type": "string", "description": "物品 ID（可选）", "default": ""},
                    "source": {"type": "string", "description": "来源", "default": ""},
                },
                "required": ["name"],
            },
        },
        emoji="➕",
    )
    def add(args):
        item = {
            "id": args.get("item_id", "") or args.get("name", ""),
            "name": args.get("name", ""),
            "type": args.get("item_type", "misc"),
        }
        for k, v in args.items():
            if k not in ("name", "item_type", "item_id", "quantity", "source") and v:
                item[k] = v
        r = inv.add_item(item, args.get("quantity", 1), args.get("source", ""))
        if not r.get("success"):
            return f"❌ 添加失败: {r.get('error', '未知错误')}"
        return f"➕ 获得 {r['quantity']}x {r['name']}\n（共 {r['total_quantity']} 件）"

    @reg.tool(
        name="trpg_inventory_remove",
        description="移除或使用物品（消耗数量）。",
        schema={
            "name": "trpg_inventory_remove",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "物品 ID 或名称"},
                    "quantity": {"type": "integer", "description": "数量", "default": 1},
                    "reason": {"type": "string", "description": "原因：使用/丢弃/售出", "default": ""},
                },
                "required": ["item_id"],
            },
        },
        emoji="➖",
    )
    def remove(args):
        r = inv.remove_item(args.get("item_id", ""), args.get("quantity", 1), args.get("reason", ""))
        if not r.get("success"):
            return f"❌ {r.get('error', '移除失败')}"
        return f"➖ 失去 {r['quantity_removed']}x {r['name']}\n剩余: {r['remaining']} 件"

    @reg.tool(
        name="trpg_equip",
        description="装备一件物品（武器/护甲/盾牌/魔法物品等）。会自动更新 AC。",
        schema={
            "name": "trpg_equip",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "string", "description": "物品 ID 或名称"}},
                "required": ["item_id"],
            },
        },
        emoji="🛡️",
    )
    def equip(args):
        r = inv.equip(args.get("item_id", ""))
        if not r.get("success"):
            return f"❌ 装备失败: {r.get('error', '未知错误')}"
        ac = inv.current_ac()
        lines = [f"🛡️ 装备：{r['item_name']}"]
        if r.get("unequipped"):
            lines.append(f"（换下了 {r['unequipped']}）")
        lines.append(f"AC: {ac['ac']} ({r.get('ac_change', 0):+d})")
        lines.append(f"  {ac['details']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_unequip",
        description="卸下一件装备。",
        schema={
            "name": "trpg_unequip",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "string", "description": "物品 ID 或名称"}},
                "required": ["item_id"],
            },
        },
        emoji="👕",
    )
    def unequip(args):
        r = inv.unequip(args.get("item_id", ""))
        if not r.get("success"):
            return f"❌ 卸下失败: {r.get('error', '未知错误')}"
        ac = inv.current_ac()
        return f"👕 卸下：{r['item_name']}\nAC: {ac['ac']} ({r.get('ac_change', 0):+d})"

    @reg.tool(
        name="trpg_use_item",
        description="使用一件消耗品（药水、卷轴等）。自动应用效果并扣除数量。",
        schema={
            "name": "trpg_use_item",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "string", "description": "物品 ID 或名称"}},
                "required": ["item_id"],
            },
        },
        emoji="💊",
    )
    def use(args):
        r = inv.use_item(args.get("item_id", ""))
        if not r.get("success"):
            return f"❌ 使用失败: {r.get('error', '未知错误')}"
        lines = [f"💊 使用：{r['item_name']}", ""]
        eff = r.get("effects", {})
        if "healed" in eff:
            lines.append(f"  ❤️ 恢复 {eff['healed']} HP")
        if "buff" in eff:
            lines.append(f"  ✨ 获得效果：{eff['buff']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_gold",
        description="查看或修改金币。可以是正数（获得）或负数（花费）。",
        schema={
            "name": "trpg_gold",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "description": "金币变化量（正=获得，负=花费，0=只查看）", "default": 0},
                    "reason": {"type": "string", "description": "原因", "default": ""},
                },
                "required": [],
            },
        },
        emoji="💰",
    )
    def gold(args):
        amt = args.get("amount", 0)
        if amt == 0:
            return f"💰 当前金币: {inv.get_gold()} 金币"
        if amt > 0:
            r = inv.add_gold(amt, args.get("reason", ""))
            return f"💰 获得 {amt} 金币\n当前: {r['new']} 金币"
        r = inv.spend_gold(-amt, args.get("reason", ""))
        if r.get("success"):
            return f"💰 花费 {-amt} 金币\n当前: {r['new']} 金币"
        return f"❌ {r.get('error', '金币不足')}"

    @reg.tool(
        name="trpg_equipped_status",
        description="查看已装备的所有物品和 AC 详情。",
        schema={"name": "trpg_equipped_status", "parameters": _NO_PARAMS},
        emoji="⚔️",
    )
    def equipped_status(args):
        ac = inv.current_ac()
        equipped = inv.list_equipped()
        lines = [f"⚔️ 装备状态", "=" * 30, "", f"AC: {ac['ac']}", f"  {ac['details']}", ""]
        for slot, name in _SLOT_NAMES.items():
            item = equipped.get(slot)
            lines.append(f"  {name}: {item['name'] if item else '—'}")
        return "\n".join(lines)
