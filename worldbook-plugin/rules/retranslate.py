"""retranslate - 用现有 mapping 给已存的 JSON 加 name_zh

不重跑 mcp_sync，节省 API 调用。只在原文件上"补中文名"。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .zh_mapping import get_zh, _is_english

logger = logging.getLogger(__name__)

# {category: filename}
CATEGORY_FILES = {
    "spells": "spells.json",
    "classes": "classes.json",
    "conditions": "conditions.json",
    "creatures": "creatures.json",
    "items": "items.json",
}


def _retranslate_rule(rule: dict) -> bool:
    """补一条规则的 name_zh。返回是否改动了。"""
    rid = rule.get("rule_id", "")
    parts = rid.split(".")
    if len(parts) < 4:
        return False
    category = parts[2]
    slug = parts[3]
    current_zh = rule.get("name_zh", "")
    if current_zh and not _is_english(current_zh):
        return False  # 已经有中文
    zh = get_zh(category, slug)
    if not zh:
        return False
    rule["name_zh"] = zh
    return True


def retranslate_file(json_path: Path) -> tuple[int, int]:
    """补一个 JSON 文件里所有规则的 name_zh。

    支持结构：
    - {"spells": [rule, ...], "creatures": [rule, ...], "conditions": [rule, ...]}
    - {"classes": {slug: rule, ...}, "items": {slug: rule, ...}}
    """
    if not json_path.exists():
        return (0, 0)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return (0, 0)

    # 找到包含 list 或 {slug: rule} 的字段（spells/classes/conditions/creatures/items）
    target_key = None
    target_value = None
    for key in ("spells", "creatures", "conditions", "classes", "items"):
        if key in data and isinstance(data[key], (list, dict)):
            target_key = key
            target_value = data[key]
            break
    if target_key is None:
        return (0, 0)

    total = 0
    changed = 0
    if isinstance(target_value, list):
        for rule in target_value:
            if not isinstance(rule, dict):
                continue
            total += 1
            if _retranslate_rule(rule):
                changed += 1
    else:  # dict {slug: rule}
        for slug, rule in target_value.items():
            if not isinstance(rule, dict):
                continue
            total += 1
            if _retranslate_rule(rule):
                changed += 1

    if changed > 0:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return (total, changed)


def retranslate_builtin(root: Path | None = None) -> list[tuple[str, tuple[int, int]]]:
    """遍历 rules/builtin/{system}/{edition}/*.json 补中文。

    Returns:
        [(rel_path, (total, changed)), ...] sorted
    """
    if root is None:
        root = Path(__file__).parent / "builtin"

    results: list[tuple[str, tuple[int, int]]] = []
    if not root.exists():
        return results

    for cat_file in CATEGORY_FILES.values():
        for json_path in root.rglob(cat_file):
            total, changed = retranslate_file(json_path)
            rel = json_path.relative_to(root.parent.parent)
            results.append((str(rel), (total, changed)))
    return sorted(results)


def main():
    logging.basicConfig(level=logging.INFO)
    results = retranslate_builtin()
    total_changed = 0
    for path, (total, changed) in results:
        if total > 0:
            pct = changed * 100 / total if total else 0
            marker = "*" if changed else " "
            print(f"{marker} {path:50s} {changed:4d}/{total:4d} ({pct:5.1f}%)")
            total_changed += changed
    print(f"\n共修改 {total_changed} 条规则的 name_zh")


if __name__ == "__main__":
    main()
