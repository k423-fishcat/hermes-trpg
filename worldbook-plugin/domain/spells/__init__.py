"""domain.spells - 法术系统内部模块

按职责拆分后的辅助逻辑：
- known_casters: 已知型施法者（术/诗/邪）
- prepared_casters: 准备型施法者（法/牧/德/圣/游）
- cast: 施法核心（被 SpellManager 调用）
- concentration: 专注法术处理

主类 SpellManager 仍在 worldbook_plugin.spells，向后兼容。
"""

from .known_casters import (
    KNOWN_CASTER_NAMES,
    is_known_caster,
    can_cast_from_known,
    get_known_casters_for,
)
from .prepared_casters import (
    PREPARED_CASTER_NAMES,
    is_prepared_caster,
    can_cast_from_prepared,
    max_prepared_count,
)
from .cast import check_can_cast, find_slot
from .concentration import (
    start_concentration,
    break_concentration,
    is_concentrating,
    get_concentration,
)

__all__ = [
    "KNOWN_CASTER_NAMES",
    "is_known_caster",
    "can_cast_from_known",
    "get_known_casters_for",
    "PREPARED_CASTER_NAMES",
    "is_prepared_caster",
    "can_cast_from_prepared",
    "max_prepared_count",
    "check_can_cast",
    "find_slot",
    "start_concentration",
    "break_concentration",
    "is_concentrating",
    "get_concentration",
]
