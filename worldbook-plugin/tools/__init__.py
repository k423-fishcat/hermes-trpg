"""tools/ 包 — 替代 v2.5 之前的 tools.py（3514 行单文件）

15 个子模块 + ToolRegistry 装饰器模式。每个子文件 100-400 行，
加新工具只需 @reg.tool() 一行装饰器 + handler 函数。

子模块：
- registry.py        ToolRegistry + @tool 装饰器
- state_tools.py     2 个：state get / state update
- narrative.py       21 个：chronicle / quest / npc / time
- bestiary.py        5 个：怪物图鉴
- combat.py          9 个：战斗追踪
- characters.py      5 个：角色卡 + XP/升级
- inventory.py       8 个：背包 / 装备 / 金币
- spells.py          7 个：法术 + 专注
- sessions.py        6 个：场次 + 选择
- check.py           1 个：D&D 5e 检定
- snapshots.py       3 个：快照与回滚
- rest.py            3 个：休息
- modules.py         4 个：模组管理
- encounters.py      4 个：遭遇管理
- worldbook.py       1 个：世界书搜索
- rules.py           3 个：规则书查询

外部调用（__init__.py）：
    from tools import register_all_tools
    register_all_tools(ctx, app)
"""

from .registry import ToolRegistry


def register_all_tools(ctx, app) -> int:
    """注册所有 82 个 TRPG 工具到 ctx。

    Args:
        ctx: PluginContext（提供 ctx.register_tool）
        app: AppContext（提供所有 service 实例）

    Returns:
        注册的工具数量
    """
    reg = ToolRegistry(ctx)

    # 状态（state get/update）
    from . import state_tools
    state_tools.register(reg, app.state)

    # 叙事层（chron / quest / npc / time）
    from . import narrative
    narrative.register(reg, app.chronicle, app.quests, app.npcs, app.clock)

    # 业务能力
    from . import bestiary
    bestiary.register(reg, app.bestiary)

    from . import combat
    combat.register(reg, app.combat)

    from . import characters
    characters.register(reg, app.characters, app.state)

    from . import inventory
    inventory.register(reg, app.inventory)

    from . import spells
    spells.register(reg, app.spells)

    from . import sessions
    sessions.register(reg, app.sessions)

    from . import check
    check.register(reg, app.state, app.chronicle)

    from . import snapshots
    snapshots.register(reg, app.state)

    from . import rest
    rest.register(reg, app.rest)

    from . import modules
    modules.register(reg, app.modules)

    from . import encounters
    encounters.register(reg, app.encounters)

    from . import worldbook
    worldbook.register(reg, app.worldbook_store)

    from . import rules
    rules.register(reg, app.rules)

    # 一次性推给 ctx
    n = reg.register_all()
    return n


__all__ = ["register_all_tools", "ToolRegistry"]
