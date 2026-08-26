"""兼容导入 bestiary_import 的 helper

Hermes 加载插件时 __package__ 可能为空，导致 from .bestiary_import 失败。
此模块用 importlib 从文件系统直接加载 bestiary_import.py。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_bestiary_import():
    """从当前目录加载 bestiary_import.py（不依赖 package name）"""
    here = Path(__file__).resolve().parent
    path = here / "bestiary_import.py"
    if not path.exists():
        raise ImportError(f"bestiary_import.py 不存在: {path}")

    name = "bestiary_import_compat__bestiary_import"
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# 对外暴露主要函数
try:
    _mod = _load_bestiary_import()
    convert_creature_to_bestiary = _mod.convert_creature_to_bestiary
except Exception:
    # 最后兜底：如果文件系统也加载失败，尝试把插件目录加入 sys.path
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    from bestiary_import import convert_creature_to_bestiary  # noqa: F401
