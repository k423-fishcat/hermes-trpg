"""状态工具（state get/update）"""

from .registry import ToolRegistry


def register(reg: ToolRegistry, state):
    @reg.tool(
        name="trpg_state_get",
        description="获取跑团状态数据。不传 path 返回完整状态摘要，传 path 返回指定字段的值。",
        schema={
            "name": "trpg_state_get",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "状态路径，点分隔，如 player.hp.current / npcs.老比尔 / inventory。为空返回完整摘要。",
                        "default": "",
                    },
                },
                "required": [],
            },
        },
        emoji="📊",
    )
    def get_state(args):
        path = args.get("path", "")
        if not path:
            from .. import state as _state_mod
            return _state_mod._format_status_summary(state)
        val = state.get(path)
        if isinstance(val, (dict, list)):
            import json
            return json.dumps(val, ensure_ascii=False, indent=2)
        return str(val) if val is not None else "（空）"

    @reg.tool(
        name="trpg_state_update",
        description="更新跑团状态（单入口原则：所有状态变更必须通过此工具）。支持同时更新多个字段。会自动记录事件日志、增加版本号。",
        schema={
            "name": "trpg_state_update",
            "parameters": {
                "type": "object",
                "properties": {
                    "changes": {
                        "type": "object",
                        "description": '要更新的路径和值的字典，如 {"player.hp.current": 15, "player.gold": 100}',
                    },
                    "reason": {"type": "string", "description": "变更原因，会写入事件日志", "default": ""},
                    "actor": {"type": "string", "description": "执行者（DM/玩家/怪物名/系统）", "default": "DM"},
                },
                "required": ["changes"],
            },
        },
        emoji="✏️",
    )
    def update_state(args):
        r = state.update(args.get("changes", {}), args.get("reason", ""), args.get("actor", "DM"))
        if not r.get("success"):
            return f"❌ 更新失败: {r.get('error', '未知错误')}"
        lines = [f"✏️ 状态更新 v{r['version']}（{r['change_count']} 项）"]
        if args.get("reason"):
            lines.append(f"原因: {args.get('reason')}")
        return "\n".join(lines)
