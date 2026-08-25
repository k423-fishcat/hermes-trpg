"""休息与恢复工具（短休/长休）"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


def register(reg: ToolRegistry, rest_mgr):
    @reg.tool(
        name="trpg_short_rest",
        description="短休（1小时）。可消耗若干命中骰恢复 HP，触发短休类资源恢复。",
        schema={
            "name": "trpg_short_rest",
            "parameters": {
                "type": "object",
                "properties": {
                    "hit_dice_count": {"type": "integer", "description": "使用多少颗命中骰（不传则用 1）", "default": 1},
                },
                "required": [],
            },
        },
        emoji="😌",
    )
    def short_rest(args):
        r = rest_mgr.short_rest(hit_dice_count=args.get("hit_dice_count", 1))
        if not r.get("success"):
            return f"❌ 短休失败: {r.get('error', '未知错误')}"
        lines = [
            "😌 短休（1 小时）",
            f"  恢复 HP: +{r.get('hp_restored', 0)}",
            f"  当前 HP: {r.get('current_hp', '?')}/{r.get('max_hp', '?')}",
        ]
        if r.get("hit_dice_used"):
            lines.append(f"  使用命中骰: {r['hit_dice_used']} 个")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_long_rest",
        description="长休（8小时）。HP 满、所有命中骰恢复、所有法术位恢复。24 小时内只能一次。",
        schema={"name": "trpg_long_rest", "parameters": _NO_PARAMS},
        emoji="😴",
    )
    def long_rest(args):
        r = rest_mgr.long_rest()
        if not r.get("success"):
            return f"❌ 长休失败: {r.get('error', '未知错误')}"
        return (
            "😴 长休（8 小时）\n"
            f"  HP: 满（{r.get('current_hp', '?')}/{r.get('max_hp', '?')}）\n"
            "  命中骰 / 法术位 / 职业资源 全部恢复"
        )

    @reg.tool(
        name="trpg_rest_status",
        description="查看当前休息状态（HP / 命中骰 / 法术位）。",
        schema={"name": "trpg_rest_status", "parameters": _NO_PARAMS},
        emoji="📊",
    )
    def rest_status(args):
        s = rest_mgr.status()
        return s
