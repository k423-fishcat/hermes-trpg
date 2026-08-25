"""D&D 5e 意图触发规则表

设计文档：docs/intent-detector-design.md 三/四节

- SKILL_TO_TOOL: 18 技能 → (ability, skill_name, tool)
- 强触发: 命中几乎必须检定
- 弱触发: 只提示"判断失败可能"，控制误报
"""

from __future__ import annotations

import re
from typing import List

from .types import ActionCategory, ActionRule


# 技能 → (属性, 技能名, 工具)
SKILL_TO_TOOL = {
    "Perception":      ("wis", "Perception",      "trpg_check"),
    "Investigation":   ("int", "Investigation",   "trpg_check"),
    "Insight":         ("wis", "Insight",         "trpg_check"),
    "Stealth":         ("dex", "Stealth",         "trpg_check"),
    "SleightOfHand":   ("dex", "Sleight of Hand", "trpg_check"),
    "Athletics":       ("str", "Athletics",       "trpg_check"),
    "Acrobatics":      ("dex", "Acrobatics",      "trpg_check"),
    "Survival":        ("wis", "Survival",        "trpg_check"),
    "Arcana":          ("int", "Arcana",          "trpg_check"),
    "Religion":        ("int", "Religion",        "trpg_check"),
    "History":         ("int", "History",         "trpg_check"),
    "Medicine":        ("wis", "Medicine",        "trpg_check"),
    "Nature":          ("int", "Nature",          "trpg_check"),
    "Persuasion":      ("cha", "Persuasion",      "trpg_check"),
    "Deception":       ("cha", "Deception",       "trpg_check"),
    "Intimidation":    ("cha", "Intimidation",    "trpg_check"),
    "Performance":     ("cha", "Performance",     "trpg_check"),
    "AnimalHandling":  ("wis", "Animal Handling", "trpg_check"),
}


# 一级强触发：这些动词几乎一定需要检定
STRONG_PATTERNS = {
    "Perception":      r"搜索|搜查|翻找|寻找|找找|侦查|搜寻|搜一下|环顾四周|观察周围|查看房间|扫视全场",
    "Investigation":   r"调查|研究|分析|推理|寻找机关|找线索|破解|辨认痕迹|查看细节|找机关|检查.*密道",
    "Insight":         r"看穿|识破|察言观色|揣摩.*意图|判断.*说谎|试探.*真假|打量.*表情",
    "Stealth":         r"潜行|偷偷|悄悄|溜过去|摸过去|匍匐|躲起来|藏到|潜到",
    "SleightOfHand":   r"撬锁|开锁|撬开|扒窃|偷.*包|顺走|摸包|藏起.*东西|变戏法",
    "Athletics":       r"撞.*门|踹.*门|推.*门|攀爬|爬.*墙|举起|搬开|抬.*石|跳过|翻越|游泳.*过去|爬上",
    "Acrobatics":      r"翻滚.*躲|平衡.*走|钻过去|翻窗|闪避.*落石",
    "Survival":        r"追踪|辨认脚印|找路|辨别方向|生火|狩猎|跟踪.*猎物",
    "Arcana":          r"辨认.*法术|识别.*魔法|检查.*法阵|魔法知识|鉴定.*魔法物品",
    "Religion":        r"辨认.*神祇|仪式|圣徽|恶魔.*知识|亡灵.*知识|教团",
    "History":         r"回忆.*历史|古代.*知识|王国.*典故|辨认.*遗迹",
    "Medicine":        r"检查伤势|诊断|止血|急救|判断.*病情|治疗.*伤口",
    "Nature":          r"辨认.*植物|辨认.*动物|辨认.*矿石|自然现象|辨认.*草药",
    "Persuasion":      r"说服|劝.*他|谈判|讲价|请求.*帮助|商量|讨好",
    "Deception":       r"撒谎|欺骗|伪装|编理由|忽悠|掩饰|假装",
    "Intimidation":    r"威胁|恐吓|震慑|逼问|威吓.*说出",
    "Performance":     r"演奏|唱歌|跳舞|演戏|表演|弹奏",
    "AnimalHandling":  r"安抚.*动物|驯服|骑乘|控制.*动物|安抚.*马",
}


# 二级弱触发：只提示判断失败可能
WEAK_PATTERNS = {
    "Perception": r"看|看一眼|看看|听|听听|闻|闻闻|摸|摸摸|观察|张望|偷看|瞄|端详|打量",
}


def _inject_text(skill: str, ability: str, tool: str, strong: bool) -> str:
    """生成注入文本（区分强弱触发）"""
    if strong:
        return (
            f"[规则触发] 玩家行动涉及 {skill}（{ability}）。若该行动存在失败可能，"
            f"必须先调用 {tool} 完成检定，再写叙事。禁止直接口述结果。"
        )
    return (
        f"[规则提示] 玩家行动涉及感知类观察（{skill}）。请先判断该行动是否存在失败可能；"
        f"若有失败可能，应调用 {tool} 检定后再叙事；若只是陈述/无失败可能，可忽略。"
    )


# 硬触发规则（非技能检定）：攻击/先攻/施法/休息/Loot
HARD_RULES = [
    # name, pattern, event_type, tool, order, inject
    ("Initiative",
     r"开战|开打|动手.*打|进入战斗|战斗开始|发起攻击|拔剑|先发制人|偷袭",
     "initiative", "trpg_combat_start", 20,
     "[规则触发] 玩家进入战斗。必须调用 trpg_combat_start 排先攻顺序，确认战斗状态后再叙事。"),
    ("Attack",
     r"攻击|砍|刺|射|挥剑|挥刀|偷袭|斩|劈|打.*守卫|施放.*攻击|挥拳",
     "attack", "trpg_combat_damage", 30,
     "[规则触发] 玩家发起攻击。必须进入战斗流程：若尚未开战先 trpg_combat_start（含先攻），"
     "再调用 trpg_combat_damage 结算。禁止直接口述攻击结果。"),
    ("CastSpell",
     r"施放|施展|念咒|释放法术|使用魔法|吟唱.*咒|准备.*法术",
     "spell", "trpg_spell_cast", 40,
     "[规则触发] 玩家施放法术。必须调用 trpg_spell_cast 校验法术位/专注/目标合法性，"
     "再描述效果。禁止直接口述法术生效。"),
    ("ShortRest",
     r"短休|休息一小时|歇一会|休息片刻",
     "rest", "trpg_short_rest", 40,
     "[规则触发] 玩家短休。调用 trpg_short_rest 消耗命中骰恢复 HP，并推进 1 小时。"),
    ("LongRest",
     r"长休|睡觉|扎营|过夜|睡一觉|搭营",
     "rest", "trpg_long_rest", 40,
     "[规则触发] 玩家长休/睡觉。调用 trpg_long_rest 恢复全部资源。"
     "先判断营地是否安全、是否会被打断。"),
    ("Loot",
     r"摸尸|搜身|翻尸体|搜刮|捡.*战利品|搜.*宝箱|翻.*口袋|搜.*尸体|检查.*尸体",
     "loot", "trpg_inventory_add", 50,
     "[规则触发] 玩家搜刮尸体/容器。先判断是否有陷阱或危险（若有先感知检定），"
     "再生成合理掉落用 trpg_inventory_add 加入背包并记录日志。禁止直接口述掉落内容。"),
]


def build_rules() -> List[ActionRule]:
    """构建 5e 触发规则：18 技能（强+弱）+ 硬触发（攻击/先攻/施法/休息/Loot）"""
    rules: List[ActionRule] = []

    # 强触发（18 技能）
    for skill, pattern in STRONG_PATTERNS.items():
        ability, skill_name, tool = SKILL_TO_TOOL[skill]
        rules.append(ActionRule(
            name=skill,
            pattern=re.compile(pattern),
            category=ActionCategory.EXPLORATION if ability in ("wis", "int") else ActionCategory.SOCIAL,
            strength=1,
            order=10,  # 技能检定最先
            inject=_inject_text(skill_name, ability, tool, strong=True),
            event_type="skill_check",
            tool=tool,
            ability=ability,
            skill=skill_name,
            system="dnd5e",
        ))

    # 弱触发（感知观察）
    for skill, pattern in WEAK_PATTERNS.items():
        ability, skill_name, tool = SKILL_TO_TOOL[skill]
        rules.append(ActionRule(
            name=f"{skill}.weak",
            pattern=re.compile(pattern),
            category=ActionCategory.EXPLORATION,
            strength=2,
            order=10,
            inject=_inject_text(skill_name, ability, tool, strong=False),
            event_type="skill_check",
            tool=tool,
            ability=ability,
            skill=skill_name,
            system="dnd5e",
        ))

    # 硬触发（攻击/先攻/施法/休息/Loot）
    for name, pattern, etype, tool, order, inject in HARD_RULES:
        rules.append(ActionRule(
            name=name,
            pattern=re.compile(pattern),
            category=_category_for(etype),
            strength=1,
            order=order,
            inject=inject,
            event_type=etype,
            tool=tool,
            system="dnd5e",
        ))

    return rules


def _category_for(event_type: str) -> ActionCategory:
    """事件类型 → 规则分类"""
    return {
        "initiative": ActionCategory.COMBAT,
        "attack": ActionCategory.COMBAT,
        "spell": ActionCategory.SPELL,
        "rest": ActionCategory.REST,
        "loot": ActionCategory.LOOT,
    }.get(event_type, ActionCategory.EXPLORATION)


__all__ = ["SKILL_TO_TOOL", "build_rules"]
