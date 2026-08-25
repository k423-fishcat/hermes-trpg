"""快照与回滚工具"""

from .registry import ToolRegistry


def register(reg: ToolRegistry, state):
    @reg.tool(
        name="trpg_snapshot_save",
        description="保存一个命名快照（战斗前/场次结束/重要节点前）。用于回滚恢复。",
        schema={
            "name": "trpg_snapshot_save",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "快照名称"},
                    "reason": {"type": "string", "description": "保存原因"},
                },
                "required": ["name"],
            },
        },
        emoji="📸",
    )
    def save(args):
        r = state.save_named_snapshot(args.get("name", ""), args.get("reason", ""))
        if not r.get("success"):
            return f"❌ 快照保存失败: {r.get('error', '未知错误')}"
        lines = [
            "📸 快照已保存",
            f"  名称: {r['name']}",
            f"  文件: {r['snapshot_file']}",
            f"  版本: v{r['version']}",
        ]
        if args.get("reason"):
            lines.append(f"  原因: {args.get('reason')}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_snapshot_list",
        description="列出所有命名快照，用于选择回滚目标。",
        schema={"name": "trpg_snapshot_list", "parameters": {"type": "object", "properties": {}, "required": []}},
        emoji="📷",
    )
    def list_snaps(args):
        snaps = state.list_named_snapshots()
        if not snaps:
            return "（暂无快照）"
        lines = [f"📷 命名快照（{len(snaps)} 个）", ""]
        for i, s in enumerate(snaps, 1):
            t = s.get("time", "")
            ver = s.get("version", 0)
            reason = f" — {s['reason']}" if s.get("reason") else ""
            lines.append(f"  {i}. [{t}] {s['name']} (v{ver}){reason}")
            lines.append(f"     文件: {s['file']}")
        lines.append("")
        lines.append("提示：使用 trpg_snapshot_rollback <文件名> 回滚")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_snapshot_rollback",
        description="回滚到指定快照。回滚前会自动保存当前状态作为备份。",
        schema={
            "name": "trpg_snapshot_rollback",
            "parameters": {
                "type": "object",
                "properties": {
                    "snapshot_file": {"type": "string", "description": "快照文件名（从 snapshot_list 获取）"},
                },
                "required": ["snapshot_file"],
            },
        },
        emoji="⏪",
    )
    def rollback(args):
        r = state.rollback_to_snapshot(args.get("snapshot_file", ""))
        if not r.get("success"):
            return f"❌ 回滚失败: {r.get('error', '未知错误')}"
        return (
            f"⏪ 已回滚到: {args.get('snapshot_file', '')}\n"
            f"  恢复到版本: v{r['restored_version']}\n"
            f"  当前状态已自动备份（pre_rollback）"
        )
