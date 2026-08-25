"""状态 Schema 校验

基于模板文件派生 schema，不引入 Pydantic 等额外依赖。

校验内容：
- 字段类型是否匹配（dict/list/int/str/bool/float）
- 缺失字段用模板默认值补（向后兼容）
- 类型不匹配给出明确的错误定位
- 读取和写入双向校验
"""

import copy
from typing import Any, Dict, List, Tuple


def validate_and_fill(state: Dict[str, Any], template: Dict[str, Any],
                      path: str = "") -> Tuple[Dict[str, Any], List[str]]:
    """校验状态并填充缺失字段（用模板默认值）

    Args:
        state: 当前状态
        template: 模板（作为 schema）
        path: 当前路径（用于报错定位）

    Returns:
        (填充后的状态, 警告列表)
    """
    warnings = []
    result = copy.deepcopy(state)

    for key, tmpl_val in template.items():
        current_path = f"{path}.{key}" if path else key

        if key not in result:
            # 缺失字段，用模板默认值填充
            result[key] = copy.deepcopy(tmpl_val)
            warnings.append(f"字段缺失: {current_path}，已填充默认值")
            continue

        actual_val = result[key]
        expected_type = _type_name(tmpl_val)
        actual_type = _type_name(actual_val)

        if expected_type == "dict" and actual_type == "dict":
            # 递归校验嵌套 dict
            filled, sub_warnings = validate_and_fill(actual_val, tmpl_val, current_path)
            result[key] = filled
            warnings.extend(sub_warnings)

        elif expected_type == "list" and actual_type == "list":
            # 列表：如果模板有元素样例，校验元素类型
            if tmpl_val and isinstance(tmpl_val[0], dict):
                # 列表里是对象（如 inventory 列表），逐个校验结构
                new_list = []
                for i, item in enumerate(actual_val):
                    if isinstance(item, dict):
                        filled, sub_w = validate_and_fill(
                            item, tmpl_val[0], f"{current_path}[{i}]"
                        )
                        new_list.append(filled)
                        warnings.extend(sub_w)
                    else:
                        new_list.append(item)
                result[key] = new_list

        elif expected_type != actual_type and tmpl_val is not None and actual_val is not None:
            # 类型不匹配，但 None 值允许（表示空）
            # 尝试修复：数字转字符串可以，字符串转数字试试
            if expected_type == "str" and actual_type in ["int", "float"]:
                result[key] = str(actual_val)
                warnings.append(f"类型转换: {current_path} {actual_type}→str")
            elif expected_type in ["int", "float"] and actual_type == "str":
                try:
                    result[key] = int(actual_val) if expected_type == "int" else float(actual_val)
                    warnings.append(f"类型转换: {current_path} str→{expected_type}")
                except (ValueError, TypeError):
                    warnings.append(
                        f"类型不匹配: {current_path} 期望 {expected_type}，实际 {actual_type}，保留原值"
                    )
            # dict / list 的类型不匹配不强制转，保留原值但警告
            elif expected_type in ["dict", "list"]:
                warnings.append(
                    f"类型不匹配: {current_path} 期望 {expected_type}，实际 {actual_type}"
                )
                # 用模板默认值替换，防止后面的代码炸
                result[key] = copy.deepcopy(tmpl_val)

    # 检查 state 里有但 template 里没有的字段（不报错，只记录，允许扩展字段）
    extra_keys = set(result.keys()) - set(template.keys())
    # 系统字段（version, event_log, campaign 等）不算额外字段
    system_keys = {"version", "event_log", "campaign", "inventory", "conditions",
                   "active_modules", "combat", "world", "snapshots"}
    extra_non_system = extra_keys - system_keys
    if extra_non_system and not path:  # 只在顶层报一次
        for k in sorted(extra_non_system):
            if k.startswith("_"):
                continue
            warnings.append(f"额外字段（模板无定义）: {k}")

    return result, warnings


def validate_write(state: Dict[str, Any], template: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """写入前校验

    比读取校验更严格——不做自动填充，只检查结构性问题。

    Returns:
        (是否通过, 错误列表)
    """
    errors = []

    def _check(obj: Any, tmpl: Any, path: str) -> None:
        if isinstance(tmpl, dict):
            if not isinstance(obj, dict):
                errors.append(f"{path}: 期望 dict，实际 {type(obj).__name__}")
                return
            for k, v in tmpl.items():
                if k in obj:
                    _check(obj[k], v, f"{path}.{k}" if path else k)
        elif isinstance(tmpl, list):
            if not isinstance(obj, list):
                errors.append(f"{path}: 期望 list，实际 {type(obj).__name__}")
                return

    _check(state, template, "")
    return len(errors) == 0, errors


def _type_name(val: Any) -> str:
    """值的类型名（简化版）"""
    if val is None:
        return "none"
    if isinstance(val, bool):
        return "bool"
    if isinstance(val, int):
        return "int"
    if isinstance(val, float):
        return "float"
    if isinstance(val, str):
        return "str"
    if isinstance(val, list):
        return "list"
    if isinstance(val, dict):
        return "dict"
    return type(val).__name__
