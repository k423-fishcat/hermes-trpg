"""叙事层命令处理 — /chronicle /quest /npc /time

四个模块的统一命令入口。

P1.1 迁移：从独立 module-level singleton 改为 AppContext 统一容器。
通过 _chron() / _quest() / _npc() / _clk() 懒加载访问 app 上的对应 manager，
保持向后兼容（其他模块还没迁移也能用）。
"""

import shlex
from typing import Any

from .app_context import get_app


def _chron():
    """懒加载编年史 manager（来自 AppContext）"""
    return get_app().chronicle


def _quest():
    """懒加载任务 manager（来自 AppContext）"""
    return get_app().quests


def _npc():
    """懒加载 NPC manager（来自 AppContext）"""
    return get_app().npcs


def _clk():
    """懒加载世界时钟（来自 AppContext）"""
    return get_app().clock


# ====================================================================
# /chronicle — 编年史
# ====================================================================

def handle_chronicle_command(raw_args: str) -> str:
    """处理 /chronicle 命令"""
    if not raw_args or raw_args.strip() in ("help", "-h"):
        return _CHRONICLE_HELP

    args = shlex.split(raw_args.strip())
    sub = args[0]

    try:
        if sub in ("chapter", "章"):
            if len(args) < 2:
                # 列出章节
                chapters = _chron().list_chapters()
                if not chapters:
                    return "（还没有章节）"
                lines = [f"章节列表（共 {len(chapters)} 章）:", ""]
                for ch in chapters:
                    marker = " <-- 当前" if _chron().is_current_chapter(ch["id"]) else ""
                    status = "进行中" if ch["status"] == "in_progress" else "已完成"
                    lines.append(f"  [{status}] {ch['id']}. {ch['title']}{marker}")
                return "\n".join(lines)

            op = args[1]
            if op in ("new", "start", "新建", "开始") and len(args) >= 3:
                title = args[2]
                desc = args[3] if len(args) > 3 else ""
                r = _chron().new_chapter(title, desc)
                if r.get("success"):
                    return f"📖 新章节开启：{title}\n\n用 /chronicle add <事件> 记录大事。"
                return f"❌ {r.get('error')}"

            elif op in ("end", "close", "结束") and len(args) >= 2:
                summary = args[2] if len(args) > 2 else ""
                r = _chron().end_chapter(summary)
                if r.get("success"):
                    return f"📖 章节结束。" + (f"\n摘要: {summary}" if summary else "")
                return f"❌ {r.get('error')}"

        elif sub in ("add", "record", "记录", "加"):
            if len(args) < 2:
                return "用法: /chronicle add <事件描述>"
            event = raw_args[len(sub)+1:].strip()
            importance = "normal"
            # 检测重要性标记
            if event.startswith("!"):
                importance = "important"
                event = event[1:].strip()
            elif event.startswith("!!"):
                importance = "major"
                event = event[2:].strip()
            r = _chron().add_event(event, importance)
            icon = "⭐" if importance in ("important", "major") else "•"
            return f"{icon} 已记录: {event}"

        elif sub in ("recap", "summary", "前情", "提要", "回顾"):
            return _chron().recap()

        elif sub in ("list", "列表", "ls"):
            chapters = _chron().list_chapters()
            if not chapters:
                return "（还没有章节）"
            lines = []
            for ch in chapters:
                status = "进行中" if ch["status"] == "in_progress" else "✓ 已完成"
                lines.append(f"[{status}] {ch['id']}. {ch['title']}")
                for hl in ch.get("highlights", [])[-5:]:
                    icon = "⭐" if hl["importance"] in ("important", "major") else "  •"
                    lines.append(f"   {icon} {hl['event']}")
                lines.append("")
            return "\n".join(lines)

        elif sub in ("search", "搜", "搜索"):
            if len(args) < 2:
                return "用法: /chronicle search <关键词>"
            keyword = args[1]
            results = _chron().search_events(keyword)
            if not results:
                return f"（没有找到和「{keyword}」相关的记录）"
            lines = [f"找到 {len(results)} 条相关记录:", ""]
            for r in results:
                lines.append(f"  [{r['chapter']}] {r['event']}")
            return "\n".join(lines)

        elif sub in ("status", "状态"):
            chron = _chron().get_chronicle()
            chapters = chron.get("chapters", [])
            current = _chron().get_current_chapter()
            total_events = sum(len(ch.get("highlights", [])) for ch in chapters)
            lines = [
                "📜 编年史状态",
                "=" * 30,
                f"章节数: {len(chapters)}",
                f"总事件数: {total_events}",
                f"当前章节: {current['title'] if current else '（无）'}",
            ]
            if current:
                lines.append(f"  本章节事件: {len(current.get('highlights', []))}")
            return "\n".join(lines)

        else:
            return f"未知子命令: {sub}\n\n{_CHRONICLE_HELP}"

    except Exception as e:
        import traceback
        return f"❌ 命令执行失败: {e}\n{traceback.format_exc()}"


_CHRONICLE_HELP = """\
/chronicle — 剧情编年史

章节管理:
  chapter                        列出章节
  chapter new <标题> [描述]      开启新章节
  chapter end [摘要]             结束当前章节

事件记录:
  add <事件描述>                 记录一件大事（加 ! 前缀=重要, !! = 重大）
  list                           列出所有章节和事件

前情提要:
  recap / 前情                   生成前情提要
  search <关键词>                搜索历史事件

其他:
  status                         编年史状态
  help                           帮助
"""


# ====================================================================
# /quest — 任务系统
# ====================================================================

def handle_quest_command(raw_args: str) -> str:
    """处理 /quest 命令"""
    if not raw_args or raw_args.strip() in ("help", "-h"):
        return _QUEST_HELP

    args = shlex.split(raw_args.strip())
    sub = args[0]

    try:
        if sub in ("list", "ls", "列表"):
            status_filter = args[1] if len(args) > 1 else ""
            quests = _quest().list_quests(status_filter)
            if not quests:
                return "（没有任务）"
            lines = [f"任务列表（共 {len(quests)} 个）:", ""]
            for q in quests:
                status_label = _quest_status_label(q.get("status", ""))
                icon = "⭐" if q.get("type") == "main" else "📜"
                step = ""
                if q.get("status") == "in_progress" and q.get("current_step"):
                    for s in q.get("steps", []):
                        if s["id"] == q["current_step"]:
                            step = f" — 当前: {s['title']}"
                            break
                lines.append(f"  {icon} [{status_label}] {q['title']}{step}")
            return "\n".join(lines)

        elif sub in ("show", "view", "详情"):
            if len(args) < 2:
                return "用法: /quest show <任务名>"
            qid = args[1]
            q = _quest().get_quest(qid)
            if not q:
                return f"❌ 任务不存在: {qid}"
            lines = [
                f"📜 {q['title']}",
                "=" * 30,
                f"类型: {q.get('type', '')}  |  状态: {_quest_status_label(q.get('status', ''))}",
                f"委托人: {q.get('giver', '未知')}",
                f"奖励: {q.get('rewards', '未知')}",
                "",
            ]
            if q.get("description"):
                lines += [q["description"], ""]
            if q.get("steps"):
                lines.append("任务步骤:")
                for s in q["steps"]:
                    s_status = s.get("status", "locked")
                    check = "✓" if s_status == "completed" else ("→" if s_status == "in_progress" else "○")
                    lines.append(f"  {check} {s['title']}")
                    if s.get("description") and s_status == "in_progress":
                        lines.append(f"     {s['description']}")
            if q.get("notes"):
                lines.append("")
                lines.append("备注:")
                for n in q["notes"][-5:]:
                    lines.append(f"  - {n.get('text', '')}")
            return "\n".join(lines)

        elif sub in ("start", "accept", "接取", "开始"):
            if len(args) < 2:
                return "用法: /quest start <任务ID>"
            r = _quest().start_quest(args[1])
            if r.get("success"):
                return f"✅ 任务开始: {r['title']}\n\n用 /quest step 推进任务步骤。"
            return f"❌ {r.get('error', '开始失败')}"

        elif sub in ("step", "advance", "下一步", "推进"):
            if len(args) < 2:
                return "用法: /quest step <任务ID>"
            r = _quest().advance_step(args[1])
            if r.get("success"):
                if r.get("all_done"):
                    return f"🎉 所有步骤已完成！\n用 /quest complete <任务ID> 完成任务并结算奖励。"
                return f"➡️ 任务推进\n\n下一步: {r['step_title']}\n{r.get('step_description', '')}"
            return f"❌ {r.get('error', '推进失败')}"

        elif sub in ("complete", "done", "完成"):
            if len(args) < 2:
                return "用法: /quest complete <任务ID> [备注]"
            qid = args[1]
            notes = args[2] if len(args) > 2 else ""
            r = _quest().complete_quest(qid, notes)
            if r.get("success"):
                return f"🎉 任务完成: {r['title']}\n\n奖励: {r.get('rewards', '无')}"
            return f"❌ {r.get('error', '完成失败')}"

        elif sub in ("fail", "失败"):
            if len(args) < 2:
                return "用法: /quest fail <任务ID> [原因]"
            qid = args[1]
            reason = args[2] if len(args) > 2 else ""
            r = _quest().fail_quest(qid, reason)
            if r.get("success"):
                return f"💀 任务失败: {qid}\n原因: {reason}"
            return f"❌ {r.get('error', '操作失败')}"

        elif sub in ("add", "new", "新建", "添加"):
            if len(args) < 3:
                return "用法: /quest add <ID> <标题> [描述] [类型] [委托人]"
            qid = args[1]
            title = args[2]
            desc = args[3] if len(args) > 3 else ""
            qtype = args[4] if len(args) > 4 else "side"
            giver = args[5] if len(args) > 5 else ""
            r = _quest().add_quest(qid, title, desc, quest_type=qtype, giver=giver)
            if r.get("success"):
                return f"✅ 任务已添加: {title} (ID: {qid})"
            return f"❌ {r.get('error', '添加失败')}"

        elif sub in ("check", "trigger", "检查触发"):
            r = _quest().check_triggers()
            if not r:
                return "（没有新解锁的任务）"
            lines = ["🔔 新任务解锁！", ""]
            for q in r:
                icon = "⭐" if q.get("type") == "main" else "📜"
                lines.append(f"  {icon} {q['title']}")
            lines.append("")
            lines.append("用 /quest start <任务ID> 接取任务。")
            return "\n".join(lines)

        else:
            return f"未知子命令: {sub}\n\n{_QUEST_HELP}"

    except Exception as e:
        import traceback
        return f"❌ 命令执行失败: {e}\n{traceback.format_exc()}"


def _quest_status_label(status: str) -> str:
    labels = {
        "hidden": "隐藏", "available": "可接取",
        "in_progress": "进行中", "completed": "已完成",
        "failed": "已失败",
    }
    return labels.get(status, status)


_QUEST_HELP = """\
/quest — 任务系统

查看:
  list [状态]                   任务列表（按状态过滤: in_progress/completed/...）
  show <任务ID>                 任务详情

操作:
  add <ID> <标题> [描述] [类型] [委托人]  添加任务
  start <任务ID>                 开始/接取任务
  step <任务ID>                  推进到下一步
  complete <任务ID> [备注]       完成任务
  fail <任务ID> [原因]           任务失败

其他:
  check                          检查任务触发条件
  help                           帮助
"""


# ====================================================================
# /npc — NPC 关系与动态
# ====================================================================

def handle_npc_command(raw_args: str) -> str:
    """处理 /npc 命令"""
    if not raw_args or raw_args.strip() in ("help", "-h"):
        return _NPC_HELP

    args = shlex.split(raw_args.strip())
    sub = args[0]

    try:
        if sub in ("list", "ls", "列表"):
            npcs = _npc().list_npcs()
            if not npcs:
                return "（还没有 NPC 记录）"
            lines = [f"NPC 列表（共 {len(npcs)} 个）:", ""]
            for n in npcs:
                status = "💀" if not n["alive"] else n["attitude_icon"]
                lines.append(f"  {status} {n['name']} @ {n.get('location', '?')} — {n['attitude_level']} ({n['attitude']:+d})")
            return "\n".join(lines)

        elif sub in ("show", "view", "详情"):
            if len(args) < 2:
                return "用法: /npc show <名字>"
            n = _npc().get_npc(args[1])
            if not n:
                return f"❌ NPC 不存在: {args[1]}"
            lines = [
                f"👤 {n['name']}",
                "=" * 30,
                f"位置: {n.get('location', '未知')}",
                f"状态: {'存活' if n.get('alive', True) else '死亡'}",
                f"态度: {n['attitude_icon']} {n['attitude_level']} ({n.get('attitude', 0):+d})",
                f"声望: {n.get('reputation', 0)}",
            ]
            if n.get("schedule"):
                lines.append("")
                lines.append("日程:")
                for slot, act in n["schedule"].items():
                    lines.append(f"  {slot}: {act}")
            if n.get("goals"):
                lines.append("")
                lines.append("目标:")
                for g in n["goals"]:
                    status = "✓" if g.get("status") == "completed" else "→"
                    lines.append(f"  {status} {g['text']}")
            if n.get("known_info"):
                lines.append("")
                lines.append("已知信息:")
                for info in n["known_info"][-5:]:
                    lines.append(f"  • {info}")
            if n.get("interactions"):
                lines.append("")
                lines.append("最近互动:")
                for inter in list(reversed(n["interactions"]))[:5]:
                    delta = f" ({inter['attitude_delta']:+d})" if inter.get("attitude_delta") else ""
                    lines.append(f"  • [{inter['type']}] {inter['summary']}{delta}")
            return "\n".join(lines)

        elif sub in ("attitude", "态度"):
            if len(args) < 3:
                if len(args) == 2:
                    # 查看态度
                    r = _npc().get_attitude(args[1])
                    if r.get("success"):
                        return f"{args[1]} 对玩家的态度: {r['icon']} {r['level']} ({r['attitude']:+d})"
                    return f"❌ {r.get('error')}"
                return "用法: /npc attitude <名字> +N/-N [原因]"
            name = args[1]
            delta = int(args[2].replace("+", ""))
            reason = args[3] if len(args) > 3 else ""
            r = _npc().change_attitude(name, delta, reason)
            if r.get("success"):
                level_notify = f"\n态度等级变化！" if r["level_changed"] else ""
                return (f"{r['icon']} {name} 态度变化: {r['old_attitude']:+d} → {r['new_attitude']:+d}\n"
                        f"当前等级: {r['level']}{level_notify}")
            return f"❌ {r.get('error', '操作失败')}"

        elif sub in ("move", "location", "位置", "移动"):
            if len(args) < 3:
                return "用法: /npc move <名字> <位置>"
            r = _npc().set_location(args[1], args[2])
            if r.get("success"):
                return f"🚶 {args[1]} 移动到: {args[2]}"
            return f"❌ {r.get('error', '操作失败')}"

        elif sub in ("log", "interaction", "互动"):
            if len(args) < 4:
                if len(args) == 2:
                    # 列出互动
                    inters = _npc().list_interactions(args[1], 10)
                    if not inters:
                        return "（没有互动记录）"
                    lines = [f"{args[1]} 的最近互动:", ""]
                    for i in inters:
                        delta = f" ({i['attitude_delta']:+d})" if i.get("attitude_delta") else ""
                        lines.append(f"  • [{i['type']}] {i['summary']}{delta}")
                    return "\n".join(lines)
                return "用法: /npc log <名字> <类型> <摘要> [态度变化]"
            name = args[1]
            itype = args[2]
            summary = " ".join(args[3:])
            delta = 0
            r = _npc().add_interaction(name, itype, summary, delta)
            if r.get("success"):
                return f"💬 已记录互动: {name} - {summary[:50]}"
            return f"❌ {r.get('error', '操作失败')}"

        elif sub in ("goal", "目标"):
            if len(args) < 3:
                return "用法: /npc goal add <名字> <目标描述>"
            op = args[1]
            if op == "add" and len(args) >= 4:
                name = args[2]
                goal = " ".join(args[3:])
                r = _npc().add_goal(name, goal)
                if r.get("success"):
                    return f"🎯 {name} 新增目标: {goal}"
            elif op == "complete" and len(args) >= 4:
                name = args[2]
                gid = args[3]
                r = _npc().complete_goal(name, gid)
                if r.get("success"):
                    return f"✅ {name} 完成目标: {gid}"
            return "用法: /npc goal add/complete ..."

        elif sub in ("know", "info", "已知"):
            if len(args) < 3:
                return "用法: /npc know <名字> <信息>"
            name = args[1]
            info = " ".join(args[2:])
            r = _npc().add_known_info(name, info)
            if r.get("success"):
                return f"💡 {name} 得知了: {info}"
            return f"❌ {r.get('error', '操作失败')}"

        elif sub in ("schedule", "日程"):
            if len(args) < 2:
                return "用法: /npc schedule <名字> [时段] [活动]"
            name = args[1]
            if len(args) == 2:
                sched = _npc().get_schedule(name)
                if not sched:
                    return f"{name} 没有日程设置。"
                lines = [f"{name} 的日程:", ""]
                for slot, act in sched.items():
                    lines.append(f"  {slot}: {act}")
                return "\n".join(lines)
            slot = args[2]
            activity = " ".join(args[3:]) if len(args) > 3 else ""
            r = _npc().set_schedule(name, slot, activity)
            if r.get("success"):
                return f"📅 {name} {slot}: {activity}"
            return f"❌ {r.get('error', '操作失败')}"

        elif sub in ("kill", "死亡", "die"):
            if len(args) < 2:
                return "用法: /npc kill <名字>"
            r = _npc().set_alive(args[1], False)
            if r.get("success"):
                return f"💀 {args[1]} 已死亡。"
            return f"❌ {r.get('error', '操作失败')}"

        else:
            return f"未知子命令: {sub}\n\n{_NPC_HELP}"

    except Exception as e:
        import traceback
        return f"❌ 命令执行失败: {e}\n{traceback.format_exc()}"


_NPC_HELP = """\
/npc — NPC 关系与动态

查看:
  list                           NPC 列表
  show <名字>                    NPC 详情
  log <名字>                     互动历史

态度:
  attitude <名字>                查看态度
  attitude <名字> +N/-N [原因]   改变态度

位置与状态:
  move <名字> <位置>             移动 NPC
  kill <名字>                    标记死亡

互动与信息:
  log <名字> <类型> <摘要>       记录互动
  know <名字> <信息>             NPC 获知信息

目标与日程:
  goal add <名字> <目标>         添加目标
  goal complete <名字> <目标ID>   完成目标
  schedule <名字> <时段> <活动>   设置日程

其他:
  help                           帮助
"""


# ====================================================================
# /time — 世界时钟
# ====================================================================

def handle_time_command(raw_args: str) -> str:
    """处理 /time 命令"""
    if not raw_args or raw_args.strip() in ("help", "-h", "now"):
        return _clk().format_time()

    args = shlex.split(raw_args.strip())
    sub = args[0]

    try:
        if sub in ("advance", "add", "+", "推进"):
            if len(args) < 2:
                return "用法: /time advance <数量><单位>\n  单位: m/分钟, h/小时, d/天\n  例: /time advance 2h"
            amount_str = args[1]
            # 解析单位
            if amount_str.endswith("m") or amount_str.endswith("分钟"):
                minutes = int(amount_str.rstrip("m分钟"))
                reason = args[2] if len(args) > 2 else ""
                r = _clk().advance_minutes(minutes, reason)
            elif amount_str.endswith("h") or amount_str.endswith("小时"):
                hours = int(amount_str.rstrip("h小时"))
                reason = args[2] if len(args) > 2 else ""
                r = _clk().advance_hours(hours, reason)
            elif amount_str.endswith("d") or amount_str.endswith("天"):
                days = int(amount_str.rstrip("d天"))
                reason = args[2] if len(args) > 2 else ""
                r = _clk().advance_days(days, reason)
            else:
                try:
                    minutes = int(amount_str)
                    r = _clk().advance_minutes(minutes)
                except ValueError:
                    return f"无法解析时间: {amount_str}\n用法: /time advance 2h / 30m / 1d"

            lines = [
                f"⏰ 时间推进",
                f"  {r['old_time']} → {r['new_time']}",
            ]
            if r.get("day_changed"):
                lines.append("  🗓 新的一天！")
            if r.get("slot_changed"):
                info = _clk().now()
                lines.append(f"  🌓 时段变化: {info['time_slot']}")
            if r.get("events_triggered"):
                lines.append("")
                lines.append("🔔 事件触发:")
                for ev in r["events_triggered"]:
                    lines.append(f"  • {ev['description']}")
            return "\n".join(lines)

        elif sub in ("set", "设置"):
            if len(args) < 2:
                return "用法: /time set <日期> <时间>\n  例: /time set 03-15 14:30"
            # 简化解析
            if len(args) >= 3:
                date_str = args[1]
                time_str = args[2]
            else:
                date_str = ""
                time_str = args[1]

            year = month = day = hour = minute = None
            if "-" in date_str:
                parts = date_str.split("-")
                if len(parts) == 2:
                    month, day = int(parts[0]), int(parts[1])
                elif len(parts) == 3:
                    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            if ":" in time_str:
                h, m = time_str.split(":")
                hour, minute = int(h), int(m)

            r = _clk().set_time(year=year, month=month, day=day, hour=hour, minute=minute)
            if r.get("success"):
                return f"🕐 时间已设置: {r['time']}"
            return f"❌ 设置失败"

        elif sub in ("weather", "天气"):
            if len(args) < 2:
                info = _clk().now()
                return f"当前天气: {info['weather']}"
            weather = " ".join(args[1:])
            r = _clk().set_weather(weather)
            if r.get("success"):
                return f"🌤 天气变化: {r['old_weather']} → {r['weather']}"
            return f"❌ 设置失败"

        elif sub in ("events", "事件"):
            op = args[1] if len(args) > 1 else "list"
            if op == "list":
                events = _clk().list_events()
                if not events:
                    return "（没有待触发的事件）"
                lines = ["📋 待触发事件:", ""]
                for ev in events:
                    lines.append(f"  • {ev['year']}-{ev['month']:02d}-{ev['day']:02d} {ev['hour']:02d}:{ev['minute']:02d}  {ev['description']}")
                return "\n".join(lines)
            elif op == "add" and len(args) >= 4:
                ev_time = args[2]
                desc = " ".join(args[3:])
                r = _clk().add_event(ev_time, desc)
                if r.get("success"):
                    return f"📅 事件已添加: {r['time']} — {desc}"
                return f"❌ {r.get('error', '添加失败')}"
            elif op == "check":
                r = _clk().check_events()
                if not r:
                    return "（没有新触发的事件）"
                lines = ["🔔 事件触发:"]
                for ev in r:
                    lines.append(f"  • {ev['description']}")
                return "\n".join(lines)
            return "用法: /time events list/add/check"

        elif sub in ("rest", "休息"):
            rest_type = args[1] if len(args) > 1 else "short"
            if rest_type in ("long", "长"):
                r = _clk().advance_hours(8, "长休")
                return f"😴 长休 8 小时\n{r['new_time']}"
            else:
                r = _clk().advance_hours(1, "短休")
                return f"😌 短休 1 小时\n{r['new_time']}"

        else:
            return f"未知子命令: {sub}\n\n{_TIME_HELP}"

    except Exception as e:
        import traceback
        return f"❌ 命令执行失败: {e}\n{traceback.format_exc()}"


_TIME_HELP = """\
/time — 世界时钟

查看:
  (无参数) / now               当前时间
  weather                      当前天气

时间推进:
  advance <数量><单位> [原因]   推进时间
    单位: m/分钟, h/小时, d/天
    例: /time advance 2h 探索地下室
  rest [short/long]            短休(1h) / 长休(8h)

设置:
  set <日期> <时间>            设置时间
  weather <天气>               设置天气

事件:
  events list                  待触发事件列表
  events add <时间> <描述>     添加定时事件
  events check                 检查并触发到期事件

其他:
  help                         帮助
"""
