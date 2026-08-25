"""战斗数值校验器（Combat Value Guard）

方案 A 的核心：在 AI 生成回复后，校验战斗数值是否通过工具记录。
只在战斗激活时工作，避免误伤社交/探索叙事。

校验策略（状态机限定，不用语义猜）：
1. 战斗未激活 → 不校验
2. 战斗激活中 → 检测回复里的战斗数值表述：
   - 伤害："造成 X 点伤害"、"受到 X 点伤害"、"X 伤害"
   - HP："HP 剩余 X"、"还剩 X HP"、"X 点生命"
   - 命中/未命中："命中"、"未命中"、"暴击"
3. 如果检测到了，检查本轮对话历史里有没有对应的工具调用
   - 有 trpg_combat_damage / combat_attack 等 → 放行
   - 没有 → 在回复末尾加醒目警告

这是软约束，不是硬拦截——在回复末尾加警告提示 DM，
而不是阻断回复（避免误杀影响体验）。
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 战斗数值相关的工具名（调用过这些就认为数值是通过工具的）
COMBAT_TOOL_NAMES = {
    "trpg_combat_damage",
    "trpg_combat_heal",
    "trpg_combat_attack",  # 攻击+伤害（如果将来有）
    "trpg_combat_condition_add",
    "trpg_combat_next_turn",
    "trpg_check",  # 检定
    "trpg_spell_cast",  # 施法
}

# 伤害表述的正则模式
DAMAGE_PATTERNS = [
    r'造成[了]?\s*(\d+)\s*点?\s*(?:伤害|穿刺伤害|挥砍伤害|钝击伤害|火焰伤害|冰霜伤害|闪电伤害|毒素伤害|酸性伤害| necrotic|光耀伤害|雷鸣伤害|力场伤害|精神伤害)',
    r'(\d+)\s*点?\s*(?:伤害|穿刺伤害|挥砍伤害|钝击伤害|火焰伤害)',
    r'受到[了]?\s*(\d+)\s*点?\s*伤害',
    r'掉了[了]?\s*(\d+)\s*点?\s*(?:HP|生命)',
    r'减少[了]?\s*(\d+)\s*点?\s*(?:HP|生命)',
]

# HP 表述
HP_PATTERNS = [
    r'(?:HP|生命)[^0-9]{0,5}(\d+)\s*[/／]\s*(\d+)',  # X/Y
    r'剩余\s*(\d+)\s*点?\s*(?:HP|生命)',
    r'还剩\s*(\d+)\s*点?\s*(?:HP|生命)',
    r'(?:HP|生命)\s*为\s*(\d+)',
]

# 命中/未命中
HIT_PATTERNS = [
    r'(?:攻击|箭|刀|剑|锤|矛|斧)[^。！？]{0,15}(?:命中|击中|砍中|刺中|射中)',
    r'(?:未命中|失手|偏了|闪开|躲过|格挡)',
    r'暴击|重击',
]


class CombatValueGuard:
    """战斗数值校验器"""

    def __init__(self, state_mgr):
        self.state = state_mgr
        # 轮次边界：pre_llm_call 时 mark_turn_start 记录本轮起点 version，
        # transform_llm_output 时只看 version 增量，精确判断"本轮"有无战斗工具调用。
        self._current_turn_id = object()   # sentinel，保证首个 turn 也能触发记录
        self._turn_start_version = 0

    def mark_turn_start(self, turn_id) -> None:
        """pre_llm_call 时调用：新 turn 记录当前状态 version 作为本轮起点

        turn_id 同一 turn 内不变（agentic 循环多次 pre_llm_call 共用一个 turn_id），
        只有 turn 切换时才更新起点，避免把前序工具调用的变更算进下一轮。
        """
        if turn_id == self._current_turn_id:
            return
        self._current_turn_id = turn_id
        try:
            state = self.state.get()
            self._turn_start_version = (
                state.get("version", 0) if isinstance(state, dict) else 0
            )
        except Exception as e:
            logger.debug(f"[combat_guard] mark_turn_start 读取版本异常: {type(e).__name__}: {e}")
            self._turn_start_version = 0

    def _current_version(self) -> int:
        try:
            state = self.state.get()
            return state.get("version", 0) if isinstance(state, dict) else 0
        except Exception:
            return 0

    def is_combat_active(self) -> bool:
        """是否处于战斗状态"""
        try:
            combat = self.state.get("combat")
            if isinstance(combat, dict):
                return combat.get("active", False)
            return False
        except Exception as e:
            # 状态读取异常：按非战斗处理（不阻断校验），但记录便于排查
            logger.debug(f"[combat_guard] is_combat_active 读取状态异常: {type(e).__name__}: {e}")
            return False

    def check_response(self, response_text: str,
                       conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """校验 AI 回复中的战斗数值

        Args:
            response_text: AI 回复文本
            conversation_history: 本轮对话历史（用于检查是否有工具调用）

        Returns:
            {
                "combat_active": bool,
                "issues_found": list,     # 发现的问题
                "warnings": list,        # 警告文本
                "needs_tool_calls": bool, # 是否疑似漏了工具调用
            }
        """
        result = {
            "combat_active": self.is_combat_active(),
            "issues_found": [],
            "warnings": [],
            "needs_tool_calls": False,
        }

        # 非战斗中不校验
        if not result["combat_active"]:
            return result

        # 检查本轮有没有调用战斗工具（用 event_log 的 version 增量精确判定）
        has_combat_tool = self._has_combat_tool_this_turn()

        # 检测伤害表述
        damage_numbers = self._extract_damage(response_text)
        if damage_numbers:
            result["issues_found"].append({
                "type": "damage",
                "numbers": damage_numbers,
            })
            if not has_combat_tool:
                result["needs_tool_calls"] = True
                result["warnings"].append(
                    f"⚠️ 检测到伤害数值（{', '.join(str(n) for n in damage_numbers)}），"
                    f"但本轮未调用 trpg_combat_damage 工具。"
                    f"战斗伤害必须通过工具记录，请使用 trpg_combat_damage 后再描述。"
                )

        # 检测 HP 表述
        hp_numbers = self._extract_hp(response_text)
        if hp_numbers and not has_combat_tool:
            # 只在明确提到具体怪物 HP 剩余时警告
            result["issues_found"].append({
                "type": "hp",
                "numbers": hp_numbers,
            })
            # HP 表述不一定是数值变更（可能只是引用状态），不强制警告
            # 但如果没有工具调用且给了精确数字，提醒一下
            if len(hp_numbers) >= 2:  # 提到了具体 X/Y
                pass  # 先不警告，误报率可能高

        # 检测命中表述
        hits = self._extract_hits(response_text)
        if hits and not has_combat_tool:
            # 命中表述也先不强制警告，因为 AI 可能只是在描述"玩家说他要攻击"
            # 只有同时出现伤害数字 + 命中才是强信号
            pass

        return result

    def format_warning_footer(self, check_result: Dict) -> str:
        """生成警告页脚（加在回复末尾）"""
        warnings = check_result.get("warnings", [])
        if not warnings:
            return ""

        lines = [
            "",
            "─" * 40,
            "🛡️ [战斗数值校验警告]",
        ]
        for w in warnings:
            lines.append(f"  {w}")
        lines.append("─" * 40)
        return "\n".join(lines)

    # ----------------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------------

    def _has_combat_tool_this_turn(self) -> bool:
        """精确判断「本轮」是否发生了战斗工具调用产生的状态变更

        transform_llm_output 钩子拿不到 conversation_history/tool_calls，
        只能用 state.event_log 反推。关键改进：用 event_log 里每个事件的
        `version` 字段（每次 update 递增）做精确边界，而不是模糊的 60 秒窗口。

        判定逻辑：event_log 从最新往回扫，遇到 version <= 本轮起点就停
        （version 严格递增，之前的都是上一轮）；期间若有 combat.* / player.hp
        路径的变更，说明本轮确实走了战斗工具。
        """
        try:
            state = self.state.get()
            if not isinstance(state, dict):
                return False
            event_log = state.get("event_log", [])
            # 最多扫 100 条（一个 turn 的变更不会超过几十条）
            for event in reversed(event_log[-100:]):
                if event.get("version", 0) <= self._turn_start_version:
                    break  # 已越过本轮起点，剩下的都是上一轮
                path = event.get("path", "")
                if path.startswith("combat.") or path.startswith("player.hp"):
                    return True
        except Exception as e:
            logger.debug(f"[combat_guard] 读取事件日志异常: {type(e).__name__}: {e}")
        return False

    def _extract_damage(self, text: str) -> List[int]:
        """提取伤害数字"""
        numbers = []
        for pat in DAMAGE_PATTERNS:
            for m in re.finditer(pat, text):
                try:
                    numbers.append(int(m.group(1)))
                except (ValueError, IndexError):
                    pass
        return list(set(numbers))  # 去重

    def _extract_hp(self, text: str) -> List[Tuple[int, int]]:
        """提取 HP 数值对（current, max）"""
        results = []
        for pat in HP_PATTERNS:
            for m in re.finditer(pat, text):
                try:
                    if m.groups() and len(m.groups()) >= 2:
                        results.append((int(m.group(1)), int(m.group(2))))
                    elif m.groups():
                        results.append((int(m.group(1)), 0))
                except (ValueError, IndexError):
                    pass
        return list(set(results))

    def _extract_hits(self, text: str) -> List[str]:
        """提取命中/未命中表述"""
        hits = []
        for pat in HIT_PATTERNS:
            for m in re.finditer(pat, text):
                hits.append(m.group(0))
        return hits
