"""模组导入框架

支持多格式的模组导入，统一转换为中间模型后导入到系统。

用法:
    from .adventure.loader import load_module, import_module, detect_format

    # 自动检测格式并加载
    mod = load_module("path/to/module")

    # 导入到系统
    stats = import_module(mod, worldbook_store=wb, state_mgr=sm, ...)

支持的格式:
  - native: adventure.json（我们自己的格式）
  - zim_wiki: Zim Desktop Wiki 目录
"""

from .models import (
    AdventureModule,
    AdventureEntry,
    AdventureNPC,
    AdventureQuest,
    AdventureEncounter,
)
from .loader import (
    load_module,
    import_module,
    detect_format,
    list_adventures,
    export_module_json,
)
from .manager import ModuleManager

__all__ = [
    "AdventureModule",
    "AdventureEntry",
    "AdventureNPC",
    "AdventureQuest",
    "AdventureEncounter",
    "load_module",
    "import_module",
    "detect_format",
    "list_adventures",
    "export_module_json",
    "ModuleManager",
]
