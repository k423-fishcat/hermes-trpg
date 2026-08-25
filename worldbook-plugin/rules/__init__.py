"""rules 模块 - 本地规则书快照

子模块：
- rule_id: 规则 ID 命名 + 解析
- schema: 数据 schema 校验（轻量版，不依赖 jsonschema）
- loader: RulesBook 类 - 加载 + 检索

数据存储：rules/builtin/{system}/{category}.json
所有运行时只读，不写入。
"""

from .rule_id import (
    make_rule_id,
    parse_rule_id,
    RuleId,
    SYSTEM_PREFIX,
)
from .loader import RulesBook, get_default_rules_book
from .schema import validate_category, SchemaError

__all__ = [
    "make_rule_id",
    "parse_rule_id",
    "RuleId",
    "SYSTEM_PREFIX",
    "RulesBook",
    "get_default_rules_book",
    "validate_category",
    "SchemaError",
]
