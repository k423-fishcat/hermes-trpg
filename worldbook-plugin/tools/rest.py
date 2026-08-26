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
            f"  恢复 HP: +{r.get('healed', 0)}",
            f"  当前 HP: {r.get('hp_after', '?')}/{r.get('hp_max', '?')}",
        ]
        if r.get("hit_dice_used"):
            lines.append(f"  使用命中骰: {r['hit_dice_used']} 个")
        if r.get("hit_dice_remaining") is not None:
            lines.append(f"  剩余命中骰: {r['hit_dice_remaining']} 个")
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
        lines = [
            "😴 长休（8 小时）",
            f"  HP: 满（{r.get('hp_after', '?')}/{r.get('hp_max', '?')}）",
            "  命中骰 / 法术位 / 职业资源 全部恢复",
        ]
        if r.get("hit_dice_restored"):
            lines.append(f"  恢复命中骰: {r['hit_dice_restored']} 个")
        if r.get("spell_slots_restored"):
            slots = r["spell_slots_restored"]
            if isinstance(slots, dict):
                parts = [f"{lv}环 +{v}" for lv, v in sorted(slots.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0)]
                lines.append(f"  恢复法术位: {'，'.join(parts)}")
            else:
                lines.append(f"  恢复法术位: {slots}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_rest_status",
        description="查看当前休息状态（HP / 命中骰 / 法术位）。",
        schema={"name": "trpg_rest_status", "parameters": _NO_PARAMS},
        emoji="📊",
    )
    def rest_status(args):
        s = rest_mgr.rest_status()
        lines = [
            "📊 休息状态",
            f"  HP: {s.get('hp', '?')}（临时 {s.get('temp_hp', 0)}）",
        ]
        hd = s.get("hit_dice", {})
        if hd:
            lines.append(f"  命中骰: {hd.get('available', '?')}/{hd.get('total', '?')} 可用（已用 {hd.get('used', 0)}）")
        slots = s.get("spell_slots", {})
        if isinstance(slots, dict) and slots:
            parts = []
            for lv, v in slots.items():
                parts.append(f"{lv}环 {v.get('current', '?')}/{v.get('max', '?')}")
            lines.append(f"  法术位: {'，'.join(parts)}")
        elif isinstance(slots, str):
            lines.append(f"  法术位: {slots}")
        return "\n".join(lines)
