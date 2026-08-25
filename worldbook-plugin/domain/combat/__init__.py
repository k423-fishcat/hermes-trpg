"""domain.combat - 战斗系统内部模块

按职责拆分后的辅助逻辑：
- damage: 伤害计算（抗/免/易伤、暴击、临时HP）
- conditions: 状态效果增删
- combat: 战斗流程（占位，由顶层 combat.py 持有）

主类 CombatTracker 仍在 worldbook_plugin.combat，向后兼容。
"""

from .damage import (
    apply_damage_modifiers,
    build_rule_reference,
    DmgCalcResult,
)
from .conditions import (
    add_condition_to_creature,
    remove_condition_from_creature,
    has_condition,
    list_conditions,
)

__all__ = [
    "apply_damage_modifiers",
    "build_rule_reference",
    "DmgCalcResult",
    "add_condition_to_creature",
    "remove_condition_from_creature",
    "has_condition",
    "list_conditions",
]
