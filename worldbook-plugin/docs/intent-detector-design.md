# Intent Detector — 行为约束层设计

> 日期：2026-08-25
> 范围：D&D 5e（2024 规则优先）；3r / COC 后续复用架构
> 目标：让"AI 该检定/该攻击/该施法"从软约束（SOUL.md 自觉）变成硬约束（意图触发）

---

## 〇、问题

长团中 AI 最常犯的错不是"编错数字"（已有 combat_guard 事后校验），而是**忘了该走规则流程**：

```
玩家：我看看房间里有没有异常
AI：你环顾四周，一切如常。      ← 没有掷骰，白看
```

`trpg_check` / `combat_*` / `spell_cast` / `rest` 工具全都有，但调用靠 AI 自觉。
本层在 **AI 开口之前** 先扫描玩家输入，命中规则事件，把"必须调用的工具 + 顺序"注入上下文。

---

## 一、架构

```
Player Input
    │
    ▼
Intent Detector     // 正则多命中扫描 → RuleEvent 列表（不淘汰，全部保留）
    │
    ▼
Action Rules       // 规则声明表（系统无关：ActionRule dataclass）
    │
    ▼
Rule Events        // SkillCheckEvent / AttackEvent / SpellEvent / RestEvent / LootEvent
    │
    ▼
Tool Planner       // 事件 → (工具, 执行顺序, 注入文本)；按系统查映射
    │
    ▼
LLM（pre_llm_call 注入）
```

**设计原则**：
1. **多触发，不覆盖** — 一条输入可命中多个规则事件，全部保留，按规则顺序注入
2. **规则与系统解耦** — Detector/Planner 与规则数据分离；换系统（5e/3r/coc）只换规则表
3. **声明式规则** — 加规则 = 加一个 `ActionRule` 实例，不改核心逻辑
4. **两级触发** — 强触发（必须检定）vs 弱触发（判断失败可能），控制误报

---

## 二、核心数据结构

### 2.1 ActionCategory（9 类规则事件）

```python
class ActionCategory(Enum):
    EXPLORATION = "exploration"
    SOCIAL      = "social"
    COMBAT      = "combat"
    SPELL       = "spell"
    TRAVEL      = "travel"
    REST        = "rest"
    INVENTORY   = "inventory"
    LOOT        = "loot"
    DOWNTIME    = "downtime"
```

### 2.2 ActionRule（规则声明）

```python
@dataclass
class ActionRule:
    name: str                    # "Perception" / "Attack" / "Loot"
    pattern: re.Pattern          # 编译正则（多组交替）
    category: ActionCategory
    strength: int                # 1=强触发(必须检定) 2=弱触发(判断失败可能)
    order: int                   # 规则执行顺序（Initiative 先于 Attack）
    inject: str                  # 注入文本模板，含 {ability}/{skill}/{tool} 占位
    # 预留扩展字段（现在用不到，dataclass 加字段不用重构）
    system: str | None = None    # 限定系统（None=通用）
    cooldown: int | None = None  # 冷却：同一规则 N 轮内不重复注入
    exclusive: bool = False      # 命中后跳过其他同 category 规则
```

### 2.3 RuleEvent（检测结果）

```python
@dataclass
class RuleEvent:
    type: str                    # "skill_check"/"attack"/"initiative"/"spell"/"rest"/"loot"
    rule: str                    # 来源规则名 "Stealth"
    category: ActionCategory
    ability: str | None          # "dex"
    skill: str | None            # "Stealth"
    tool: str | None             # "trpg_check"
    text: str                    # 最终注入文本（Tool Planner 生成）
```

---

## 三、Intent Detector（多命中扫描）

### 3.1 流程

```python
def detect(user_input: str, rules: list[ActionRule]) -> list[RuleEvent]:
    events = []
    for rule in rules:
        if rule.pattern.search(user_input):
            events.append(rule_to_event(rule, user_input))
    events.sort(key=lambda e: e_order(e))   # 按规则顺序
    return events
```

### 3.2 两级词表（5e 中文）

**一级强触发**（命中几乎必须检定）：

```python
STRONG_TRIGGERS = {
    "Perception":    r"搜索|搜查|翻找|寻找|找找|侦查|搜寻|搜一下|检查房间|环顾四周|观察周围",
    "Investigation": r"调查|研究|分析|推理|寻找机关|找线索|破解|辨认痕迹|查看细节",
    "Insight":       r"判断.*说谎|察言观色|揣摩|试探|看穿|识破",
    "Stealth":       r"潜行|偷偷|悄悄|溜过去|摸过去|躲|藏|潜|匍匐",
    "SleightOfHand": r"撬锁|开锁|扒窃|偷.*包|顺走|摸包|变戏法|藏东西",
    "Athletics":     r"推门|撞门|踹门|爬|攀|举|搬|抬|跳.*过去|翻越|游泳",
    "Acrobatics":    r"翻滚|平衡|钻过去|翻窗|闪避.*障碍",
    "Survival":      r"追踪|辨认脚印|找路|辨别方向|生火|狩猎",
    "Arcana":        r"辨认法术|魔法物品|法阵|魔法知识|奥秘",
    "Religion":      r"辨认.*神祇|仪式|圣徽|恶魔|亡灵.*知识",
    "History":       r"回忆.*历史|王国|典故|古代.*知识",
    "Medicine":      r"检查伤势|诊断|止血|急救|判断.*病情",
    "Nature":        r"辨认.*植物|动物|矿石|自然现象",
    "Persuasion":    r"说服|劝|谈判|讲价|请求|商量",
    "Deception":     r"撒谎|欺骗|伪装|编理由|忽悠|掩饰",
    "Intimidation":  r"威胁|恐吓|震慑|逼问|威吓",
    "Performance":   r"演奏|唱歌|跳舞|演戏|表演",
    "AnimalHandling": r"安抚.*动物|驯服|骑乘|控制.*动物",
}

# 软性弱触发（命中只提示"判断失败可能"）
WEAK_TRIGGERS = {
    "Perception":  r"看|看一眼|看看|听|听听|闻|闻闻|摸|摸摸|观察|张望|偷看|瞄|端详|打量",
}
```

**强触发注入**（明确要求）：

```
[规则触发] 玩家行动涉及 {skill}（{ability}）。若该行动存在失败可能，
必须先调用 {tool} 完成检定，再写叙事。禁止直接口述结果。
```

**弱触发注入**（留判断权，控误报）：

```
[规则提示] 玩家行动涉及感知类（看/听/闻/摸）。请判断该行动是否存在失败可能；
若存在，必须调用技能检定后再叙事；若只是陈述/无失败可能，可忽略。
```

> 弱触发的关键：不强制，但把"是否该检定"的责任显式交给 AI 判断，
> 减少"我看了看地图"这类误报。

---

## 四、硬触发事件（5e）

### 4.1 攻击 / 先攻（Combat）

```python
COMBAT_RULES = [
    ActionRule("Attack",    r"攻击|砍|刺|射|挥剑|挥刀|施放.*攻击|打.*守卫|拔剑.*砍",
               COMBAT, 1, 30,
               "玩家发起攻击。必须进入战斗流程：若未开战先 trpg_combat_start（含先攻），"
               "再调用 trpg_combat_damage 结算。"),
    ActionRule("Initiative", r"动手|开战|战斗开始|拔剑|发起攻击|进入战斗|偷袭",
               COMBAT, 1, 20,
               "进入战斗。必须调用 trpg_combat_start 排先攻顺序。"),
]
```

**组合示例**：`我潜行过去偷袭守卫` → 命中 `Stealth`（order 10）+ `Initiative`（order 20）+ `Attack`（order 30）→ 注入顺序：先潜行检定 → 再先攻 → 后攻击。

### 4.2 施法（Spell）

```python
SPELL_RULES = [
    ActionRule("CastSpell", r"施放|施展|念咒|释放法术|使用魔法|准备.*法术",
               SPELL, 1, 40,
               "玩家施法。必须调用 trpg_spell_cast 校验法术位/专注/目标合法性，"
               "不得直接口述法术效果。"),
]
```

### 4.3 休息（Rest，事件化）

```
Rest Event → 是否安全 → 是否被打断 → 消耗补给 → 恢复资源 → 推进时间
```

```python
REST_RULES = [
    ActionRule("ShortRest", r"短休|休息一小时|歇一会", REST, 1, 40,
               "短休。调用 trpg_short_rest：消耗命中骰恢复 HP，推进 1 小时。"),
    ActionRule("LongRest",  r"长休|睡觉|扎营|过夜|睡一觉", REST, 1, 40,
               "长休。调用 trpg_long_rest：恢复全部资源，推进 8 小时。"
               "判断营地是否安全 / 是否会被打断。"),
]
```

### 4.4 Loot（独立事件，5e）

```
Loot Event → 读取尸体/容器 → 生成掉落 → 加入队伍(trpg_inventory_add) → 记录日志
```

```python
LOOT_RULES = [
    ActionRule("Loot", r"摸尸|搜身|翻尸体|搜刮|捡.*战利品|搜.*宝箱|翻.*口袋",
               LOOT, 1, 40,
               "搜刮。必须先检查是否有陷阱/危险（若存在则先感知检定），"
               "再生成合理掉落并用 trpg_inventory_add 加入背包，记录日志。"
               "禁止直接口述掉落内容。"),
]
```

> Loot 与 Investigation 分离：摸尸是 loot 流程，不是调查检定。

---

## 五、Tool Planner（事件 → 工具 + 顺序）

### 5.1 事件 → 工具映射（按系统）

```python
# dnd5e.py
SKILL_TO_TOOL = {
    "Perception":    ("wis", "Perception",    "trpg_check"),
    "Investigation": ("int", "Investigation", "trpg_check"),
    "Insight":       ("wis", "Insight",       "trpg_check"),
    "Stealth":       ("dex", "Stealth",       "trpg_check"),
    "SleightOfHand": ("dex", "Sleight of Hand","trpg_check"),
    "Athletics":     ("str", "Athletics",     "trpg_check"),
    "Acrobatics":    ("dex", "Acrobatics",    "trpg_check"),
    "Survival":      ("wis", "Survival",      "trpg_check"),
    "Arcana":        ("int", "Arcana",        "trpg_check"),
    "Religion":      ("int", "Religion",      "trpg_check"),
    "History":       ("int", "History",       "trpg_check"),
    "Medicine":      ("wis", "Medicine",      "trpg_check"),
    "Nature":        ("int", "Nature",        "trpg_check"),
    "Persuasion":    ("cha", "Persuasion",    "trpg_check"),
    "Deception":     ("cha", "Deception",     "trpg_check"),
    "Intimidation":  ("cha", "Intimidation",  "trpg_check"),
    "Performance":   ("cha", "Performance",   "trpg_check"),
    "AnimalHandling":("wis", "Animal Handling","trpg_check"),
}

# 事件类型 → 工具序列
EVENT_TO_TOOL = {
    "initiative": ["trpg_combat_start"],
    "attack":     ["trpg_combat_damage"],
    "spell":      ["trpg_spell_cast"],
    "rest":       ["trpg_short_rest", "trpg_long_rest"],
    "loot":       ["trpg_inventory_add"],
}
```

### 5.2 执行顺序

```python
EVENT_ORDER = {
    "skill_check": 10,   # 先检定
    "initiative":  20,   # 再进战斗/先攻
    "attack":      30,   # 后攻击
    "spell":       40,   # 施法
    "rest":        40,   # 休息
    "loot":        50,   # 搜刮
}
```

### 5.3 注入文本生成

```python
def plan(events: list[RuleEvent]) -> str:
    ordered = sorted(events, key=lambda e: EVENT_ORDER.get(e.type, 99))
    return "\n".join(e.text for e in ordered)
```

---

## 六、与 injector 整合

`injector.py` 的 `_do_inject` 在 P0 段（战斗约束同层）调用 intent 层：

```python
# 战斗约束之后、任务之前，插入意图触发
from .intent import detect_intent
events = detect_intent(user_message, template_name)
if events:
    sections.append({
        "priority": 0,
        "name": "规则触发",
        "content": planner.plan(events),
        "max_ratio": 0.10,   # 触发文本设上限，防刷屏
    })
```

**长度控制**：多触发时注入文本可能较长，复用现有「优先级配额制」。
触发注入作为 P0 但 `max_ratio=0.10`，超过从最低优先级截断。

---

## 七、与现有系统分工

| 层 | 管什么 | 位置 |
|----|--------|------|
| **Intent Detector** | 事前：该检定/该攻击/该施法 | `injector.py`（pre_llm_call） |
| **combat_guard** | 事后：AI 编数字 | `__init__.py`（transform_llm_output） |

两者互补，互不干扰。intent 堵"忘流程"，combat_guard 堵"编数字"。

---

## 八、文件结构

```
worldbook-plugin/
├── intent/                    # 🆕
│   ├── __init__.py           # 公共入口 detect_intent(user_input, template_name) -> str
│   ├── types.py              # ActionCategory / ActionRule / RuleEvent
│   ├── detector.py           # 多命中扫描
│   ├── planner.py            # 事件→工具+顺序+文本
│   └── dnd5e.py             # 5e 规则表（技能触发 + 硬触发 + 工具映射）
├── injector.py               # P0 段调用 detect_intent
└── tests/
    └── test_intent.py       # 🆕
```

---

## 九、实施计划

| 阶段 | 内容 | 产出 | 工作量 |
|:---:|------|------|:---:|
| **P1** | types + detector + 5e 技能触发表（两级词表）+ injector 接入 | 最小可用：技能检定触发 | 1.5h |
| **P2** | planner + 攻击/先攻/施法/休息事件 + 组合触发排序 | 战斗链可用 | 1.5h |
| **P3** | Loot 事件 + Rest 事件化深化 + 3r/coc 规则表 | 全事件类型 + 多系统 | 2h |

**P1 验收**：
- `我检查箱子` → 注入强触发 Perception/Investigation，含 `trpg_check`
- `我看了看地图` → 注入弱触发（提示判断失败可能），不强检
- `我潜行过去` → 注入 Stealth 强触发
- `test_intent.py` 全绿

---

## 十、测试计划（test_intent.py）

```python
# 强触发
assert "Perception" in detect_intent("我搜索房间")
assert "trpg_check" in detect_intent("我撬开锁")

# 弱触发
assert "判断" in detect_intent("我看了一眼地图")   # 弱提示，不含"必须"
assert "必须" not in detect_intent("我看了一眼地图")

# 多触发组合
events = detect("我潜行过去偷袭守卫")
assert {"Stealth", "Initiative", "Attack"} <= {e.rule for e in events}
# 顺序：Stealth < Initiative < Attack
assert order(events) == ["Stealth", "Initiative", "Attack"]

# 不误报
assert detect_intent("我打个招呼") == ""
assert detect_intent("今天天气不错") == ""

# 无匹配不注入
assert detect_intent("我们继续赶路") in ("", "travel_rule")
```

---

*设计版本：v1.0*
*范围：D&D 5e*
*前置：架构重构 v2.7 已完成（测试套件 69 全绿可回归）*
