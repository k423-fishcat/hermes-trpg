"""检定引擎工具（D&D 5e check）"""

from .registry import ToolRegistry


def register(reg: ToolRegistry, state, chron):
    @reg.tool(
        name="trpg_check",
        description="执行一次 DnD 5e 检定（技能/属性/豁免/死亡豁免）。自动从玩家状态读取加值，自动附规则引用，结果可追溯。所有需要掷骰子的判定必须调用此工具，不允许口述判定。",
        schema={
            "name": "trpg_check",
            "description": "执行 DnD 5e 检定（技能/属性/豁免/死亡豁免）",
            "parameters": {
                "type": "object",
                "properties": {
                    "check_type": {
                        "type": "string",
                        "description": "检定类型: skill(技能检定) / ability(属性检定) / save(豁免检定) / death(死亡豁免)",
                        "default": "skill",
                    },
                    "check_name": {
                        "type": "string",
                        "description": "技能名（如运动/隐匿/游说）或属性名（力量/敏捷）或豁免名（敏捷豁免）",
                        "default": "",
                    },
                    "dc": {"type": "integer", "description": "难度等级 DC", "default": 15},
                    "advantage": {"type": "boolean", "description": "是否优势", "default": False},
                    "disadvantage": {"type": "boolean", "description": "是否劣势", "default": False},
                    "bonus": {"type": "integer", "description": "额外加值/减值", "default": 0},
                    "use_proficiency": {
                        "type": "boolean",
                        "description": "是否计算熟练加值（技能检定默认是，属性检定默认否）",
                        "default": True,
                    },
                    "description": {"type": "string", "description": "检定描述（做什么）", "default": ""},
                },
                "required": ["check_name"],
            },
        },
        emoji="🎯",
    )
    def check(args):
        from ..check_engine import roll_check, format_check_result
        try:
            result = roll_check(
                state, check_type=args.get("check_type", "skill"),
                check_name=args.get("check_name", ""),
                dc=args.get("dc", 15), advantage=args.get("advantage", False),
                disadvantage=args.get("disadvantage", False),
                bonus=args.get("bonus", 0),
                use_proficiency=args.get("use_proficiency", True),
                description=args.get("description", ""),
                chron=chron)
            return format_check_result(result)
        except Exception as e:
            return f"❌ 检定失败: {e}"
