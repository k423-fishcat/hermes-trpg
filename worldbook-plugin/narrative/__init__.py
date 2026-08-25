"""叙事层模块包

包含：
- chronicle: 剧情编年史
- quests: 任务推进系统
- npcs: NPC 关系与动态
- clock: 世界时钟
- sessions: 场次管理

P1 #9 优化：改为 __getattr__ 懒加载，避免 import narrative 任意子模块
时加载全部 5 个 manager（~1700 行）。只有真正访问某 manager 才加载对应文件。

用法不变：
    from .narrative import ChronicleManager  # 仍工作（触发 __getattr__）
"""

__all__ = [
    "ChronicleManager", "QuestManager", "NPCManager", "WorldClock", "SessionManager",
]

# 模块 → 需要加载的类名
_LAZY_EXPORTS = {
    "ChronicleManager": ("chronicle", "ChronicleManager"),
    "QuestManager": ("quests", "QuestManager"),
    "NPCManager": ("npcs", "NPCManager"),
    "WorldClock": ("clock", "WorldClock"),
    "SessionManager": ("sessions", "SessionManager"),
}


def __getattr__(name):
    """懒加载：首次访问某 manager 时才 import 对应子模块"""
    mapping = _LAZY_EXPORTS.get(name)
    if mapping is not None:
        submodule, attr = mapping
        import importlib
        mod = importlib.import_module(f"{__name__}.{submodule}")
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
