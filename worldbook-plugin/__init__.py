"""世界书自动注入插件

功能：
- pre_llm_call 钩子：自动检索相关世界书条目并注入上下文
- 斜杠命令：/worldbook <status|list|search|add|edit|delete|import|export>
- 支持多世界书、分类过滤、相似度阈值

插件目录：~/.hermes/plugins/worldbook/
"""

import logging
import shlex
from typing import Any

from .config import load_config
from .store import WorldBookStore
from .retriever import WorldBookRetriever
from .injector import ContextInjector
from .manager import WorldBookManager
from .state import StateManager
from .state_cmd import handle_state_command
from .narrative import ChronicleManager, QuestManager, NPCManager, WorldClock
from .narrative_cmd import (
    handle_chronicle_command,
    handle_quest_command,
    handle_npc_command,
    handle_time_command,
)

logger = logging.getLogger(__name__)

# 全局单例
_store = None
_retriever = None
_injector = None
_manager = None
_state_mgr = None
_combat_guard = None


def _get_store() -> WorldBookStore:
    global _store
    if _store is None:
        _store = WorldBookStore()
    return _store


def _get_retriever(config: dict) -> WorldBookRetriever:
    global _retriever
    if _retriever is None:
        store = _get_store()
        _retriever = WorldBookRetriever(store, config)
    return _retriever


def _get_state_mgr() -> StateManager:
    from .state import get_default_state_mgr
    return get_default_state_mgr()


def _get_combat_guard():
    """战斗数值校验器的持久单例（pre 与 transform 钩子共享，跨钩子记录轮次边界）"""
    global _combat_guard
    if _combat_guard is None:
        from .combat_guard import CombatValueGuard
        _combat_guard = CombatValueGuard(_get_state_mgr())
    return _combat_guard


def _get_injector(config: dict) -> ContextInjector:
    global _injector
    if _injector is None:
        retriever = _get_retriever(config)
        state_mgr = _get_state_mgr()
        _injector = ContextInjector(retriever, state_mgr, config)
    return _injector


def _get_manager(config: dict) -> WorldBookManager:
    global _manager
    if _manager is None:
        store = _get_store()
        _manager = WorldBookManager(store, config)
    return _manager


def _on_pre_llm_call(**kwargs):
    """pre_llm_call 钩子回调"""
    # 先记录战斗校验的轮次边界（独立于注入开关，combat_guard 需跨钩子共享）
    try:
        _get_combat_guard().mark_turn_start(kwargs.get("turn_id"))
    except Exception as e:
        logger.debug(f"[worldbook] combat_guard mark_turn_start 异常: {e}")

    try:
        config = load_config()
        # 如果关闭了自动注入，直接返回
        if not config.get("enabled", True) or not config.get("auto_inject", True):
            return None
        injector = _get_injector(config)
        result = injector.on_pre_llm_call(**kwargs) or {}

        # v2.9：规则书按需注入（仅在 auto_inject 开启时）
        try:
            from .app_context import get_app
            from .adapter.rules_injector import RulesInjector
            app = get_app()
            user_msg = kwargs.get("user_message", "") or ""
            # 从 player state 推断 system
            system = kwargs.get("system") or "dnd5e"
            rules_inj = RulesInjector(app.rules)
            rules_block = rules_inj.inject_for_context(user_msg, system=system)
            if rules_block:
                existing = result.get("system_addition", "")
                result["system_addition"] = existing + "\n\n" + rules_block
        except Exception as e:
            logger.debug(f"[worldbook] 规则注入异常: {e}")

        return result if result else None
    except Exception as e:
        logger.debug(f"[worldbook] pre_llm_call 钩子异常: {e}")
        return None


def _on_transform_llm_output(**kwargs):
    """transform_llm_output 钩子回调

    战斗数值校验：战斗中检测 AI 回复里的伤害/HP 数字，如果没有对应工具调用，
    在回复末尾加醒目警告。
    """
    try:
        config = load_config()
        if not config.get("enabled", True):
            return None
        if not config.get("combat_guard", True):
            return None

        response_text = kwargs.get("response_text", "")
        if not response_text:
            return None

        guard = _get_combat_guard()
        # 用 event_log 的 version 增量精确判断本轮是否走了战斗工具
        # （transform 钩子拿不到 conversation_history，不再依赖空历史）
        check_result = guard.check_response(response_text)

        if check_result.get("warnings"):
            footer = guard.format_warning_footer(check_result)
            return response_text + footer

        return None  # 不修改
    except Exception as e:
        logger.debug(f"[worldbook] transform_llm_output 钩子异常: {e}")
        return None


def _handle_worldbook_command(raw_args: str):
    """处理 /worldbook 斜杠命令"""
    config = load_config()
    manager = _get_manager(config)

    if not raw_args or raw_args.strip() in ("help", "-h", "--help"):
        return _HELP_TEXT

    args = shlex.split(raw_args.strip())
    sub = args[0]

    try:
        if sub == "status":
            return manager.status()

        elif sub == "list":
            worldbook = args[1] if len(args) > 1 else None
            category = args[2] if len(args) > 2 else None
            return manager.list_entries(worldbook=worldbook, category=category)

        elif sub == "books":
            return manager.list_books()

        elif sub == "search":
            if len(args) < 2:
                return "用法: /worldbook search <关键词>"
            query = " ".join(args[1:])
            return manager.search_entries(query)

        elif sub == "add":
            # /worldbook add <title> | <content> [--keys k1,k2] [--category 地点] [--book 灰港]
            # 简化：title 是第一个参数，content 用引号包围
            if len(args) < 2:
                return "用法: /worldbook add <title> <content> [--category 分类] [--keys k1,k2]"
            title = args[1]
            content = args[2] if len(args) > 2 else ""
            category = "其他"
            keys = [title]
            for i, arg in enumerate(args):
                if arg == "--category" and i + 1 < len(args):
                    category = args[i + 1]
                elif arg == "--keys" and i + 1 < len(args):
                    keys = args[i + 1].split(",")
            return manager.add_entry(title=title, content=content, keys=keys, category=category)

        elif sub == "edit":
            if len(args) < 3:
                return "用法: /worldbook edit <entry_id> <field> <value>"
            entry_id = args[1]
            field = args[2]
            value = " ".join(args[3:]) if len(args) > 3 else ""
            return manager.edit_entry(entry_id, **{field: value})

        elif sub == "delete":
            if len(args) < 2:
                return "用法: /worldbook delete <entry_id>"
            return manager.delete_entry(args[1])

        elif sub == "enable":
            if len(args) < 2:
                return "用法: /worldbook enable <世界书名> [true|false]"
            name = args[1]
            enabled = args[2].lower() != "false" if len(args) > 2 else True
            return manager.enable_book(name, enabled)

        elif sub == "import":
            if len(args) < 2:
                return "用法: /worldbook import <json文件路径> [世界书名]"
            path = args[1]
            name = args[2] if len(args) > 2 else None
            return manager.import_book(path, name)

        elif sub == "export":
            if len(args) < 3:
                return "用法: /worldbook export <世界书名> <输出路径>"
            name = args[1]
            out = args[2]
            return manager.export_book(name, out)

        else:
            return f"未知子命令: {sub}\n\n{_HELP_TEXT}"

    except Exception as e:
        return f"命令执行失败: {e}"


_HELP_TEXT = """\
/worldbook — 世界书管理

子命令:
  status                     查看世界书系统状态
  list [世界书] [分类]       列出条目
  books                      列出所有世界书
  search <关键词>            搜索条目（本地关键词）
  add <title> <content>      添加条目
    --category 分类            地点/NPC/怪物/物品/组织/规则/剧情/其他
    --keys k1,k2              关键词列表，逗号分隔
  edit <id> <field> <value>  编辑条目字段
  delete <id>                删除条目
  enable <书名> [true|false] 启用/禁用世界书
  import <path> [书名]       从 JSON 导入世界书
  export <书名> <path>       导出世界书到 JSON
  help                       显示帮助

示例:
  /worldbook status
  /worldbook search 灰港
  /worldbook add "新地点" "这是一个新地点..." --category 地点 --keys 地点1,place1
"""


def register(ctx: Any) -> None:
    """插件注册入口"""
    # 注册 pre_llm_call 钩子（核心功能）
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)

    # 注册斜杠命令
    ctx.register_command(
        "worldbook",
        handler=_handle_worldbook_command,
        description="世界书管理：自动注入、条目增删改查、多世界书支持",
    )

    ctx.register_command(
        "state",
        handler=handle_state_command,
        description="跑团状态管理：角色属性、生命值、背包、金币、任务、事件日志",
    )

    ctx.register_command(
        "chronicle",
        handler=handle_chronicle_command,
        description="剧情编年史：章节管理、大事记录、前情提要",
    )

    ctx.register_command(
        "quest",
        handler=handle_quest_command,
        description="任务系统：多步骤任务、触发条件、任务依赖",
    )

    ctx.register_command(
        "npc",
        handler=handle_npc_command,
        description="NPC 关系与动态：态度值、互动历史、日程、目标",
    )

    ctx.register_command(
        "time",
        handler=handle_time_command,
        description="世界时钟：游戏时间推进、天气、定时事件",
    )

    # 注册 MCP 工具（让 AI 可以直接调用）
    try:
        from .app_context import get_app
        from .tools import register_all_tools

        app = get_app()
        n = register_all_tools(ctx, app)
        logger.info(f"[worldbook] 注册了 {n} 个 TRPG MCP 工具")
    except Exception as e:
        import traceback
        logger.warning(f"[worldbook] MCP 工具注册失败: {e}\n{traceback.format_exc()}")

    logger.info("[worldbook] 插件注册成功：pre_llm_call 钩子 + 6 个命令 + MCP 工具")
