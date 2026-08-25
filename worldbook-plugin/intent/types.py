"""Intent Detector 类型定义

设计文档：docs/intent-detector-design.md
- ActionCategory: 9 类规则事件
- ActionRule: 规则声明（系统无关）
- RuleEvent: 检测结果
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Optional


class ActionCategory(Enum):
    EXPLORATION = "exploration"
    SOCIAL = "social"
    COMBAT = "combat"
    SPELL = "spell"
    TRAVEL = "travel"
    REST = "rest"
    INVENTORY = "inventory"
    LOOT = "loot"
    DOWNTIME = "downtime"


@dataclass
class ActionRule:
    """规则声明：把玩家意图正则映射为规则事件

    Args:
        name: 规则名（"Perception" / "Attack" / "Loot"）
        pattern: 编译正则（多组交替）
        category: 规则分类
        strength: 1=强触发(必须检定) 2=弱触发(判断失败可能)
        order: 规则执行顺序（skill 10 < initiative 20 < attack 30 ...）
        inject: 注入文本模板
        event_type: 事件类型（"skill_check"/"attack"/"initiative"/"spell"/"rest"/"loot"）
        tool: 应调用的工具（如 "trpg_combat_start"）
        ability: 属性键（技能事件用，如 "dex"）
        skill: 技能名（技能事件用，如 "Stealth"）
        system: 限定系统（None=通用）
        cooldown: 冷却轮数（预留，未用）
        exclusive: 命中后跳过同 category 其他规则（预留，未用）
    """

    name: str
    pattern: re.Pattern
    category: ActionCategory
    strength: int
    order: int
    inject: str
    event_type: str = "skill_check"
    tool: Optional[str] = None
    ability: Optional[str] = None
    skill: Optional[str] = None
    system: Optional[str] = None
    cooldown: Optional[int] = None
    exclusive: bool = False

    def matches(self, text: str) -> bool:
        return bool(self.pattern.search(text))


@dataclass
class RuleEvent:
    """一次检测命中的规则事件"""

    type: str                      # "skill_check" / "attack" / ...
    rule: str                      # 来源规则名
    category: ActionCategory
    ability: Optional[str] = None  # "dex"
    skill: Optional[str] = None    # "Stealth"
    tool: Optional[str] = None     # "trpg_check"
    text: str = ""                 # 最终注入文本


__all__ = ["ActionCategory", "ActionRule", "RuleEvent"]
