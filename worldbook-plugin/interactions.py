"""世界书交互点系统（Interaction Points）

在世界书条目里嵌入预设的交互点数据，让探索/社交/陷阱等场景的检定
有明确的 DC 和后果，不完全靠 AI 临场编。

交互点数据结构：
{
  "id": "door_lockpick",
  "trigger": "撬锁",
  "type": "skill",          # skill / ability / save / item / dialogue
  "check": {
    "skill": "巧手",
    "ability": "dex",
    "dc": 15,
    "retry": true,          # 是否可以重试
    "retry_penalty": 0,     # 每次重试 DC 增加多少
  },
  "outcomes": {
    "success": "你悄无声息地撬开了锁，门轻轻地开了。",
    "failure": "你的撬锁工具卡在了锁里，发出了咔哒一声响。",
    "critical_success": "你毫不费力地打开了锁，甚至还能重新锁回去不留痕迹。",
    "critical_failure": "咔嘣——工具断了！锁也坏了，现在再也打不开了。",
  },
  "consequences": {
    "success_flags": ["door_unlocked"],
    "failure_flags": ["lock_broken"],
    "success_damage": "",
    "failure_damage": "1d4",
  },
  "rewards": {
    "xp": 0,
    "items": [],
    "info": "",
  },
  "hidden": false,           # 是否隐藏（需要检定才能发现）
  "discovery_dc": 12,        # 发现它需要的 DC（如果隐藏）
  "discovery_skill": "察觉",
}
"""

import re
from typing import Any, Dict, List, Optional


class InteractionEngine:
    """交互点引擎——解析交互点、判定、应用后果"""

    @staticmethod
    def find_interactions(entry: Dict, action_hint: str = "") -> List[Dict]:
        """从世界书条目中提取交互点

        Args:
            entry: 世界书条目 dict
            action_hint: 玩家动作关键词（用于过滤匹配的交互点）

        Returns:
            匹配的交互点列表
        """
        interactions = entry.get("interactions", [])
        if not interactions:
            return []

        if not action_hint:
            return list(interactions)

        # 按触发词匹配
        hint_lower = action_hint.lower()
        matched = []
        for ia in interactions:
            trigger = ia.get("trigger", "").lower()
            if trigger and trigger in hint_lower:
                matched.append(ia)
            # 也检查 id
            if ia.get("id", "").lower() in hint_lower:
                if ia not in matched:
                    matched.append(ia)

        # 如果有匹配的返回匹配的，否则返回全部（让 AI 判断）
        return matched if matched else list(interactions)

    @staticmethod
    def resolve_interaction(interaction: Dict,
                            roll_result: int,
                            total_bonus: int = 0) -> Dict[str, Any]:
        """解析交互点结果

        Args:
            interaction: 交互点数据
            roll_result: 检定结果（d20 值，不含加值）
            total_bonus: 玩家加值总和

        Returns:
            结果字典
        """
        check_info = interaction.get("check", {})
        dc = check_info.get("dc", 10)

        total = roll_result + total_bonus
        is_crit = roll_result == 20
        is_fumble = roll_result == 1

        # 判断成败
        if is_crit:
            outcome_key = "critical_success"
            success = True
        elif is_fumble:
            outcome_key = "critical_failure"
            success = False
        elif total >= dc:
            outcome_key = "success"
            success = True
        else:
            outcome_key = "failure"
            success = False

        outcomes = interaction.get("outcomes", {})
        description = outcomes.get(outcome_key, outcomes.get("success" if success else "failure", ""))

        consequences = interaction.get("consequences", {})
        rewards = interaction.get("rewards", {})

        return {
            "success": success,
            "outcome_type": outcome_key,
            "description": description,
            "dc": dc,
            "roll": roll_result,
            "total": total,
            "bonus": total_bonus,
            "consequences": consequences,
            "rewards": rewards,
            "interaction_id": interaction.get("id", ""),
            "trigger": interaction.get("trigger", ""),
        }

    @staticmethod
    def format_interaction_for_injection(interaction: Dict) -> str:
        """格式化交互点为可注入的文本（给 AI 看的）"""
        check = interaction.get("check", {})
        outcomes = interaction.get("outcomes", {})
        hidden = interaction.get("hidden", False)
        disc_dc = interaction.get("discovery_dc", 0)

        lines = []
        trigger = interaction.get("trigger", "")
        itype = interaction.get("type", "skill")

        lines.append(f"  ▶ [{itype}] {trigger}")

        if hidden:
            skill = interaction.get("discovery_skill", "察觉")
            lines.append(f"    🔍 隐藏：需要 {skill} DC{disc_dc} 才能发现")
        else:
            skill = check.get("skill", "")
            ability = check.get("ability", "")
            dc = check.get("dc", "?")
            check_label = skill or ability
            lines.append(f"    🎲 {check_label} DC{dc}")

        # 后果（简要）
        if outcomes.get("success"):
            succ = outcomes["success"][:60]
            if len(outcomes["success"]) > 60:
                succ += "..."
            lines.append(f"    ✅ 成功：{succ}")

        if outcomes.get("failure"):
            fail = outcomes["failure"][:60]
            if len(outcomes["failure"]) > 60:
                fail += "..."
            lines.append(f"    ❌ 失败：{fail}")

        return "\n".join(lines)

    @staticmethod
    def add_interaction_to_entry(entry: Dict, interaction: Dict) -> Dict:
        """给世界书条目添加交互点"""
        if "interactions" not in entry:
            entry["interactions"] = []
        entry["interactions"].append(interaction)
        return entry

    @staticmethod
    def quick_create(trigger: str, skill: str, dc: int,
                     success_text: str, failure_text: str,
                     interaction_id: str = "",
                     hidden: bool = False,
                     discovery_dc: int = 12,
                     itype: str = "skill") -> Dict:
        """快速创建一个交互点"""
        return {
            "id": interaction_id or trigger.replace(" ", "_"),
            "trigger": trigger,
            "type": itype,
            "check": {
                "skill": skill,
                "dc": dc,
                "retry": True,
            },
            "outcomes": {
                "success": success_text,
                "failure": failure_text,
            },
            "consequences": {},
            "rewards": {},
            "hidden": hidden,
            "discovery_dc": discovery_dc,
        }
