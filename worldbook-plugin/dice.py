"""集中骰子引擎（Centralized Dice Engine）

所有骰子运算的统一入口。替代分散在 5 个文件里的 13 处 random.randint 内联调用。

设计目标：
- 所有掷骰逻辑集中在此，AI / slash 命令 / MCP 工具全部走这一份
- 支持常见骰子表达式：1d20, 2d6+3, 4d6kh3 (DnD 5e 属性), adv/dis, COC 百分骰
- 每个函数返回结构化结果（结果值 + 详情），方便工具格式化输出
- 不依赖外部 MCP / Go 进程，纯 Python stdlib（random + re）

主要函数：
- roll_dice(count, sides)        投 N 颗 M 面骰
- roll(expr)                     解析表达式 2d6+3 / 1d20 / 4d6kh3 / adv / dis
- roll_d20(advantage, disadvantage) 单颗 d20，可选优势/劣势
- roll_damage(dice_expr, modifier, crit)  伤害骰，暴击翻倍
- roll_hit_dice(dice_expr)       命中骰（D&D 规则：最少 1）
- roll_healing(dice_expr, modifier) 治疗骰
- roll_ability_scores(method)    DnD 5e 属性掷骰
- coc_check(skill_value, ...)    COC 7e 技能检定
"""

import random
import re
from typing import Any, Dict, List, Optional, Tuple


# 表达式解析正则
# 形如：2d6, d20, 4d6kh3, 2d6+1, 1d8+3, 2d6+1d4+3
_DICE_RE = re.compile(r'(\d*)d(\d+)([+\-]\d+)?', re.IGNORECASE)
# 简易表达式项：单组 d 表达式 或 常数
_TERM_RE = re.compile(r'([+\-]?)\s*(\d*)d(\d+)|([+\-]?\d+)', re.IGNORECASE)


# ============================================================
# 基础掷骰
# ============================================================

def roll_dice(count: int, sides: int) -> List[int]:
    """投 N 颗 M 面骰，返回每颗结果列表

    Args:
        count: 骰子数量（>=1）
        sides: 骰子面数（>=2）

    Returns:
        每颗骰子的结果列表
    """
    if count < 1:
        raise ValueError(f"骰子数量必须 >= 1，得到 {count}")
    if sides < 2:
        raise ValueError(f"骰子面数必须 >= 2，得到 {sides}")
    if count > 1000:
        raise ValueError(f"骰子数量太多（最多 1000），得到 {count}")
    if sides > 10000:
        raise ValueError(f"骰子面数太多（最多 10000），得到 {sides}")
    return [random.randint(1, sides) for _ in range(count)]


def roll_d20(advantage: bool = False, disadvantage: bool = False) -> Dict[str, Any]:
    """单颗 d20 投掷，可选优势/劣势

    Returns:
        {
          "nat_roll": 天然骰值（最终用于判定的）,
          "all_rolls": [所有原始骰值],
          "is_advantage": 是否优势,
          "is_disadvantage": 是否劣势,
          "is_crit_success": nat_roll == 20,
          "is_crit_fail": nat_roll == 1,
        }
    """
    if advantage and not disadvantage:
        rolls = roll_dice(2, 20)
        nat_roll = max(rolls)
    elif disadvantage and not advantage:
        rolls = roll_dice(2, 20)
        nat_roll = min(rolls)
    else:
        rolls = roll_dice(1, 20)
        nat_roll = rolls[0]

    return {
        "nat_roll": nat_roll,
        "all_rolls": rolls,
        "is_advantage": bool(advantage and not disadvantage),
        "is_disadvantage": bool(disadvantage and not advantage),
        "is_crit_success": nat_roll == 20,
        "is_crit_fail": nat_roll == 1,
    }


# ============================================================
# 表达式解析（2d6+3, 4d6kh3, 等）
# ============================================================

def roll(expr: str) -> Dict[str, Any]:
    """解析骰子表达式并投掷

    支持的语法：
    - 基础: d20, 2d6, 4d8
    - 加减: d20+5, 3d6-2
    - 多组: 2d6+1d4+3
    - 优势/劣势: adv / dis
    - 百分骰: d100 / d%
    - 留高/留低: 4d6kh3 (DnD 属性)

    Returns:
        {
          "expression": 原表达式,
          "total": 总和,
          "details": 各组细节,
          "nat_20": 是否天然 20（仅 d20 适用）,
          "nat_1": 是否天然 1,
        }
    """
    original = expr
    expr_clean = expr.strip().lower().replace(" ", "")

    # 优势/劣势
    if expr_clean in ("adv", "advantage", "优势"):
        r = roll_d20(advantage=True)
        return {
            "expression": "2d20kh1 (优势)",
            "total": r["nat_roll"],
            "details": {"rolls": r["all_rolls"], "took": "max"},
            "nat_20": r["is_crit_success"],
            "nat_1": r["is_crit_fail"],
        }
    if expr_clean in ("dis", "disadv", "disadvantage", "劣势"):
        r = roll_d20(disadvantage=True)
        return {
            "expression": "2d20kl1 (劣势)",
            "total": r["nat_roll"],
            "details": {"rolls": r["all_rolls"], "took": "min"},
            "nat_20": r["is_crit_success"],
            "nat_1": r["is_crit_fail"],
        }

    # COC 百分骰
    if expr_clean in ("d100", "1d100", "d%"):
        r = random.randint(1, 100)
        return {
            "expression": original,
            "total": r,
            "details": {"type": "coc_percentile", "rolls": [r]},
            "nat_20": False,
            "nat_1": False,
        }

    # 通用表达式解析
    # 用 _TERM_RE 匹配每一项（带符号），支持多组相加
    terms = []
    pos = 0
    while pos < len(expr_clean):
        m = _TERM_RE.match(expr_clean, pos)
        if not m:
            raise ValueError(f"无法解析骰子表达式: {expr}（位置 {pos}）")
        sign_str, count_str, sides_str, const_str = m.groups()

        if const_str is not None:
            # 常数项（可能带符号 "3" / "-3"）
            const_str_stripped = const_str.lstrip("+-")
            if const_str_stripped:
                value = int(const_str_stripped)
                # 符号：先看 const_str 自己的首字符
                if const_str.startswith("-"):
                    sign = -1
                else:
                    sign = 1
                terms.append(("const", sign, value, 0))
            pos = m.end()
        else:
            # 骰子项
            sign = 1 if sign_str != "-" else -1
            count = int(count_str) if count_str else 1
            sides = int(sides_str)
            # 支持 kh/kl 后缀：4d6kh3
            rest = expr_clean[m.end():]
            keep = None
            keep_mode = None  # "high" or "low"
            kh_m = re.match(r'k(h|l)(\d+)', rest, re.IGNORECASE)
            if kh_m:
                keep_mode = "high" if kh_m.group(1).lower() == "h" else "low"
                keep = int(kh_m.group(2))
                pos = m.end() + len(kh_m.group(0))
            else:
                pos = m.end()
            terms.append(("dice", sign, count, sides, keep, keep_mode))

    # 实际掷骰
    total = 0
    details = []
    all_rolls: List[int] = []
    for term in terms:
        if term[0] == "const":
            _, sign, value, _ = term
            total += sign * value
            details.append({"type": "const", "value": value, "sign": sign})
        else:
            _, sign, count, sides, keep, keep_mode = term
            rolls = roll_dice(count, sides)
            if keep is not None and keep_mode is not None:
                sorted_rolls = sorted(rolls, reverse=(keep_mode == "high"))
                kept = sorted_rolls[:keep]
                dropped = sorted_rolls[keep:]
                subtotal = sum(kept) * sign
                total += subtotal
                all_rolls.extend(kept)
                details.append({
                    "type": "dice",
                    "expr": f"{count}d{sides}k{'h' if keep_mode == 'high' else 'l'}{keep}",
                    "rolls": rolls,
                    "kept": kept,
                    "dropped": dropped,
                    "subtotal": subtotal,
                    "sign": sign,
                })
            else:
                subtotal = sum(rolls) * sign
                total += subtotal
                all_rolls.extend(rolls)
                details.append({
                    "type": "dice",
                    "expr": f"{count}d{sides}",
                    "rolls": rolls,
                    "subtotal": subtotal,
                    "sign": sign,
                })

    # 单 d20 标记
    is_single_d20 = (
        len(details) == 1
        and details[0]["type"] == "dice"
        and details[0]["expr"] in ("1d20", "d20")
    )

    result: Dict[str, Any] = {
        "expression": original,
        "total": total,
        "details": details,
        "nat_20": is_single_d20 and all_rolls[0] == 20,
        "nat_1": is_single_d20 and all_rolls[0] == 1,
    }
    if is_single_d20:
        if result["nat_20"]:
            result["note"] = "暴击！天然 20！"
        elif result["nat_1"]:
            result["note"] = "大失败！天然 1！"

    return result


# ============================================================
# 伤害 / 治疗 / 命中骰
# ============================================================

def roll_damage(dice_expr: str, modifier: int = 0, crit: bool = False) -> Dict[str, Any]:
    """伤害骰（暴击时骰子数翻倍）

    Args:
        dice_expr: 武器伤害骰表达式，如 "1d8", "2d6"
        modifier: 伤害加值（通常是属性调整值）
        crit: 是否暴击

    Returns:
        {
          "dice_expr": 原表达式,
          "modifier": 加值,
          "crit": 是否暴击,
          "rolls": 各骰结果,
          "total": 总伤害（含 modifier）,
        }
    """
    parsed = _parse_single_dice(dice_expr)
    count, sides = parsed
    if crit:
        count *= 2
    rolls = roll_dice(count, sides)
    total = sum(rolls) + modifier
    return {
        "dice_expr": dice_expr,
        "modifier": modifier,
        "crit": crit,
        "rolls": rolls,
        "total": total,
    }


def roll_healing(dice_expr: str, modifier: int = 0) -> Dict[str, Any]:
    """治疗骰（支持带 modifier 的完整表达式，如 "2d4+2"）

    与 roll_damage 不同：法术治疗不暴击，直接解析整个表达式。
    单独的 modifier 参数会加在表达式结果之上（用于施法属性调整等）。

    Returns:
        {
          "dice_expr": 原表达式,
          "modifier": 加值,
          "rolls": 各骰结果,
          "total": 治疗量,
        }
    """
    # 用 roll() 解析完整表达式（含 modifier）
    r = roll(dice_expr)
    rolls = []
    for d in r["details"]:
        if isinstance(d, dict) and d.get("type") == "dice":
            rolls.extend(d.get("rolls", []))
    total = r["total"] + modifier
    return {
        "dice_expr": dice_expr,
        "modifier": modifier,
        "rolls": rolls,
        "total": total,
    }


def roll_hit_dice(sides: int) -> int:
    """单颗命中骰（D&D 规则：最少 1 点）

    用于升级 HP（level_up）：roll 至少 1，+ con mod，但即使加 mod 也至少 +1。

    Args:
        sides: 骰子面数（6/8/10/12）

    Returns:
        单颗骰子结果（1 ~ sides）
    """
    return random.randint(1, sides)


def roll_hit_dice_total(dice_expr: str, con_modifier: int = 0) -> Dict[str, Any]:
    """短休时用 N 颗命中骰恢复 HP

    Args:
        dice_expr: 命中骰表达式，如 "2d10"（2 颗 d10）
        con_modifier: 体质调整值

    Returns:
        {
          "dice_expr": 原表达式,
          "rolls": 各骰结果,
          "con_modifier": 体质加值,
          "raw_total": 骰子原始总和,
          "heal_total": 实际恢复 HP（最少 1/颗）,
        }
    """
    count, sides = _parse_single_dice(dice_expr)
    rolls = roll_dice(count, sides)
    # D&D 规则：每颗至少恢复 1（含 con_modifier）
    heal_per_die = [max(1, r + con_modifier) for r in rolls]
    return {
        "dice_expr": dice_expr,
        "rolls": rolls,
        "con_modifier": con_modifier,
        "raw_total": sum(rolls),
        "heal_total": sum(heal_per_die),
        "heal_per_die": heal_per_die,
    }


def roll_heal_spell(dice_expr: str, modifier: int = 0) -> Dict[str, Any]:
    """法术治疗：治疗骰总和 + 加值（可能为负）

    不像短休命中骰有"最少 1"的限制，法术治疗是纯加法。
    """
    return roll_healing(dice_expr, modifier)


# ============================================================
# DnD 属性 / COC 检定
# ============================================================

def roll_ability_scores(method: str = "standard") -> Dict[str, Any]:
    """DnD 5e 六项属性掷骰

    Args:
        method: standard (4d6kh3 标准) / classic (3d6 经典)
                / heroic (2d6+6 英雄) / flat (8+1d6)

    Returns:
        {
          "method": 方法名,
          "abilities": {六项属性: {结果, 各骰, ...}},
          "total": 6 项总和,
          "modifier_sum": 所有修正值之和,
        }
    """
    abilities = ["str", "dex", "con", "int", "wis", "cha"]
    results: Dict[str, Dict[str, Any]] = {}

    for ab in abilities:
        if method == "standard":
            rolls = roll_dice(4, 6)
            rolls_sorted = sorted(rolls, reverse=True)
            kept = rolls_sorted[:3]
            results[ab] = {
                "score": sum(kept),
                "rolls": rolls,
                "kept": kept,
            }
        elif method == "classic":
            rolls = roll_dice(3, 6)
            results[ab] = {"score": sum(rolls), "rolls": rolls}
        elif method == "heroic":
            rolls = roll_dice(2, 6)
            results[ab] = {"score": sum(rolls) + 6, "rolls": rolls, "bonus": 6}
        elif method == "flat":
            rolls = roll_dice(1, 6)
            results[ab] = {"score": 8 + rolls[0], "base": 8, "roll": rolls[0]}
        else:
            raise ValueError(
                f"未知方法: {method}，支持: standard / classic / heroic / flat"
            )

    total = sum(v["score"] for v in results.values())
    return {
        "method": method,
        "abilities": results,
        "total": total,
        "modifier_sum": sum((v["score"] - 10) // 2 for v in results.values()),
    }


def roll_initiative(dex_modifier: int = 0) -> Dict[str, Any]:
    """先攻掷骰（1d20 + dex 调整值）

    Args:
        dex_modifier: 敏捷调整值

    Returns:
        {"nat_roll": 天然 20/1, "modifier": 加值, "total": 最终先攻值}
    """
    r = roll_d20()
    return {
        "nat_roll": r["nat_roll"],
        "modifier": dex_modifier,
        "total": r["nat_roll"] + dex_modifier,
        "is_crit_success": r["is_crit_success"],
        "is_crit_fail": r["is_crit_fail"],
    }


# ============================================================
# COC 7e
# ============================================================

def coc_check(skill_value: int,
              bonus_dice: int = 0,
              penalty_dice: int = 0) -> Dict[str, Any]:
    """COC 7th 技能检定

    Args:
        skill_value: 技能值（1-99）
        bonus_dice: 奖励骰数量
        penalty_dice: 惩罚骰数量

    Returns:
        {
          "skill_value": 技能值,
          "roll": 最终骰值,
          "units": 个位骰,
          "tens_all": 所有十位骰,
          "bonus_dice": 奖励骰数,
          "penalty_dice": 惩罚骰数,
          "level": 成功等级,
          "success": 是否成功,
          "margin": 差值,
        }
    """
    if skill_value < 1 or skill_value > 99:
        raise ValueError(f"技能值必须在 1-99 之间，得到 {skill_value}")
    if bonus_dice < 0 or penalty_dice < 0:
        raise ValueError("奖励/惩罚骰不能为负")

    units = random.randint(0, 9)
    num_tens = 1 + bonus_dice + penalty_dice
    tens_list = [random.randint(0, 9) for _ in range(num_tens)]

    # 决定最终十位
    if bonus_dice > 0 and penalty_dice == 0:
        chosen_tens = min(tens_list)
    elif penalty_dice > 0 and bonus_dice == 0:
        chosen_tens = max(tens_list)
    else:
        # 同时有奖励和惩罚：奖励优先（取最小）
        chosen_tens = min(tens_list)

    roll_value = chosen_tens * 10 + units
    if roll_value == 0:
        roll_value = 100

    # 成功等级判定
    if roll_value == 1:
        level, success = "大成功", True
    elif roll_value == 100:
        level, success = "大失败", False
    elif roll_value > skill_value:
        level, success = "失败", False
    elif roll_value <= skill_value // 5:
        level, success = "极难成功", True
    elif roll_value <= skill_value // 2:
        level, success = "困难成功", True
    else:
        level, success = "成功", True

    return {
        "skill_value": skill_value,
        "roll": roll_value,
        "units": units,
        "tens_all": tens_list,
        "chosen_tens": chosen_tens,
        "bonus_dice": bonus_dice,
        "penalty_dice": penalty_dice,
        "level": level,
        "success": success,
        "margin": skill_value - roll_value,
    }


# ============================================================
# 辅助 / 解析
# ============================================================

def _parse_single_dice(expr: str) -> Tuple[int, int]:
    """解析单个 d 表达式（"1d8", "2d6"），返回 (count, sides)

    Raises:
        ValueError: 不是合法的 d 表达式
    """
    expr = expr.strip().lower().replace(" ", "")
    m = re.match(r'^(\d*)d(\d+)$', expr)
    if not m:
        raise ValueError(f"无法解析骰子表达式: {expr}（期望形如 '1d8' / '2d6'）")
    count = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    return count, sides


def format_roll_result(result: Dict[str, Any]) -> str:
    """把 roll() / roll_damage() 等的结果格式化为可读字符串

    用于 MCP 工具的返回值。
    """
    expr = result.get("expression") or result.get("dice_expr", "?")
    total = result.get("total", 0)
    details = result.get("details")

    # roll_damage / roll_healing 格式：rolls 在 result 顶层
    if "rolls" in result and isinstance(result["rolls"], list) and not details:
        rolls_str = ",".join(str(r) for r in result["rolls"])
        crit_str = "（暴击翻倍）" if result.get("crit") else ""
        mod = result.get("modifier", 0)
        mod_str = f"{mod:+d}" if mod else ""
        breakdown = f"[{rolls_str}]"
        if mod_str:
            breakdown += f" {mod_str}"
        return f"🎲 {expr}{crit_str} = {breakdown} = {total}"

    if isinstance(details, list):
        # roll() 格式：每项是 dice/const
        parts = []
        for i, d in enumerate(details):
            if d.get("type") == "const":
                val = d.get("value", 0)
                sign = d.get("sign", 1)
                # 第一项不带符号前缀（前面没东西要加）
                if i == 0:
                    parts.append(str(val) if sign > 0 else f"-{abs(val)}")
                else:
                    op = "+" if sign > 0 else "-"
                    parts.append(f"{op} {abs(val)}")
            else:
                rolls_str = ",".join(str(r) for r in d.get("rolls", []))
                parts.append(f"{d.get('expr', '?')}({rolls_str})")
        breakdown = " ".join(parts)
        lines = [f"🎲 {expr} = {breakdown} = {total}"]
    elif isinstance(details, dict) and "rolls" in details:
        # 优势/劣势 / COC 百分骰
        rolls = details["rolls"]
        rolls_str = ",".join(str(r) for r in rolls)
        took = details.get("took", "")
        if took:
            lines = [f"🎲 {expr} = [{rolls_str}] → {took} {total}"]
        else:
            lines = [f"🎲 {expr} = [{rolls_str}] = {total}"]
    else:
        lines = [f"🎲 {expr} = {total}"]

    if result.get("nat_20"):
        lines.append("💥 暴击！天然 20！")
    elif result.get("nat_1"):
        lines.append("💀 大失败！天然 1！")
    elif result.get("note"):
        lines.append(result["note"])

    return "\n".join(lines)


__all__ = [
    "roll_dice",
    "roll_d20",
    "roll",
    "roll_damage",
    "roll_healing",
    "roll_heal_spell",
    "roll_hit_dice",
    "roll_hit_dice_total",
    "roll_ability_scores",
    "roll_initiative",
    "coc_check",
    "format_roll_result",
]
