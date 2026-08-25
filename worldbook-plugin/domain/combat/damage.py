"""damage - 伤害计算（PHB p.197）

D&D 5e 伤害应用规则（独立应用，不累乘）：
1. 免疫 → 0 伤害
2. 易伤 → 翻倍
3. 抗性 → 减半（向下取整）
4. 临时HP 优先抵消
5. 暴击由调用方在掷骰时翻倍（这里只记录标记）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DmgCalcResult:
    """伤害计算结果"""
    final_amount: int  # 经抗/免/易伤后、扣临时HP 前的实际 HP 伤害
    initial_amount: int
    temp_absorbed: int
    actual_damage: int  # 实际扣减 HP 的伤害
    vulnerabilities_applied: int = 0
    resistances_applied: int = 0
    immunities_applied: int = 0
    killed: bool = False
    calc_steps: List[str] = field(default_factory=list)


def apply_damage_modifiers(
    creature: Dict[str, Any],
    template: Optional[Dict[str, Any]],
    amount: int,
    damage_type: str,
    critical: bool = False,
) -> DmgCalcResult:
    """应用抗/免/易伤，返回 DmgCalcResult（不写回 creature）。

    调用方负责扣临时HP 与最终 hp 写回。
    """
    initial_amount = amount
    vuln_applied = 0
    res_applied = 0
    imm_applied = 0
    calc_steps: List[str] = []

    if damage_type and template:
        # 1) 免疫
        if damage_type in template.get("damage_immunities", []):
            amount = 0
            imm_applied += 1
            calc_steps.append(f"免疫 {damage_type} 伤害 → 伤害归零")
        else:
            # 2) 易伤（先于抗性）
            if damage_type in template.get("damage_vulnerabilities", []):
                amount = amount * 2
                vuln_applied += 1
                calc_steps.append(
                    f"易伤 {damage_type} → 伤害翻倍: {initial_amount} → {amount}"
                )
            # 3) 抗性
            if damage_type in template.get("damage_resistances", []):
                amount = amount // 2
                res_applied += 1
                calc_steps.append(f"抵抗 {damage_type} → 伤害减半: → {amount}")
    if not calc_steps:
        calc_steps.append(f"初始伤害: {initial_amount} 点{damage_type}伤害")

    if critical:
        calc_steps.append("💥 暴击！伤害骰已翻倍")

    # 临时 HP 吸收
    hp = creature.get("hp", {})
    temp = hp.get("temp", 0)
    current = hp.get("current", 0)
    temp_absorbed = 0
    actual_damage = amount
    new_current = current

    if temp > 0:
        if amount <= temp:
            temp_absorbed = amount
            actual_damage = 0
            new_current = current
            calc_steps.append(
                f"临时HP吸收: {temp_absorbed} 点（剩余临时HP: {temp - temp_absorbed}）"
            )
        else:
            temp_absorbed = temp
            actual_damage = amount - temp
            new_current = max(0, current - actual_damage)
            calc_steps.append(f"临时HP吸收: {temp_absorbed} 点（已耗尽）")
            calc_steps.append(f"实际生命伤害: {actual_damage} 点")
    else:
        new_current = max(0, current - amount)
        if amount > 0:
            calc_steps.append(f"生命伤害: {amount} 点")

    killed = new_current <= 0 and creature.get("is_alive", True)

    return DmgCalcResult(
        final_amount=amount,
        initial_amount=initial_amount,
        temp_absorbed=temp_absorbed,
        actual_damage=actual_damage,
        vulnerabilities_applied=vuln_applied,
        resistances_applied=res_applied,
        immunities_applied=imm_applied,
        killed=killed,
        calc_steps=calc_steps,
    )


def build_rule_reference(
    damage_type: str,
    res_applied: int,
    vuln_applied: int,
    imm_applied: int,
    had_temp_hp: bool,
    critical: bool,
    killed: bool,
) -> str:
    """组装 PHB p.197 规则引用文本。"""
    parts = ["📖 规则依据：DnD 5e 伤害规则（PHB p.197）。"]
    if damage_type:
        parts.append(f"{damage_type}伤害。")
    if had_temp_hp:
        parts.append("临时HP优先抵消伤害，耗尽后才扣实际HP。")
    if res_applied:
        parts.append(f"伤害抗性：{damage_type} 减半（向下取整），共应用 {res_applied} 次。")
    if vuln_applied:
        parts.append(f"伤害易伤：{damage_type} 翻倍，共应用 {vuln_applied} 次。")
    if imm_applied:
        parts.append(f"伤害免疫：{damage_type} 伤害无效，共应用 {imm_applied} 次。")
    if critical:
        parts.append("暴击：伤害骰翻倍（不含调整值），抗/免/易伤仍按规则应用。")
    if killed:
        parts.append("HP降至0时目标倒下；玩家角色需进行死亡豁免。")
    return " ".join(parts)
