"""RulesBook - 运行时规则书快照加载与检索

所有数据来自 rules/builtin/{system}/{category}.json
运行时只读，断网也能用。
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Optional

from .schema import validate_category, SchemaError
from .rule_id import make_rule_id, parse_rule_id, RuleId

logger = logging.getLogger(__name__)

# 默认规则书目录（相对插件根）
DEFAULT_RULES_DIR = Path(__file__).parent / "builtin"


class RulesBook:
    """规则书快照

    用法：
        book = RulesBook()  # 用默认目录
        book.load("dnd5e")  # 加载 dnd5e 所有分类
        spell = book.get("dnd5e", "spells", "fireball")
        results = book.search("火球", system="dnd5e")
    """

    def __init__(self, rules_dir: Path | str | None = None):
        self.rules_dir = Path(rules_dir) if rules_dir else DEFAULT_RULES_DIR
        # 缓存：{system: {category: {name: data}}}
        self._cache: dict[str, dict[str, dict[str, dict]]] = {}
        self._lock = threading.RLock()

    # ----------------------------------------------------------------
    # 加载
    # ----------------------------------------------------------------

    def load(self, system: str = "dnd5e", categories: list[str] | None = None,
             edition: str = "2024", validate: bool = False) -> "RulesBook":
        """加载一个规则系统的所有（或指定）分类到内存。

        Args:
            system: 规则系统 ("dnd5e" / "dnd3r" / "coc7e" / "custom")
            categories: 要加载的分类列表（None = 全部）
            edition: SRD 版本 ("2024" / "2014" / "any")—— 决定读哪个子目录
            validate: 是否校验 schema

        Returns:
            self
        """
        # 优先尝试 rules/builtin/{system}/{edition}/；fallback 到 rules/builtin/{system}/
        edition_dir = self.rules_dir / system / edition
        flat_dir = self.rules_dir / system
        if edition_dir.is_dir():
            system_dir = edition_dir
        elif flat_dir.is_dir():
            system_dir = flat_dir
        else:
            logger.debug(f"[rules] 系统目录不存在: {system}")
            return self

        with self._lock:
            cache_key = f"{system}:{edition}"
            if cache_key not in self._cache:
                self._cache[cache_key] = {}

            for json_file in system_dir.glob("*.json"):
                category = json_file.stem
                if categories and category not in categories:
                    continue

                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (OSError, json.JSONDecodeError) as e:
                    logger.warning(f"[rules] 加载失败 {json_file}: {e}")
                    continue

                if validate:
                    errors = validate_category(category, data)
                    if errors:
                        logger.warning(
                            f"[rules] {system}/{edition}/{category} schema 校验失败:\n"
                            + "\n".join(f"  - {e}" for e in errors[:5])
                        )
                        # 不抛异常，仅警告

                items = self._extract_items(category, data)
                self._cache[cache_key][category] = items
                logger.debug(
                    f"[rules] 加载 {system}/{edition}/{category}: {len(items)} 条"
                )

        return self

    def _extract_items(self, category: str, data: dict) -> dict[str, dict]:
        """从分类数据中提取条目 {name: data}"""
        items_dict: dict[str, dict] = {}

        if category == "classes":
            # classes 是 dict[英文名, data]
            classes = data.get("classes", {})
            if isinstance(classes, dict):
                for k, v in classes.items():
                    if isinstance(v, dict):
                        # 用 rule_id 的 name 段（如果存在）或 fallback 到 k
                        rid = v.get("rule_id", "")
                        if rid and "classes." in rid:
                            name = rid.split("classes.")[-1]
                        else:
                            name = k
                        items_dict[name] = v
        elif category == "spell_slots":
            # spell_slots 整体作为一个条目存
            items_dict["_default"] = data
        elif category == "equipment":
            items_dict["_default"] = data
        else:
            # 默认：list[dict] 或 dict[英文名, dict]
            list_key = self._guess_list_key(category, data)
            if not list_key:
                return items_dict
            raw = data.get(list_key, [])
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        name = self._extract_name(category, item)
                        if name:
                            items_dict[name] = item
            elif isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, dict):
                        items_dict[k] = v

        return items_dict

    def _guess_list_key(self, category: str, data: dict) -> str | None:
        """从数据里猜条目列表的 key"""
        # 优先用 schema 定义的
        from .schema import CATEGORY_SCHEMAS
        if category in CATEGORY_SCHEMAS:
            lk, _ = CATEGORY_SCHEMAS[category]
            if lk and lk in data:
                return lk
        # 兜底
        for candidate in ("spells", "conditions", "rules", "items",
                          "creatures", "skills", "saves"):
            if candidate in data:
                return candidate
        return None

    def _extract_name(self, category: str, item: dict) -> str | None:
        """从条目里抽名字（用于 cache key）"""
        rid = item.get("rule_id")
        if rid:
            parsed = parse_rule_id(rid)
            if parsed:
                return parsed.name
        # fallback
        for k in ("name_en", "name_zh"):
            if item.get(k):
                return str(item[k]).lower().replace(" ", "_")
        return None

    # ----------------------------------------------------------------
    # 查询
    # ----------------------------------------------------------------

    def _resolve_cache(self, system: str, edition: str = "2024") -> dict:
        """拿某个 system:edition 下的分类 dict，找不到回退到 system 键。"""
        cache_key = f"{system}:{edition}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        if system in self._cache:
            return self._cache[system]
        return {}

    def get(self, system: str, category: str, name: str,
            edition: str = "2024") -> Optional[dict]:
        """取单条规则。返回 None 表示未找到。"""
        with self._lock:
            cat_data = self._resolve_cache(system, edition).get(category, {})
            return cat_data.get(name)

    def list(self, system: str, category: str, edition: str = "2024") -> list[dict]:
        """列出某分类下所有规则（值列表）"""
        with self._lock:
            cat_data = self._resolve_cache(system, edition).get(category, {})
            return list(cat_data.values())

    def list_names(self, system: str, category: str,
                   edition: str = "2024") -> list[str]:
        """列出某分类下所有规则的 name"""
        with self._lock:
            cat_data = self._resolve_cache(system, edition).get(category, {})
            return list(cat_data.keys())

    def list_categories(self, system: str, edition: str = "2024") -> list[str]:
        """列出某系统下所有已加载的分类"""
        with self._lock:
            return list(self._resolve_cache(system, edition).keys())

    def has(self, system: str, category: str, name: str,
            edition: str = "2024") -> bool:
        """检查某条规则是否存在"""
        return self.get(system, category, name, edition=edition) is not None

    def is_loaded(self, system: str, category: str | None = None,
                  edition: str = "2024") -> bool:
        """检查是否已加载"""
        with self._lock:
            sys_data = self._resolve_cache(system, edition)
            if category:
                return category in sys_data
            return bool(sys_data)

    # ----------------------------------------------------------------
    # 检索
    # ----------------------------------------------------------------

    def search(self, query: str, system: str = "dnd5e",
               category: str | None = None, top_k: int = 5,
               edition: str = "2024") -> list[dict]:
        """按关键词检索

        匹配字段：name_zh, name_en, summary, description, tags
        匹配方式：name 完全匹配 > 名称包含 > summary 包含

        Args:
            query: 关键词（中文或英文）
            system: 规则系统
            category: 限定分类（None = 全部）
            top_k: 返回前 K 条
        """
        if not query or not query.strip():
            return []

        with self._lock:
            sys_data = self._resolve_cache(system, edition)
            if category:
                cats = {category: sys_data.get(category, {})}
            else:
                cats = sys_data

        scored: list[tuple[float, dict]] = []
        q_lower = query.lower().strip()
        q_zh = query.strip()

        for cat_name, items in cats.items():
            for item in items.values():
                if not isinstance(item, dict):
                    continue
                score = self._score_item(item, q_lower, q_zh)
                if score > 0:
                    scored.append((score, item))

        scored.sort(key=lambda x: -x[0])
        return [item for _, item in scored[:top_k]]

    def _score_item(self, item: dict, q_lower: str, q_zh: str) -> float:
        """给一条规则打分"""
        score = 0.0

        name_zh = (item.get("name_zh") or "").lower()
        name_en = (item.get("name_en") or "").lower()

        # 完全匹配（最高）
        if q_zh == (item.get("name_zh") or "").strip():
            score += 20
        elif q_lower == name_en:
            score += 20
        # 名称包含
        elif q_zh in (item.get("name_zh") or ""):
            score += 10
        elif q_lower in name_en:
            score += 10
        # 短名称（≤4 字符）要求子串
        elif len(q_zh) <= 4 and q_zh in name_zh:
            score += 5

        # summary 包含
        summary = (item.get("summary") or "").lower()
        if q_zh in (item.get("summary") or ""):
            score += 3
        elif q_lower in summary:
            score += 2

        # description 包含
        desc = (item.get("description") or "").lower()
        if q_zh in (item.get("description") or ""):
            score += 2
        elif q_lower in desc:
            score += 1

        # tags 包含
        tags = item.get("tags", [])
        if any(q_zh in str(t) or q_lower in str(t).lower() for t in tags):
            score += 2

        return score

    # ----------------------------------------------------------------
    # 维护
    # ----------------------------------------------------------------

    def clear(self, system: str | None = None) -> None:
        """清空缓存"""
        with self._lock:
            if system:
                self._cache.pop(system, None)
            else:
                self._cache.clear()

    def stats(self) -> dict:
        """统计信息"""
        with self._lock:
            result = {}
            for sys_name, cats in self._cache.items():
                result[sys_name] = {
                    cat: len(items) for cat, items in cats.items()
                }
            return result


# ═════════════════════════════════════════════════════════════
# 全局单例
# ═════════════════════════════════════════════════════════════

_default_book: RulesBook | None = None
_default_lock = threading.Lock()


def get_default_rules_book() -> RulesBook:
    """获取默认 RulesBook 单例（懒加载 + 预加载 dnd5e）"""
    global _default_book
    with _default_lock:
        if _default_book is None:
            _default_book = RulesBook()
            try:
                _default_book.load("dnd5e")
            except Exception as e:
                logger.warning(f"[rules] 预加载 dnd5e 失败: {e}")
        return _default_book


def reset_default_rules_book() -> None:
    """重置默认 RulesBook（仅供测试）"""
    global _default_book
    with _default_lock:
        if _default_book is not None:
            _default_book.clear()
        _default_book = None
