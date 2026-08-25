"""统一依赖容器（AppContext）

替代散落在 __init__.py / state_cmd.py / narrative_cmd.py 里的模块级 singleton。
v2.5 加了 state.get_default_state_mgr() 解决核心问题，但还有 4 个 manager
（chronicle/quests/npcs/clock）和 bestiary/combat/inventory 等业务 manager 各自单例。
AppContext 是统一所有 service 的下一步。

用法：
    from .app_context import get_app
    app = get_app()
    app.state.update({...})
    app.chronicle.add_event(...)

迁移路线：
- P1.1：建 app_context.py + narrative_cmd.py 第一个迁移
- 后续：state_cmd.py → __init__.py → tools.py → 其他
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .state import StateManager
    from .narrative import ChronicleManager, QuestManager, NPCManager, WorldClock
    from .narrative.sessions import SessionManager
    from .bestiary import Bestiary
    from .combat import CombatTracker
    from .inventory import InventoryManager
    from .spells import SpellManager
    from .characters import CharacterManager
    from .rest import RestManager
    from .encounters import EncounterManager
    from .modules import ModuleManager
    from .store import WorldBookStore
    from .combat_guard import CombatValueGuard
    from .rules import RulesBook

logger = logging.getLogger(__name__)

_app: Optional["AppContext"] = None


class AppContext:
    """统一的应用上下文（依赖容器）

    所有 service 在这里集中构造和缓存。任何 hook / 命令 / 工具
    都通过 get_app() 获取同一实例，杜绝之前散落 singleton 导致的
    缓存不一致问题。
    """

    def __init__(self) -> None:
        # === 核心 ===
        self.state: "StateManager" = None  # type: ignore
        self.worldbook_store: "WorldBookStore" = None  # type: ignore
        self.combat_guard: "CombatValueGuard" = None  # type: ignore

        # === 规则书快照 ===
        self.rules: "RulesBook" = None  # type: ignore

        # === 叙事层 ===
        self.chronicle: "ChronicleManager" = None  # type: ignore
        self.quests: "QuestManager" = None  # type: ignore
        self.npcs: "NPCManager" = None  # type: ignore
        self.clock: "WorldClock" = None  # type: ignore
        self.sessions: "SessionManager" = None  # type: ignore

        # === 业务能力 ===
        self.bestiary: "Bestiary" = None  # type: ignore
        self.combat: "CombatTracker" = None  # type: ignore
        self.inventory: "InventoryManager" = None  # type: ignore
        self.spells: "SpellManager" = None  # type: ignore
        self.characters: "CharacterManager" = None  # type: ignore
        self.rest: "RestManager" = None  # type: ignore
        self.encounters: "EncounterManager" = None  # type: ignore
        self.modules: "ModuleManager" = None  # type: ignore

        # === 插件 ctx（由 register() 注入）===
        self.plugin_ctx: Any = None

    def build(self) -> "AppContext":
        """构造并连接所有 service。get_app() 首次调用会触发。"""
        from .config import get_plugin_data_dir
        from .state import get_default_state_mgr
        from .store import WorldBookStore
        from .narrative import ChronicleManager, QuestManager, NPCManager, WorldClock
        from .narrative.sessions import SessionManager
        from .bestiary import Bestiary
        from .combat import CombatTracker
        from .inventory import InventoryManager
        from .spells import SpellManager
        from .characters import CharacterManager
        from .rest import RestManager
        from .encounters import EncounterManager
        from .modules import ModuleManager
        from .combat_guard import CombatValueGuard
        from .rules import RulesBook

        data_dir = get_plugin_data_dir()
        rules_dir = Path(__file__).parent / "rules" / "builtin"

        # === 核心 ===
        self.state = get_default_state_mgr()
        self.worldbook_store = WorldBookStore()

        # === 规则书快照（独立挂载，不依赖 data_dir）===
        self.rules = RulesBook(rules_dir)
        try:
            self.rules.load("dnd5e")
            logger.info("[app_context] 规则书快照 dnd5e 已加载: %s", self.rules.stats())
        except Exception as e:
            logger.warning(f"[app_context] 规则书快照加载失败: {e}")

        # === 叙事层 ===
        self.chronicle = ChronicleManager(self.state)
        self.quests = QuestManager(self.state)
        self.npcs = NPCManager(self.state)
        self.clock = WorldClock(self.state)
        self.sessions = SessionManager(self.state)

        # === 业务能力 ===
        self.bestiary = Bestiary(data_dir)
        self.combat = CombatTracker(self.state, self.bestiary)
        self.inventory = InventoryManager(self.state)
        self.spells = SpellManager(self.state)
        self.characters = CharacterManager(data_dir)
        self.rest = RestManager(self.state, clock=self.clock)
        self.encounters = EncounterManager(
            self.state, combat_tracker=self.combat, bestiary=self.bestiary
        )
        self.modules = ModuleManager(
            self.state, data_dir / "adventures", worldbook_store=self.worldbook_store
        )

        # === 战斗硬约束 ===
        self.combat_guard = CombatValueGuard(self.state)

        logger.info("[app_context] built 15 services (含 rules)")
        return self

    def reset(self) -> None:
        """清空所有 service（仅供测试 / data_dir 变化时用）"""
        for attr in list(self.__dict__.keys()):
            if attr != "plugin_ctx":
                setattr(self, attr, None)


def get_app() -> "AppContext":
    """获取（或懒加载）全局 AppContext 单例"""
    global _app
    if _app is None:
        _app = AppContext()
        _app.build()
    return _app


def reset_app() -> None:
    """重置全局单例（仅供测试）"""
    global _app
    if _app is not None:
        _app.reset()
    _app = None


def set_app(app: "AppContext") -> None:
    """手动注入 app（仅供测试 mock 用）"""
    global _app
    _app = app


__all__ = ["AppContext", "get_app", "reset_app", "set_app"]
