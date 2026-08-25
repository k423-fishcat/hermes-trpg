"""跑团状态管理命令 (/state) — 多战役 + 多模板版本"""

import shlex
from typing import Any

from .app_context import get_app
from .state import StateManager  # 仅用于类型注解


def handle_state_command(raw_args: str) -> str:
    """处理 /state 斜杠命令"""
    mgr = get_app().state

    if not raw_args or raw_args.strip() in ("help", "-h", "--help"):
        return _HELP_TEXT

    args = shlex.split(raw_args.strip())
    sub = args[0]

    try:
        # === 战役管理 ===
        if sub in ("campaign", "战役"):
            if len(args) < 2:
                # 列出战役
                campaigns = mgr.list_campaigns()
                if not campaigns:
                    return "（还没有战役，用 /state campaign create <名> 创建）"
                lines = [f"战役列表（共 {len(campaigns)} 个）:", ""]
                for c in campaigns:
                    current = " <-- 当前" if c["name"] == mgr.campaign_name else ""
                    tmpl = c.get("template", "")
                    v = c.get("version", 0)
                    disp = c.get("display_name", c["name"])
                    lines.append(f"  - {disp} [{tmpl}] v{v}{current}")
                return "\n".join(lines)

            op = args[1]
            if op == "create" and len(args) >= 3:
                name = args[2]
                tmpl = args[3] if len(args) > 3 else "dnd5e"
                display = args[4] if len(args) > 4 else ""
                r = mgr.create_campaign(name, tmpl, display)
                if r.get("success"):
                    return f"✅ 已创建战役: {r.get('display_name')}（模板: {r.get('template')}）"
                else:
                    return f"❌ {r.get('error', '创建失败')}"

            elif op == "switch" and len(args) >= 3:
                name = args[2]
                r = mgr.switch_campaign(name)
                if r.get("success"):
                    return f"✅ 已切换到战役: {name}（模板: {r.get('template')}）"
                else:
                    return f"❌ {r.get('error', '切换失败')}"

            elif op == "delete" and len(args) >= 3:
                name = args[2]
                if name == mgr.campaign_name:
                    return "❌ 不能删除当前战役，请先切换到其他战役"
                r = mgr.delete_campaign(name)
                return f"✅ 已删除战役: {name}" if r.get("success") else f"❌ {r.get('error')}"

        elif sub in ("templates", "模板"):
            tmpls = mgr.list_templates()
            lines = [f"可用模板（共 {len(tmpls)} 个）:", ""]
            for t in tmpls:
                lines.append(f"  - {t['name']}（{t['display_name']}）")
                if t.get("description"):
                    lines.append(f"    {t['description']}")
            return "\n".join(lines)

        # === 状态查看 ===
        elif sub in ("status", "s", "状态"):
            return _format_status_summary(mgr)

        elif sub in ("get", "g", "查看"):
            path = args[1] if len(args) > 1 else ""
            val = mgr.get(path)
            if isinstance(val, (dict, list)):
                import json
                return json.dumps(val, ensure_ascii=False, indent=2)
            return str(val)

        # === 生命值 ===
        elif sub in ("damage", "dmg", "受伤"):
            if len(args) < 2:
                return "用法: /state damage <数值> [来源]"
            amount = int(args[1])
            source = args[2] if len(args) > 2 else "未知"
            current = mgr.get("player.hp.current") or mgr.get("derived.hp_current") or 0
            hp_max = mgr.get("player.hp.max") or mgr.get("derived.hp_max") or 0
            new_hp = max(0, current - amount)
            r = mgr.update({"player.hp.current": new_hp} if mgr.get("player.hp") else {"derived.hp_current": new_hp},
                          reason=f"受到 {amount} 点伤害（来源: {source}）", actor=source)
            msg = f"受到 {amount} 点伤害（{source}）\nHP: {new_hp}/{hp_max}"
            if new_hp <= 0:
                msg += "\n⚠️ 生命值归零！"
            return msg

        elif sub in ("heal", "治疗"):
            if len(args) < 2:
                return "用法: /state heal <数值> [来源]"
            amount = int(args[1])
            source = args[2] if len(args) > 2 else "未知"
            current = mgr.get("player.hp.current") or mgr.get("derived.hp_current") or 0
            hp_max = mgr.get("player.hp.max") or mgr.get("derived.hp_max") or 0
            new_hp = min(hp_max, current + amount)
            path = "player.hp.current" if mgr.get("player.hp") is not None else "derived.hp_current"
            r = mgr.update({path: new_hp},
                          reason=f"恢复 {amount} 点生命值（来源: {source}）", actor="系统")
            return f"恢复 {amount} 点生命（{source}）\nHP: {new_hp}/{hp_max}"

        # === 金币/金钱 ===
        elif sub in ("gold", "money", "金币", "钱"):
            if len(args) < 2:
                gold = mgr.get("player.gold") or mgr.get("cash_dollars") or 0
                return f"金钱: {gold}"
            op = args[1]
            amount = int(args[2]) if len(args) > 2 else 0
            if op in ("add", "+"):
                source = args[3] if len(args) > 3 else ""
                current = mgr.get("player.gold") or mgr.get("cash_dollars") or 0
                path = "player.gold" if mgr.get("player.gold") is not None else "cash_dollars"
                mgr.update({path: current + amount},
                          reason=f"获得 {amount} 金币（{source}）" if source else f"获得 {amount} 金币",
                          actor="系统")
                return f"💰 获得 {amount}\n当前: {current + amount}"
            elif op in ("spend", "-"):
                reason = args[3] if len(args) > 3 else ""
                current = mgr.get("player.gold") or mgr.get("cash_dollars") or 0
                if current < amount:
                    return f"❌ 金钱不足（{current}/{amount}）"
                path = "player.gold" if mgr.get("player.gold") is not None else "cash_dollars"
                mgr.update({path: current - amount},
                          reason=f"花费 {amount} 金币（{reason}）" if reason else f"花费 {amount} 金币",
                          actor="玩家")
                return f"💰 花费 {amount}\n剩余: {current - amount}"

        # === 背包 ===
        elif sub in ("inv", "inventory", "背包"):
            inv = mgr.get("inventory") or []
            if len(args) < 2:
                if not inv:
                    return "背包是空的。"
                lines = [f"背包（{len(inv)} 件）:", ""]
                for i in inv:
                    lines.append(f"  - {i['name']} x{i.get('qty', 1)}")
                    if i.get("desc"):
                        lines.append(f"    {i['desc']}")
                return "\n".join(lines)
            op = args[1]
            if op == "add" and len(args) >= 3:
                name = args[2]
                qty = int(args[3]) if len(args) > 3 else 1
                desc = args[4] if len(args) > 4 else ""
                for item in inv:
                    if item.get("name") == name:
                        item["qty"] = item.get("qty", 0) + qty
                        mgr.update({"inventory": inv}, reason=f"获得物品: {name} x{qty}", actor="系统")
                        return f"✅ 获得物品: {name} x{qty}"
                inv.append({"name": name, "qty": qty, "desc": desc})
                mgr.update({"inventory": inv}, reason=f"获得物品: {name} x{qty}", actor="系统")
                return f"✅ 获得物品: {name} x{qty}"
            elif op == "remove" and len(args) >= 3:
                name = args[2]
                qty = int(args[3]) if len(args) > 3 else 1
                for i, item in enumerate(inv):
                    if item.get("name") == name:
                        cur = item.get("qty", 0)
                        if cur < qty:
                            return f"❌ {name} 数量不足（{cur}/{qty}）"
                        if cur == qty:
                            inv.pop(i)
                        else:
                            item["qty"] = cur - qty
                        mgr.update({"inventory": inv}, reason=f"失去物品: {name} x{qty}", actor="系统")
                        return f"✅ 失去物品: {name} x{qty}"
                return f"❌ 背包中没有: {name}"

        # === 状态效果 ===
        elif sub in ("cond", "condition", "状态"):
            conds = mgr.get("player.conditions") or mgr.get("conditions") or []
            if len(args) < 2:
                if not conds:
                    return "无状态效果。"
                lines = ["状态效果:", ""]
                for c in conds:
                    name = c.get("display_name") or c.get("name", "")
                    src = c.get("source", "")
                    lines.append(f"  - {name}（来自{src}）" if src else f"  - {name}")
                return "\n".join(lines)
            op = args[1]
            if op == "add" and len(args) >= 3:
                name = args[2]
                display = args[3] if len(args) > 3 else name
                source = args[4] if len(args) > 4 else ""
                conds.append({
                    "name": name, "display_name": display,
                    "source": source, "start_time": __import__("time").time(),
                })
                path = "player.conditions" if mgr.get("player.conditions") is not None else "conditions"
                mgr.update({path: conds}, reason=f"获得状态: {display}", actor=source or "系统")
                return f"✅ 获得状态: {display}"
            elif op == "remove" and len(args) >= 3:
                name = args[2]
                new_conds = [c for c in conds if c.get("name") != name]
                if len(new_conds) == len(conds):
                    return f"❌ 未找到状态: {name}"
                path = "player.conditions" if mgr.get("player.conditions") is not None else "conditions"
                mgr.update({path: new_conds}, reason=f"移除状态: {name}", actor="系统")
                return f"✅ 移除状态: {name}"

        # === NPC 状态 ===
        elif sub in ("npc", "NPC"):
            npcs = mgr.get("npcs") or {}
            if len(args) < 2:
                if not npcs:
                    return "（没有 NPC 状态记录）"
                lines = [f"NPC 状态（共 {len(npcs)} 个）:", ""]
                for name, npc in npcs.items():
                    loc = npc.get("location", "")
                    alive = npc.get("alive", True)
                    attitude = npc.get("attitude", "")
                    status = "✅" if alive else "💀"
                    lines.append(f"  {status} {name} @ {loc} [{attitude}]")
                return "\n".join(lines)
            name = args[1]
            if len(args) < 3:
                npc = npcs.get(name)
                if not npc:
                    return f"（没有 {name} 的状态记录）"
                import json
                return json.dumps(npc, ensure_ascii=False, indent=2)
            # 设置字段: /state npc 老比尔 location 醉海豹酒馆
            field = args[2]
            value = args[3] if len(args) > 3 else ""
            npc_data = npcs.get(name, {})
            npc_data[field] = value
            mgr.update({f"npcs.{name}": npc_data}, reason=f"更新 NPC: {name}.{field}", actor="DM")
            return f"✅ 已更新 NPC {name}: {field} = {value}"

        # === 世界状态 ===
        elif sub in ("world", "flag", "世界"):
            world = mgr.get("world") or {}
            if len(args) < 2:
                if not world:
                    return "（没有世界状态标记）"
                import json
                return json.dumps(world, ensure_ascii=False, indent=2)
            flag = args[1]
            if len(args) < 3:
                return f"{flag} = {world.get(flag, '未设置')}"
            value = args[2]
            try: value = int(value)
            except ValueError:
                if value.lower() == "true": value = True
                elif value.lower() == "false": value = False
            mgr.update({f"world.{flag}": value}, reason=f"世界状态: {flag} = {value}", actor="DM")
            return f"✅ 世界状态: {flag} = {value}"

        # === 任务 ===
        elif sub in ("quest", "任务"):
            quests = mgr.get("quests") or {}
            if len(args) < 2:
                if not quests:
                    return "（没有任务）"
                lines = ["任务列表:", ""]
                for name, q in quests.items():
                    status = q.get("status", "未知")
                    step = q.get("current_step", "")
                    lines.append(f"  [{status}] {name}: {step}")
                return "\n".join(lines)
            op = args[1]
            if op == "update" and len(args) >= 3:
                name = args[2]
                status = args[3] if len(args) > 3 else ""
                step = args[4] if len(args) > 4 else ""
                notes = args[5] if len(args) > 5 else ""
                quest = quests.get(name, {})
                if status: quest["status"] = status
                if step: quest["current_step"] = step
                if notes:
                    quest.setdefault("notes", []).append({"time": __import__("time").time(), "text": notes})
                mgr.update({f"quests.{name}": quest}, reason=f"任务更新: {name}", actor="DM")
                return f"✅ 任务已更新: {name}"

        # === 回滚 ===
        elif sub in ("undo", "rollback", "回滚"):
            steps = int(args[1]) if len(args) > 1 else 1
            r = mgr.undo(steps)
            if r.get("success"):
                return f"⏪ 已回滚 {r.get('steps_rolled_back', 0)} 步\n版本: v{r.get('old_version')} → v{r.get('new_version')}"
            else:
                return f"❌ {r.get('error', '回滚失败')}"

        # === 事件日志 ===
        elif sub in ("log", "日志"):
            n = int(args[1]) if len(args) > 1 else 10
            events = mgr.get("event_log") or []
            recent = events[-n:]
            if not recent:
                return "（没有事件记录）"
            import time as _time
            lines = [f"最近 {len(recent)} 条事件:", ""]
            for ev in reversed(recent):
                t = _time.strftime("%H:%M:%S", _time.localtime(ev.get("time", 0)))
                actor = ev.get("actor", "?")
                reason = ev.get("reason", "")
                lines.append(f"  v{ev.get('version', '?')} [{t}] {actor}: {reason}")
            return "\n".join(lines)

        # === 通用 set ===
        elif sub in ("set", "update"):
            if len(args) < 3:
                return "用法: /state set <path> <value>"
            path = args[1]
            value = args[2]
            try: value = int(value)
            except ValueError:
                try: value = float(value)
                except ValueError: pass
            r = mgr.update({path: value}, reason=f"手动设置: {path}", actor="DM")
            return f"✅ 已设置 {path} = {value}（版本 v{r['version']}）"

        else:
            return f"未知子命令: {sub}\n\n{_HELP_TEXT}"

    except Exception as e:
        import traceback
        return f"❌ 命令执行失败: {e}\n{traceback.format_exc()}"


def _format_status_summary(mgr: StateManager) -> str:
    """格式化状态总览（适配不同模板）"""
    s = mgr.load()
    tmpl = s.get("template", "dnd5e")

    lines = [
        f"📊 角色状态（{s.get('campaign', '未命名')}）",
        "=" * 30,
    ]

    # DnD 风格
    if tmpl == "dnd5e":
        p = s.get("player", {})
        hp = p.get("hp", {})
        conds = p.get("conditions", [])
        cond_text = ", ".join(c.get("display_name", c.get("name", "")) for c in conds) if conds else "无"
        inv = s.get("inventory", [])
        inv_items = ", ".join(f"{i['name']}x{i.get('qty', 1)}" for i in inv[:8])
        if len(inv) > 8:
            inv_items += f" 等{len(inv)}件"
        quests = s.get("quests", {})
        active = [n for n, q in quests.items() if q.get("status") in ("进行中", "in_progress", "active")]

        lines += [
            f"角色: {p.get('name', '未命名')} | {p.get('race', '')} {p.get('class', '')} Lv.{p.get('level', 1)}",
            f"HP: {hp.get('current', 0)}/{hp.get('max', 0)}" + (f" (+{hp.get('temp', 0)} 临时)" if hp.get("temp") else ""),
            f"AC: {p.get('ac', 10)} | 速度: {p.get('speed', 30)}尺",
            f"金币: {p.get('gold', 0)} GP",
            f"状态: {cond_text}",
            "",
            "💪 属性:",
            f"  STR {p['abilities'].get('str', 10):>2}  DEX {p['abilities'].get('dex', 10):>2}  CON {p['abilities'].get('con', 10):>2}",
            f"  INT {p['abilities'].get('int', 10):>2}  WIS {p['abilities'].get('wis', 10):>2}  CHA {p['abilities'].get('cha', 10):>2}",
            f"  熟练加值: +{p.get('proficiency_bonus', 2)}",
            "",
            "🎒 背包:",
            f"  {inv_items or '(空)'}",
            "",
            f"📜 任务: {len(active)} 个进行中",
        ]
        for q in active[:5]:
            qd = quests[q]
            step = qd.get("current_step", "")
            lines.append(f"  - {q}: {step}")

    # COC 风格
    elif tmpl == "coc7e":
        inv = s.get("investigator", {})
        chars = s.get("characteristics", {})
        der = s.get("derived", {})
        conds = s.get("conditions", [])
        cond_text = ", ".join(c.get("display_name", c.get("name", "")) for c in conds) if conds else "无"

        lines += [
            f"调查员: {inv.get('name', '未命名')}",
            f"职业: {inv.get('occupation', '')} | 年龄: {inv.get('age', '?')}",
            f"HP: {der.get('hp_current', 0)}/{der.get('hp_max', 0)}",
            f"理智: {der.get('san_current', 0)}/{der.get('san_max', 0)}",
            f"魔法值: {der.get('mp_current', 0)}/{der.get('mp_max', 0)}",
            f"状态: {cond_text}",
            "",
            "📐 特征值:",
            f"  STR {chars.get('str', '?')}  CON {chars.get('con', '?')}  SIZ {chars.get('siz', '?')}",
            f"  DEX {chars.get('dex', '?')}  APP {chars.get('app', '?')}  INT {chars.get('int', '?')}",
            f"  POW {chars.get('pow', '?')}  EDU {chars.get('edu', '?')}  LUK {chars.get('luk', '?')}",
        ]

    # 通用
    else:
        lines.append("（自定义模板，用 /state get 查看详细字段）")

    lines += ["", f"版本: v{s.get('version', 0)} | 模板: {tmpl} | 战役: {s.get('campaign', '')}"]
    return "\n".join(lines)


_HELP_TEXT = """\
/state — 跑团状态管理（多战役 + 多模板）

战役管理:
  campaign                   列出所有战役
  campaign create <名> [模板] [显示名]
                             创建新战役（默认模板 dnd5e）
  campaign switch <名>       切换战役
  campaign delete <名>       删除战役
  templates                  列出可用模板

状态查看:
  status / s                 状态总览
  get <路径>                 查看指定路径
  log [N]                    最近 N 条事件日志

生命值:
  damage / dmg <n> [来源]     受到伤害
  heal <n> [来源]            恢复生命

金钱:
  gold                       查看金钱
  gold add <n> [来源]        获得
  gold spend <n> [原因]      花费

背包:
  inv                        查看背包
  inv add <名> [数量] [描述]  添加
  inv remove <名> [数量]     移除

状态效果:
  cond                       查看状态
  cond add <名> [显示名] [来源]
  cond remove <名>

NPC:
  npc                        列出 NPC 状态
  npc <名字>                 查看 NPC 详情
  npc <名字> <字段> <值>     设置 NPC 字段

世界状态:
  world / flag               查看所有标记
  world <标记> <值>          设置标记

任务:
  quest                      任务列表
  quest update <名> [状态] [步骤] [备注]

其他:
  set <path> <value>         手动设置任意值
  undo [步数]                回滚状态（默认 1 步）
  help                       显示帮助
"""
