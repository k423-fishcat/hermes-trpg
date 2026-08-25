"""战斗追踪工具"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


def register(reg: ToolRegistry, ct):
    @reg.tool(
        name="trpg_combat_start",
        description="开始一场战斗。传入怪物列表和玩家先攻值，自动排先攻顺序并实例化怪物。",
        schema={
            "name": "trpg_combat_start",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "战斗名称/场景描述", "default": "遭遇战"},
                    "monsters": {
                        "type": "array",
                        "description": "怪物列表，每项格式 {monster_id, count, initiative_bonus}",
                        "items": {"type": "object"},
                    },
                    "player_initiative": {"type": "integer", "description": "玩家先攻值（已投好的）"},
                },
                "required": ["player_initiative"],
            },
        },
        emoji="⚔️",
    )
    def start(args):
        r = ct.start_combat(
            name=args.get("name", "遭遇战"),
            monsters=args.get("monsters", []),
            player_initiative=args.get("player_initiative", 10),
        )
        if not r.get("success"):
            return f"❌ {r.get('error', '开始失败')}"
        lines = [f"⚔️ 战斗开始：{r['name']}", "", "先攻顺序:"]
        for i, u in enumerate(r["initiative_order"]):
            marker = "→ " if i == 0 else "  "
            icon = "🧙" if u.get("is_player") else "👹"
            lines.append(f"  {marker}{icon} {u['name']}（先攻 {u['initiative']}）")
        lines.append(f"\n共 {r['creature_count']} 只怪物。用 trpg_combat_next_turn 推进回合。")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_combat_status",
        description="当前战斗状态总览：先攻顺序、当前谁的回合、各单位 HP 和状态。",
        schema={"name": "trpg_combat_status", "parameters": _NO_PARAMS},
        emoji="📊",
    )
    def status(args):
        return ct.status()

    @reg.tool(
        name="trpg_combat_next_turn",
        description="推进到下一个行动单位。自动跳过死亡单位，回到底部时开新回合。",
        schema={"name": "trpg_combat_next_turn", "parameters": _NO_PARAMS},
        emoji="➡️",
    )
    def next_turn(args):
        r = ct.next_turn()
        if not r.get("success"):
            return f"❌ {r.get('error', '推进失败')}"
        lines = []
        if r.get("is_new_round"):
            lines.append(f"━ 第 {r['round']} 回合 ━\n")
        icon = "🧙" if r.get("is_player") else "👹"
        lines.append(f"➡️ 轮到 {r['current']} 行动 {icon}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_combat_damage",
        description="对怪物造成伤害。自动扣除 HP，HP 归零时标记死亡并从先攻跳过。",
        schema={
            "name": "trpg_combat_damage",
            "parameters": {
                "type": "object",
                "properties": {
                    "creature_ref": {"type": "string", "description": "怪物标识（先攻列表里的名字或 ref_id）"},
                    "amount": {"type": "integer", "description": "伤害数值"},
                    "damage_type": {"type": "string", "description": "伤害类型：穿刺/挥砍/钝击/火焰/寒冷/毒素等", "default": ""},
                    "source": {"type": "string", "description": "伤害来源", "default": "玩家攻击"},
                },
                "required": ["creature_ref", "amount"],
            },
        },
        emoji="💥",
    )
    def damage(args):
        r = ct.damage_creature(args.get("creature_ref", ""), args.get("amount", 0),
                                 args.get("damage_type", ""), args.get("source", "玩家攻击"))
        if not r.get("success"):
            return f"❌ {r.get('error', '操作失败')}"
        lines = [f"💥 {r['name']} 受到 {r['damage']} 点{args.get('damage_type', '')}伤害"]
        if r.get("calc_steps"):
            lines.append("📐 计算过程:")
            for s in r["calc_steps"]:
                lines.append(f"   • {s}")
        lines.append(f"❤️ 剩余HP: {r['hp_current']}/{r['hp_max']}")
        if r.get("temp_hp", 0) > 0:
            lines.append(f"🛡️ 临时HP: {r['temp_hp']}")
        if r.get("killed"):
            lines.append("💀 目标倒下！")
        if r.get("rule_reference"):
            lines.append(f"\n{r['rule_reference']}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_combat_heal",
        description="治疗怪物（或玩家治疗敌人... 很少用）。",
        schema={
            "name": "trpg_combat_heal",
            "parameters": {
                "type": "object",
                "properties": {
                    "creature_ref": {"type": "string", "description": "怪物标识"},
                    "amount": {"type": "integer", "description": "治疗数值"},
                    "source": {"type": "string", "description": "来源", "default": ""},
                },
                "required": ["creature_ref", "amount"],
            },
        },
        emoji="💚",
    )
    def heal(args):
        r = ct.heal_creature(args.get("creature_ref", ""), args.get("amount", 0), args.get("source", ""))
        if not r.get("success"):
            return f"❌ {r.get('error', '操作失败')}"
        return f"💚 {r['name']} 恢复 {r['healed']} HP\n   HP: {r['hp_current']}/{r['hp_max']}"

    @reg.tool(
        name="trpg_combat_condition_add",
        description="给怪物添加状态效果（中毒/眩晕/定身/着火等）。",
        schema={
            "name": "trpg_combat_condition_add",
            "parameters": {
                "type": "object",
                "properties": {
                    "creature_ref": {"type": "string", "description": "怪物标识"},
                    "condition_name": {"type": "string", "description": "状态名（英文标识）"},
                    "display_name": {"type": "string", "description": "显示名（中文）", "default": ""},
                    "duration": {"type": "string", "description": "持续时间，如 '1分钟' / '到战斗结束'", "default": ""},
                },
                "required": ["creature_ref", "condition_name"],
            },
        },
        emoji="☠️",
    )
    def add_cond(args):
        r = ct.add_condition(args.get("creature_ref", ""), args.get("condition_name", ""),
                               args.get("display_name", ""), args.get("duration", ""))
        if not r.get("success"):
            return f"❌ {r.get('error', '操作失败')}"
        return f"☠️ {r['name']} 获得状态: {args.get('display_name', '') or args.get('condition_name', '')}"

    @reg.tool(
        name="trpg_combat_creature_add",
        description="中途加入一个战斗单位（援军/召唤物/新敌人）。",
        schema={
            "name": "trpg_combat_creature_add",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "单位名称"},
                    "initiative": {"type": "integer", "description": "先攻值"},
                    "template_id": {"type": "string", "description": "怪物模板 ID（如果是怪物）", "default": ""},
                    "is_player": {"type": "boolean", "description": "是否是玩家/盟友", "default": False},
                },
                "required": ["name", "initiative"],
            },
        },
        emoji="➕",
    )
    def add_creature(args):
        r = ct.add_creature(args.get("name", ""), args.get("initiative", 0),
                              template_id=args.get("template_id", ""),
                              is_player=args.get("is_player", False))
        if not r.get("success"):
            return f"❌ {r.get('error', '操作失败')}"
        return f"➕ {r['name']} 加入战斗（先攻 {r['initiative']}）"

    @reg.tool(
        name="trpg_combat_end",
        description="结束战斗。标记战斗结束，保存战斗日志。",
        schema={
            "name": "trpg_combat_end",
            "parameters": {
                "type": "object",
                "properties": {"result": {"type": "string", "description": "结果：胜利/失败/逃跑/平局", "default": "胜利"}},
                "required": [],
            },
        },
        emoji="🏁",
    )
    def end(args):
        r = ct.end_combat(args.get("result", "胜利"))
        if not r.get("success"):
            return f"❌ {r.get('error', '操作失败')}"
        return f"🏁 战斗结束：{r['result']}\n共 {r['rounds']} 回合，{r['log_entries']} 条日志。"

    @reg.tool(
        name="trpg_combat_log",
        description="查看最近的战斗日志。",
        schema={
            "name": "trpg_combat_log",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "查看最近多少条", "default": 10}},
                "required": [],
            },
        },
        emoji="📜",
    )
    def log(args):
        log = ct.get_log(args.get("limit", 10))
        if not log:
            return "（没有战斗日志）"
        lines = [f"战斗日志（最近 {len(log)} 条）:", ""]
        for e in log:
            lines.append(f"  • [{e.get('round', '?')}R{getattr(e, 'turn_index', '')}] {e.get('message', '')}")
        return "\n".join(lines)
