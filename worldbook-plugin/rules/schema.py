"""规则书数据 schema 校验

不依赖 jsonschema 库（避免引入重量级依赖）。
每个分类用 dict 描述必填字段和字段类型，validate_category 校验一份数据。
"""

from __future__ import annotations

from typing import Any, Callable

# ═════════════════════════════════════════════════════════════
# 各分类的 schema 定义
# ═════════════════════════════════════════════════════════════

# spells: 一条法术
SPELL_FIELDS = {
    "rule_id": str,
    "name_zh": str,
    "name_en": str,
    "level": int,
    "school": str,
    "casting_time": str,
    "range": str,
    "duration": str,
    "phb_page": (int, type(None)),
}

# classes: 一条职业（dict[英文名, data]）
CLASS_FIELDS = {
    "rule_id": str,
    "name_zh": str,
    "name_en": str,
    "hit_die": str,
    "caster_type": str,  # "known" | "prepared" | "none"
    "phb_page": (int, type(None)),
}

# conditions: 一条状态效果
CONDITION_FIELDS = {
    "rule_id": str,
    "name_zh": str,
    "name_en": str,
    "summary": str,
    "phb_page": (int, type(None)),
}

# combat / rest / 通用 rules: 一条规则
GENERIC_RULE_FIELDS = {
    "rule_id": str,
    "name_zh": str,
    "name_en": str,
    "summary": str,
    "phb_page": (int, type(None)),
}

# checks: 一条技能/豁免
CHECK_FIELDS = {
    "rule_id": str,
    "name_zh": str,
    "name_en": str,
    "ability": str,
    "phb_page": (int, type(None)),
}

# spell_slots: 整体（不逐条校验，校验顶层结构）
SPELL_SLOTS_FIELDS = {
    "full_caster": dict,
    "half_caster": dict,
    "warlock": dict,
}

CATEGORY_SCHEMAS: dict[str, tuple[list[str], dict]] = {
    # category → (list_key, fields_per_item)
    # list_key 是 JSON 里"条目列表"的 key 名
    "spells": ("spells", SPELL_FIELDS),
    "classes": ("classes", CLASS_FIELDS),  # 注意：classes 是 dict[英文名, data]
    "conditions": ("conditions", CONDITION_FIELDS),
    "combat": ("rules", GENERIC_RULE_FIELDS),
    "rest": ("rules", GENERIC_RULE_FIELDS),
    "items": ("items", GENERIC_RULE_FIELDS),
    "creatures": ("creatures", GENERIC_RULE_FIELDS),
    "checks": ("skills", CHECK_FIELDS),  # 默认校验 skills；saves 同样 schema
    "equipment": ("by_class", {}),  # 装备数据结构特殊，宽松校验
    "spell_slots": (None, SPELL_SLOTS_FIELDS),  # 特殊结构
}


class SchemaError(Exception):
    """schema 校验失败"""
    pass


def validate_category(category: str, data: dict) -> list[str]:
    """校验一个分类的数据，返回所有错误信息（不抛异常）。
    校验通过返回空列表。
    """
    errors: list[str] = []
    if category not in CATEGORY_SCHEMAS:
        errors.append(f"未知 category: {category}")
        return errors

    list_key, item_fields = CATEGORY_SCHEMAS[category]

    # 顶层字段
    if "version" not in data:
        errors.append(f"[{category}] 缺少 version 字段")
    if "category" not in data:
        errors.append(f"[{category}] 缺少 category 字段")

    # 条目列表
    if list_key is None:
        # spell_slots 特殊结构
        for k, t in item_fields.items():
            if k not in data:
                errors.append(f"[{category}] 缺少字段: {k}")
        return errors

    if list_key not in data:
        errors.append(f"[{category}] 缺少列表字段: {list_key}")
        return errors

    items = data[list_key]
    if not isinstance(items, (list, dict)):
        errors.append(f"[{category}] {list_key} 应为 list 或 dict，实际 {type(items).__name__}")
        return errors

    # items 是 list
    if isinstance(items, list):
        for i, item in enumerate(items):
            _check_item(category, list_key, i, item, item_fields, errors)
    # items 是 dict（classes 风格）
    elif isinstance(items, dict):
        for k, item in items.items():
            _check_item(category, list_key, k, item, item_fields, errors)

    return errors


def _check_item(category: str, list_key: str, key: Any, item: Any,
                fields: dict, errors: list[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"[{category}] {list_key}[{key}] 不是 dict: {type(item).__name__}")
        return
    for fname, ftype in fields.items():
        if fname not in item:
            errors.append(f"[{category}] {list_key}[{key}] 缺少字段: {fname}")
            continue
        val = item[fname]
        if not _check_type(val, ftype):
            errors.append(
                f"[{category}] {list_key}[{key}].{fname} "
                f"类型错误: 期望 {_type_name(ftype)}, 实际 {type(val).__name__}"
            )


def _check_type(val: Any, expected: Any) -> bool:
    if isinstance(expected, tuple):
        return any(_check_type(val, t) for t in expected)
    if expected is type(None):
        return val is None
    return isinstance(val, expected)


def _type_name(t: Any) -> str:
    if isinstance(t, tuple):
        return " | ".join(_type_name(x) for x in t)
    if t is type(None):
        return "None"
    return t.__name__
