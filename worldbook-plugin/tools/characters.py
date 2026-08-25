"""角色卡工具"""

from .registry import ToolRegistry


_NO_PARAMS = {"type": "object", "properties": {}, "required": []}


def register(reg: ToolRegistry, char_mgr, state):
    @reg.tool(
        name="trpg_char_list",
        description="列出所有已创建的角色卡。",
        schema={"name": "trpg_char_list", "parameters": _NO_PARAMS},
        emoji="👤",
    )
    def list_c(args):
        chars = char_mgr.list_characters()
        if not chars:
            return "（还没有创建角色卡）"
        lines = [f"👤 角色卡列表（共 {len(chars)} 个）", ""]
        for c in chars:
            lines.append(f"  [{c['id']}] {c['name']}")
            lines.append(f"     {c.get('race', '?')} {c.get('class', '?')} Lv{c.get('level', '?')}")
            lines.append(f"     HP {c.get('hp_max', '?')} | AC {c.get('ac', '?')}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_char_sheet",
        description="查看一个角色的完整角色卡数据。",
        schema={
            "name": "trpg_char_sheet",
            "parameters": {
                "type": "object",
                "properties": {"char_id": {"type": "string", "description": "角色 ID（文件名）"}},
                "required": ["char_id"],
            },
        },
        emoji="📋",
    )
    def sheet(args):
        char = char_mgr.load_character(args.get("char_id", ""))
        if not char:
            return f"❌ 角色不存在: {args.get('char_id', '')}"
        lines = [
            f"📋 {char.name}",
            "=" * 40,
            f"{char.race} {char.class_name}"
            + (f"（{char.subclass}）" if char.subclass else "")
            + f"  Lv{char.level}",
            f"背景: {char.background} | 阵营: {char.alignment}",
            f"XP: {char.xp} / {char.next_level_xp}",
            "",
            f"HP: {char.hp_max} | AC: {char.ac} | 速度: {char.speed}尺",
            f"命中骰: {char.hit_dice_total} | 熟练加值: +{char.proficiency_bonus}",
            f"被动感知: {char.passive_perception}",
            "",
            "属性:",
        ]
        cn = {"str": "力量", "dex": "敏捷", "con": "体质", "int": "智力", "wis": "感知", "cha": "魅力"}
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            score = char.abilities.get(ab, 10)
            mod = (score - 10) // 2
            sm = char.save_bonus(ab)
            lines.append(f"  {cn[ab]}: {score:2d} ({mod:+d})  豁免+{sm}")
        lines.append("\n技能:")
        for skill in sorted(char.skill_proficiencies):
            b = char.skill_bonus(skill)
            exp = "（专长）" if skill in char.skill_expertise else ""
            lines.append(f"  • {skill}: +{b}{exp}")
        if char.gold:
            lines.append(f"\n金币: {char.gold} gp")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_char_status",
        description="查看当前玩家的快速状态：HP、命中骰、法术位、等级、XP、被动感知等。",
        schema={"name": "trpg_char_status", "parameters": _NO_PARAMS},
        emoji="🩸",
    )
    def status(args):
        player = state.get("player") or {}
        if not player:
            return "（没有玩家状态数据）"
        hp = player.get("hp", {})
        hd = player.get("hit_dice", {})
        level = player.get("level", 1)
        xp = player.get("xp", 0)
        name = player.get("name", "冒险者")
        ac = player.get("ac", "?")
        passive = player.get("passive_perception", "?")
        insp = player.get("inspiration", False)
        from ..characters import XP_THRESHOLDS
        next_xp = XP_THRESHOLDS.get(level, 999999)
        xp_pct = int(xp / next_xp * 100) if next_xp > 0 else 100
        lines = [
            f"🩸 {name}  Lv{level}",
            "=" * 30,
            f"HP: {hp.get('current', 0)}/{hp.get('max', 0)}"
            + (f" (+{hp.get('temp', 0)}临时)" if hp.get('temp', 0) else ""),
            f"命中骰: {hd.get('used', 0)}/{hd.get('total', '1d8')}",
            f"AC: {ac} | 被动感知: {passive}" + (" | ⭐灵感" if insp else ""),
            f"XP: {xp} / {next_xp} ({xp_pct}%)",
        ]
        slots = player.get("spell_slots", {})
        slots_max = player.get("spell_slots_max", {})
        if slots_max:
            slot_strs = [f"{l}环 {slots.get(l, 0)}/{mx}" for l, mx in sorted(slots_max.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)]
            lines.append(f"法术位: {' | '.join(slot_strs)}")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_award_xp",
        description="奖励玩家 XP。如果达到升级阈值，会提示可以升级。",
        schema={
            "name": "trpg_award_xp",
            "parameters": {
                "type": "object",
                "properties": {
                    "xp": {"type": "integer", "description": "XP 数量（正数）"},
                    "reason": {"type": "string", "description": "奖励原因", "default": ""},
                },
                "required": ["xp"],
            },
        },
        emoji="⭐",
    )
    def award_xp(args):
        xp = args.get("xp", 0)
        if xp <= 0:
            return "❌ XP 必须是正数"
        player = state.get("player") or {}
        current_xp = player.get("xp", 0)
        new_xp = current_xp + xp
        level = player.get("level", 1)
        player["xp"] = new_xp
        from ..characters import XP_THRESHOLDS
        next_xp = XP_THRESHOLDS.get(level, 999999)
        can = new_xp >= next_xp
        state.update({"player": player}, reason=f"获得 XP: +{xp}（{args.get('reason', '')}）", actor="DM")
        lines = [f"⭐ 获得 {xp} XP", f"总 XP: {current_xp} → {new_xp}", f"等级: {level} | 下一级需要: {next_xp}"]
        if can:
            lines.append("\n🎉 可以升级了！使用 trpg_level_up 完成升级。")
        return "\n".join(lines)

    @reg.tool(
        name="trpg_level_up",
        description="执行升级。增加等级、HP、熟练加值，扣减对应 XP。",
        schema={
            "name": "trpg_level_up",
            "parameters": {
                "type": "object",
                "properties": {
                    "hp_roll": {"type": "integer", "description": "升级 HP 掷骰结果（不提供则自动掷）"},
                    "extra_abilities": {"type": "array", "description": "加属性（每 4 级 1 次）", "items": {"type": "string"}},
                },
                "required": [],
            },
        },
        emoji="⬆️",
    )
    def level_up(args):
        from ..dice import roll_hit_dice
        from ..characters import XP_THRESHOLDS
        player = state.get("player") or {}
        level = player.get("level", 1)
        xp = player.get("xp", 0)
        hd_total = player.get("hit_dice", {}).get("total", "1d8")
        next_xp = XP_THRESHOLDS.get(level, 999999)
        if xp < next_xp:
            return f"❌ XP 不足: {xp} / {next_xp}"
        new_level = level
        for lvl in range(level + 1, 21):
            if xp >= XP_THRESHOLDS.get(lvl, 999999):
                new_level = lvl
            else:
                break
        levels_gained = new_level - level
        if levels_gained == 0:
            return "❌ 无法升级"
        new_prof = 2 + (new_level - 1) // 4
        con_score = player.get("abilities", {}).get("con", 10)
        con_mod = (con_score - 10) // 2
        sides = int(str(hd_total).split('d')[1]) if 'd' in str(hd_total) else 8
        hp_added = 0
        rolls = []
        hp_roll = args.get("hp_roll")
        extra_abilities = args.get("extra_abilities") or []
        for _ in range(levels_gained):
            if hp_roll is not None:
                roll = hp_roll
                hp_roll = None
            else:
                roll = roll_hit_dice(sides)
            heal = max(1, roll + con_mod)
            rolls.append(roll)
            hp_added += heal
        ability_bump_msg = ""
        if extra_abilities:
            ability_levels = [4, 8, 12, 16, 19]
            bumped = any(lvl in ability_levels for lvl in range(level + 1, new_level + 1))
            if bumped:
                for ab in extra_abilities[:2]:
                    ab = ab.lower()
                    if ab in player.get("abilities", {}):
                        player["abilities"][ab] += 1
                ability_bump_msg = f"属性提升: {', '.join(extra_abilities)} +1"
        player["level"] = new_level
        player["proficiency_bonus"] = new_prof
        player["hp"]["max"] = player["hp"].get("max", 0) + hp_added
        player["hp"]["current"] = player["hp"]["current"] + hp_added
        num_hd = int(str(hd_total).split('d')[0]) if 'd' in str(hd_total) else 1
        new_hd_total = f"{num_hd + levels_gained}d{sides}"
        player["hit_dice"]["total"] = new_hd_total
        wis_score = player.get("abilities", {}).get("wis", 10)
        player["passive_perception"] = 10 + (wis_score - 10) // 2 + new_prof
        state.update({"player": player}, reason=f"升级: Lv{level} → Lv{new_level}", actor="DM")
        lines = [
            f"⬆️ 升级！Lv{level} → Lv{new_level}",
            "=" * 30,
            f"HP 增加: +{hp_added}（掷骰 {rolls} + 体质{con_mod:+d}）",
            f"新 HP: {player['hp']['max']}",
            f"命中骰: {new_hd_total} | 熟练加值: +{new_prof}",
        ]
        if ability_bump_msg:
            lines.append(ability_bump_msg)
        lines.append(f"\n⭐ 恭喜升到 {new_level} 级！")
        return "\n".join(lines)
