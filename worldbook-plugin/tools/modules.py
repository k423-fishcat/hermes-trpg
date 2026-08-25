"""模组管理工具"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


def register(reg: ToolRegistry, module_mgr):
    @reg.tool(
        name="trpg_module_list",
        description="列出所有可用模组及其激活状态。",
        schema={"name": "trpg_module_list", "parameters": _NO_PARAMS},
        emoji="📦",
    )
    def list_modules(args):
        available = module_mgr.list_available()
        active = set(module_mgr.list_active())
        if not available:
            return "（没有可用模组）"
        lines = [f"📦 可用模组（{len(available)} 个）", ""]
        for m in available:
            status = "✅ 已激活" if m["id"] in active else "  未激活"
            sys_name = m.get("system", "?")
            lines.append(f"  {status} | {m['name']} (id: {m['id']}, system: {sys_name})")
            if m.get("description"):
                lines.append(f"      {m['description']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_module_activate",
        description="激活一个模组，将模组的世界书条目/NPC/任务/遭遇导入到运行时系统。",
        schema={
            "name": "trpg_module_activate",
            "parameters": {
                "type": "object",
                "properties": {
                    "module_id": {"type": "string", "description": "模组 ID（从 module_list 获取）"},
                },
                "required": ["module_id"],
            },
        },
        emoji="🟢",
    )
    def activate(args):
        r = module_mgr.activate(args.get("module_id", ""))
        if not r.get("success"):
            return f"❌ 激活失败: {r.get('error', '未知错误')}"
        return (
            f"✅ 模组已激活: {r['module_name']}\n"
            f"  条目: +{r['entries_imported']} | NPC: +{r['npcs_imported']} | "
            f"任务: +{r['quests_imported']} | 遭遇: +{r['encounters_imported']}"
        )

    @reg.tool(
        name="trpg_module_deactivate",
        description="停用一个已激活的模组（数据保留在状态中，不删除）。",
        schema={
            "name": "trpg_module_deactivate",
            "parameters": {
                "type": "object",
                "properties": {
                    "module_id": {"type": "string", "description": "模组 ID"},
                },
                "required": ["module_id"],
            },
        },
        emoji="⏸️",
    )
    def deactivate(args):
        r = module_mgr.deactivate(args.get("module_id", ""))
        if not r.get("success"):
            return f"❌ 停用失败: {r.get('error', '未知错误')}"
        return f"⏸️ 模组已停用: {args.get('module_id', '')}\n  数据已保留在状态中"

    @reg.tool(
        name="trpg_module_info",
        description="查看指定模组的详细信息。",
        schema={
            "name": "trpg_module_info",
            "parameters": {
                "type": "object",
                "properties": {
                    "module_id": {"type": "string", "description": "模组 ID"},
                },
                "required": ["module_id"],
            },
        },
        emoji="ℹ️",
    )
    def info(args):
        m = module_mgr.get_module_info(args.get("module_id", ""))
        if not m:
            return f"❌ 模组不存在: {args.get('module_id', '')}"
        lines = [
            f"ℹ️ {m['name']} (id: {m['id']})",
            f"  系统: {m.get('system', '?')}",
            f"  格式: {m.get('format', '?')}",
            f"  激活: {'是' if m.get('active') else '否'}",
        ]
        for k in ("entry_count", "npc_count", "quest_count", "encounter_count"):
            if k in m:
                lines.append(f"  {k}: {m[k]}")
        if m.get("error"):
            lines.append(f"  ⚠️ 错误: {m['error']}")
        return "\n".join(lines)
