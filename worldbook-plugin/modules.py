"""兼容垫片：modules.py → adventure/manager.py

旧代码：`from .modules import ModuleManager`
新代码：`from .adventure import ModuleManager`
两者等价。
"""

from .adventure.manager import ModuleManager

__all__ = ["ModuleManager"]
