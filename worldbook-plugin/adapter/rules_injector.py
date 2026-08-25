"""RulesInjector - 按当前上下文自动注入相关规则片段

注入到 pre_llm_call 钩子返回的 system_addition 字段。
玩家说"火球术" → 自动注入 fireball 摘要 + rule_id
玩家说"长休" → 注入 long_rest 摘要
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 关键词 → 规则分类 + name 映射
KEYWORD_RULES = {
    # 休息
    "长休": ("rest", "long_rest"),
    "短休": ("rest", "short_rest"),
    "休息": ("rest", "short_rest"),
    "契约法术位": ("rest", "warlock_pact_magic"),
    # 死亡
    "死亡豁免": ("combat", "death_saving_throw"),
    "濒死": ("combat", "death_saving_throw"),
    # 战斗
    "暴击": ("combat", "critical_hit"),
    "抗性": ("combat", "damage_resistance"),
    "易伤": ("combat", "damage_vulnerability"),
    "免疫": ("combat", "damage_immunity"),
    "优势": ("combat", "advantage"),
    "劣势": ("combat", "disadvantage"),
    # 技能
    "察觉": ("checks", "perception"),
    "隐匿": ("checks", "stealth"),
    "潜行": ("checks", "stealth"),
    "说服": ("checks", "persuasion"),
    "欺瞒": ("checks", "deception"),
    "威吓": ("checks", "intimidation"),
    "调查": ("checks", "investigation"),
    "奥秘": ("checks", "arcana"),
    "洞察": ("checks", "insight"),
}


class RulesInjector:
    """规则按需注入器"""

    def __init__(self, rules_book):
        self.rules = rules_book

    def inject_for_context(self, prompt: str, system: str = "dnd5e",
                           max_injections: int = 3) -> str:
        """从 prompt 检测涉及的规则，生成 markdown 块。

        Returns:
            markdown 字符串（空字符串表示无注入）
        """
        if not prompt or not prompt.strip():
            return ""
        if not self.rules or not self.rules.is_loaded(system):
            return ""

        triggered = self._detect_triggers(prompt, system)
        if not triggered:
            return ""

        # 去重
        seen = set()
        injected: list[str] = []
        for category, name in triggered:
            if len(injected) >= max_injections:
                break
            rule = self.rules.get(system, category, name)
            if not rule or not isinstance(rule, dict):
                continue
            rid = rule.get("rule_id", "")
            if rid in seen or not rid:
                continue
            seen.add(rid)
            injected.append(self._format_rule(rule))

        if not injected:
            return ""

        return "## 📖 规则速查（自动注入，来源 PHB 规则书）\n" + "\n".join(injected)

    def _detect_triggers(self, prompt: str, system: str) -> list[tuple[str, str]]:
        """从 prompt 检测可能涉及的规则 (category, name) 列表"""
        triggers: list[tuple[str, str]] = []
        prompt_lower = prompt.lower()

        # 1. 关键词触发
        for keyword, (category, name) in KEYWORD_RULES.items():
            if keyword in prompt:
                triggers.append((category, name))

        # 2. 法术名触发（查 spells 分类）
        try:
            spell_names = self.rules.list_names(system, "spells")
            for slug in spell_names:
                rule = self.rules.get(system, "spells", slug)
                if not rule:
                    continue
                name_zh = rule.get("name_zh", "")
                name_en = rule.get("name_en", "")
                # 中文名精确匹配（短名）优先
                if name_zh and len(name_zh) <= 12 and name_zh in prompt:
                    triggers.append(("spells", slug))
                # 英文名（lowercase 比较）
                elif name_en and name_en.lower() in prompt_lower:
                    triggers.append(("spells", slug))
        except Exception:
            pass

        # 3. 状态名触发
        try:
            cond_names = self.rules.list_names(system, "conditions")
            for slug in cond_names:
                rule = self.rules.get(system, "conditions", slug)
                if not rule:
                    continue
                name_zh = rule.get("name_zh", "")
                name_en = rule.get("name_en", "")
                if name_zh and name_zh in prompt:
                    triggers.append(("conditions", slug))
                elif name_en and name_en.lower() in prompt_lower:
                    triggers.append(("conditions", slug))
        except Exception:
            pass

        # 4. 怪物名触发（避免对所有 331 个怪物都查——只查短名 ≤ 12 字符的）
        try:
            creature_names = self.rules.list_names(system, "creatures")
            for slug in creature_names:
                # 跳过带连字符/下划线太多的（通常是变种）
                if slug.count("_") > 3:
                    continue
                rule = self.rules.get(system, "creatures", slug)
                if not rule:
                    continue
                name_zh = rule.get("name_zh", "")
                name_en = rule.get("name_en", "")
                if name_zh and len(name_zh) <= 12 and name_zh in prompt:
                    triggers.append(("creatures", slug))
                elif name_en and len(name_en) <= 20 and name_en.lower() in prompt_lower:
                    triggers.append(("creatures", slug))
        except Exception:
            pass

        return triggers

    def _format_rule(self, rule: dict) -> str:
        """格式化单条规则为 markdown 行（中英对照）

        例子：
            - **火球术 / Fireball** (`rules.dnd5e.spells.fireball`, PHB p.241): ...
        """
        name_zh = rule.get("name_zh", "")
        name_en = rule.get("name_en", "")
        rid = rule.get("rule_id", "")
        phb = f", PHB p.{rule['phb_page']}" if rule.get("phb_page") else ""

        # 中英对照标题
        if name_zh and name_en and name_zh != name_en:
            # 检查 name_zh 是否含 ASCII（部分映射可能不完整）
            if any(ord(c) >= 128 for c in name_zh):
                title = f"{name_zh} / {name_en}"
            else:
                # 翻译没命中（zh 还是英文）—— 只显示英文
                title = name_en
        elif name_zh:
            title = name_zh
        elif name_en:
            title = name_en
        else:
            title = "?"

        summary = (
            rule.get("summary")
            or rule.get("description")
            or rule.get("desc")
            or ""
        )
        if len(summary) > 200:
            summary = summary[:200] + "..."
        return f"- **{title}** (`{rid}`{phb}): {summary}"
