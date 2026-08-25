"""rule_id 命名与解析

格式：rules.{system}.{category}.{name}

例：
  rules.dnd5e.spells.fireball
  rules.dnd5e.classes.wizard
  rules.dnd5e.combat.critical_hit
  rules.dnd5e.conditions.stunned
  rules.dnd5e.rest.long_rest
  rules.dnd5e.checks.stealth

system ∈ {"dnd5e", "dnd3r", "coc7e", "custom"}
category ∈ {"spells", "classes", "conditions", "combat", "rest", "checks",
            "equipment", "spell_slots", "items", "creatures"}
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SYSTEM_PREFIX = "rules"

# 支持的 system
VALID_SYSTEMS = {"dnd5e", "dnd3r", "coc7e", "custom"}

# 支持的 category（按 system 不同有差异，但 loader 不强制）
VALID_CATEGORIES = {
    "spells", "classes", "conditions", "combat", "rest", "checks",
    "equipment", "spell_slots", "items", "creatures",
    "rules",  # 通用规则条目（如 combat.json 里的 "rules" 字段）
}


@dataclass(frozen=True)
class RuleId:
    """规则 ID 的结构化表示"""
    system: str
    category: str
    name: str

    def __str__(self) -> str:
        return make_rule_id(self.system, self.category, self.name)


def make_rule_id(system: str, category: str, name: str) -> str:
    """构造规则 ID"""
    system = _normalize(system)
    category = _normalize(category)
    name = _normalize(name, allow_dot=False)
    return f"{SYSTEM_PREFIX}.{system}.{category}.{name}"


def parse_rule_id(rid: str) -> RuleId | None:
    """解析规则 ID，失败返回 None"""
    if not isinstance(rid, str):
        return None
    parts = rid.split(".")
    if len(parts) != 4:
        return None
    if parts[0] != SYSTEM_PREFIX:
        return None
    system, category, name = parts[1], parts[2], parts[3]
    if system not in VALID_SYSTEMS:
        return None
    if category not in VALID_CATEGORIES:
        return None
    if not name:
        return None
    return RuleId(system=system, category=category, name=name)


def _normalize(s: str, allow_dot: bool = True) -> str:
    """归一化：lowercase、替换空格为下划线、移除非法字符"""
    if not s:
        return ""
    s = str(s).strip().lower()
    # 空格 → 下划线
    s = s.replace(" ", "_").replace("-", "_")
    # 移除非字母数字下划线（中文保留）
    pattern = r"[a-z0-9_一-鿿]" if allow_dot else r"[a-z0-9_一-鿿]"
    s = "".join(re.findall(pattern, s))
    return s or "unnamed"
