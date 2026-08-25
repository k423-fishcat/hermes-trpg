"""zh_mapping - 中英文名映射查表

用法：
    from .zh_mapping import get_zh
    zh_name = get_zh("spells", "fireball")  # → "火球术"
    zh_name = get_zh("creatures", "orc")     # → "兽人"

数据来源：rules/zh_mapping.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# zh_mapping.json 在 rules/ 目录下（和本文件同目录）
DEFAULT_MAPPING_PATH = Path(__file__).parent / "zh_mapping.json"

# 缓存：{category: {slug: name_zh}}
_cache: dict[str, dict[str, str]] | None = None
_loaded: bool = False


def _load_mapping(path: Path | None = None) -> dict[str, dict[str, str]]:
    """加载 zh_mapping.json"""
    global _cache, _loaded
    if _loaded and _cache is not None:
        return _cache

    mapping_path = path or DEFAULT_MAPPING_PATH
    if not mapping_path.exists():
        logger.warning(f"[zh_mapping] 文件不存在: {mapping_path}")
        _cache = {}
        _loaded = True
        return _cache

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"[zh_mapping] 加载失败: {e}")
        _cache = {}
        _loaded = True
        return _cache

    # 过滤掉 _meta 等元数据 key + ---- section ---- 分隔标记
    _cache = {
        k: {sk: sv for sk, sv in v.items() if not (isinstance(sv, str) and sv in ("section", "_section"))}
        for k, v in data.items()
        if not k.startswith("_") and isinstance(v, dict)
    }
    _loaded = True
    logger.debug(f"[zh_mapping] 加载 {sum(len(v) for v in _cache.values())} 条映射")
    return _cache


def get_zh(category: str, slug: str, default: str | None = None) -> str | None:
    """查 category.slug 的中文名。

    Args:
        category: spells/classes/conditions/creatures/items
        slug: 来自 rule_id 末段
        default: 没找到时返回什么（None = 返回 None）

    Returns:
        中文名 或 None/default
    """
    mapping = _load_mapping()
    cat_data = mapping.get(category, {})
    # 1. 原样查
    if slug in cat_data:
        return cat_data[slug]
    # 2. spells 用连字符的 slug（2014 SRD 风格）也兼容
    if category == "spells" and "-" in slug:
        underscore = slug.replace("-", "_")
        if underscore in cat_data:
            return cat_data[underscore]
    return default


def translate(rule: dict, default: str | None = None) -> dict:
    """根据 rule['rule_id'] 自动补 name_zh（如果还没有中文名）。

    Args:
        rule: 单条规则 dict（必须含 rule_id）
        default: 没找到时 name_zh 用什么（None = 保持原 name_en）

    Returns:
        原 dict（就地修改）
    """
    rid = rule.get("rule_id", "")
    # 从 rule_id 抽 category 和 slug
    # rules.dnd5e.spells.fireball → ("spells", "fireball")
    parts = rid.split(".")
    if len(parts) < 4:
        return rule
    category = parts[2]
    slug = parts[3]

    # 已有非英文名就跳过
    current_zh = rule.get("name_zh", "")
    if current_zh and not _is_english(current_zh):
        return rule

    zh = get_zh(category, slug)
    if zh:
        rule["name_zh"] = zh
    elif default is not None:
        rule["name_zh"] = default
    return rule


def _is_english(text: str) -> bool:
    """简单判断：是否纯英文（ASCII 字母）"""
    if not text:
        return True
    return all(ord(c) < 128 for c in text if c.isalpha())


def stats() -> dict:
    """返回映射统计：{category: count}"""
    mapping = _load_mapping()
    return {cat: len(slugs) for cat, slugs in mapping.items()}


def reload(path: Path | None = None) -> None:
    """重置缓存（测试用）"""
    global _cache, _loaded
    _cache = None
    _loaded = False
    if path:
        _load_mapping(path)
