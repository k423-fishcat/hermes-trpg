"""模组统一数据模型（Intermediate Model）

所有格式的模组都先转换成这个中间模型，再统一导入到跑团系统。
这样新增格式时只需要写一个解析器，不用改导入逻辑。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AdventureEntry:
    """一条世界书/设定条目"""
    id: str
    title: str
    category: str = "other"        # location / npc / item / organization / quest / creature / dungeon / encounter / other
    content: str = ""               # 完整内容（Markdown/纯文本）
    summary: str = ""               # 一句话摘要
    keywords: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外属性（位置/CR/阵营等）
    source_format: str = ""         # 来源格式


@dataclass
class AdventureQuest:
    """一个任务"""
    id: str
    title: str
    description: str = ""
    quest_type: str = "side"        # main / side / hidden / personal
    giver: str = ""
    rewards: str = ""
    steps: List[Dict[str, str]] = field(default_factory=list)  # [{id, title, description}]
    prerequisites: List[str] = field(default_factory=list)


@dataclass
class AdventureNPC:
    """一个 NPC"""
    id: str
    name: str
    description: str = ""
    personality: str = ""
    initial_attitude: int = 0       # -20 到 +20
    location: str = ""
    known_info: List[str] = field(default_factory=list)
    schedule: Dict[str, str] = field(default_factory=dict)


@dataclass
class AdventureEncounter:
    """一个预设遭遇"""
    id: str
    name: str
    encounter_type: str = "combat"  # combat / social / exploration / trap
    description: str = ""
    location: str = ""
    creatures: List[Dict] = field(default_factory=list)
    dc_info: Dict[str, int] = field(default_factory=dict)
    rewards: str = ""


@dataclass
class AdventureModule:
    """完整模组（中间模型）

    所有格式解析器都输出这个结构，然后由导入器统一写入系统。
    """
    id: str
    name: str
    system: str = "dnd5e"
    version: str = "0.1"
    author: str = ""
    description: str = ""

    # 分类内容
    entries: List[AdventureEntry] = field(default_factory=list)    # 世界书条目
    npcs: List[AdventureNPC] = field(default_factory=list)        # NPC
    quests: List[AdventureQuest] = field(default_factory=list)    # 任务
    encounters: List[AdventureEncounter] = field(default_factory=list)  # 遭遇
    world_flags: Dict[str, Any] = field(default_factory=dict)     # 初始世界标记

    # 开场
    opening_title: str = ""
    opening_summary: str = ""
    opening_hook: str = ""

    # 元数据
    source_format: str = ""
    source_path: str = ""
    entry_count: int = 0

    def stats(self) -> Dict[str, int]:
        """统计各类型数量"""
        by_cat = {}
        for e in self.entries:
            by_cat[e.category] = by_cat.get(e.category, 0) + 1
        return {
            "entries": len(self.entries),
            "entries_by_category": by_cat,
            "npcs": len(self.npcs),
            "quests": len(self.quests),
            "encounters": len(self.encounters),
            "world_flags": len(self.world_flags),
        }
