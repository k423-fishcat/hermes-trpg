# Worldbook 插件 vs TRPG-AI-DM — 对比分析

> 日期：2026-08-24
> 对比对象：
> - **自研**：`E:\Program\PaoTuan\worldbook-plugin`（Hermes 跑团系统，v2.5）
> - **参考**：`E:\Program\PaoTuan\Other\TRPG-AI-DM`（开源 Web 跑团，FastAPI + Vue）

> **2026-08-25 备注**：本文档记录的是 v2.5 时期的状态对比。当前自研插件已演进到 **v2.8**，主要变化：
> - `tools.py`（3514 行）已拆分为 `tools/` 子包
> - `state.py` 已拆分为 `state/` 包（含 RLock 并发保护）
> - 新增 `app_context.py` 服务容器（14 个服务）
> - 新增 `intent/` 意图检测层（v1: 18 技能 / v2: 6 硬触发）
> - 新增多规则系统（D&D 5e / 3r / COC 7e）
> - **D&D 5e PHB 规则书合规修复**（spells/combat/inventory/rest 共 4 模块，48 新测试，142 → 190 通过）
>
> 详细更新见 `docs/跑团系统-完整总结.md` 与 `docs/worldbook-architecture-review.md`。

---

## 〇、一句话总结

| | Worldbook 插件 | TRPG-AI-DM |
|---|---|---|
| **形态** | 嵌入 Hermes CLI 的对话引擎 | 独立 Web 应用（前后端分离） |
| **核心哲学** | 工具驱动 + 状态硬约束 + 多层记忆 | 工具驱动 + 三层硬约束 + 自动世界生成 |
| **最大优势** | 工程可靠性（原子写/快照/Schema）+ Hermes 生态 | 「AI 不会编错」三层防护 + 剧本自动化 |
| **最大短板** | 部署依赖 Hermes，CLI 体验门槛 | 单体 DM Agent 难维护，缺战役级长团记忆 |

---

## 一、基本盘对比

| 维度 | Worldbook 插件 | TRPG-AI-DM |
|------|---------------|-----------|
| 形态 | Hermes 插件（CLI 对话） | Web 应用（FastAPI + Vue/TS） |
| 代码规模 | ~13,758 行 Python | ~6,000 行 Python + ~前端 TS |
| 核心文件分布 | 工具 3514 行 + 叙事 1709 行 + 状态 570 行 + 战斗 689 行 | `dm_agent.py` **单文件 2334 行**（单体） |
| 数据存储 | 全部本地 JSON（人类可读） | SQLite（SQLAlchemy 异步）+ 本地 KB |
| 多用户 | ❌ 单人 | ✅ 每用户隔离（剧本/存档/角色/媒体） |
| 工具数量 | ~77 个 `trpg_*` 工具 | ~30 个 DM 工具（更少但更集成） |
| 规则系统 | dnd5e / coc7e 模板 | dnd5e / dnd4e / coc / custom skill 包 |
| RAG 后端 | 关键词 + OpenViking 向量 | jieba + TF-IDF + BM25（**零 token 成本**） |
| 规则深度 | 完整 SRD（依赖 dnd-rules MCP） | 自己实现 5e/4e/COC 规则引擎 |
| 部署难度 | 极低（装插件） | 中等（前后端 + DB） |
| 战斗模型 | 多步（start/attack/damage/turn 拆分） | **单步**（combat_round 一键完成） |
| 硬约束层数 | 两层（事前 P0 提示 + 事后 regex 校验） | **三层**（关键词触发 + 工具后场景校验 + 回合结束自动同步） |
| 冒险导入 | 手动整理（zim wiki 解析器） | **全自动**（PDF/DOC/MD → 切分 → 摘要 → 生成世界大纲） |
| 长团记忆 | 编年史 + 章节 + 里程碑 + 选择因果链 | 短期（5-10 轮）+ 自动压缩 + 长期 |
| 模式档位 | 单一模式 | **三档**（lite / standard / deep-thinking） |
| 数据安全 | 原子写 + 双快照（20+30） + Schema 校验 | 每轮自动存档 + response cache |
| UI | 无（CLI） | Vue 3 + TS + Tailwind + Zustand |
| 输出 | 纯文本 | SSE 流式 + Markdown 渲染 |

---

## 二、架构差异（核心）

### 2.1 Worldbook 插件：五层分离 + 工具拆分

```
Hermes Agent
   ↓ pre_llm_call 钩子
ContextInjector (P0~P6 优先级配额)
   ↓ 注入到 user_message
LLM (SOUL.md + Skills)
   ↓ Function Calls (~77 个 trpg_* 工具)
Tools.py + 业务模块（combat/state/inventory/spells/...）
   ↓ 状态变更
StateManager (原子写 + 快照 + Schema 校验)
   ↓ 持久化
data/campaigns/<战役>/state.json
   ↓ transform_llm_output 钩子
CombatGuard (事后 regex 校验)
```

**特点：**
- **工具按业务领域拆分**：combat.py、inventory.py、spells.py、check_engine.py 各自独立
- **状态层独立**：state.py 是中心，所有工具都通过它读写
- **钩子驱动的注入与校验**：pre/transform_llm_call 是约束的物理点

### 2.2 TRPG-AI-DM：FastAPI + 单体 DM Agent + 三层防护

```
Browser (Vue 3)
   ↓ HTTP/SSE
FastAPI (main.py, 1827 行)
   ↓ 调用
DM Agent (dm_agent.py, **2334 行单文件**)
   ↓ Function Calling
Tools (engine/tools.py, 16KB) + 规则计算 (game_systems.py, 33KB)
   ↓ 状态变更
WorldState (world_state.py, 23KB) + SQLAlchemy
   ↓ 持久化
SQLite + saves/ + scenarios/ + knowledge_base/
```

**特点：**
- **DM Agent 单体**：所有 LLM 交互、System Prompt、工具调度、约束注入都塞在一个文件
- **三层防护内嵌在 process_player_action 函数**（L2143-2257）：
  - 第一层 L2178-2183：感知动词正则触发系统提醒
  - 第二层 L2214-2225：每轮工具调用后强制场景校验
  - 第三层 L2240-2245：end_of_turn 时系统自动 advance_turn + save + push journal

### 2.3 关键差异

| 项 | Worldbook | TRPG-AI-DM |
|---|-----------|-----------|
| 工具粒度 | 细（一个工具一件事） | 粗（combat_round 一个工具打完一回合） |
| AI 自由度 | 高（自己组合工具） | 低（系统替你做） |
| 数值可靠性 | 依赖 AI 自觉 + 事后正则 | 物理上不可能错（工具里算死） |
| 叙事灵活度 | 高（AI 可以描述任意过程） | 中（被工具返回的格式约束） |
| 单文件复杂度 | 中（tools.py 3514 行但有清晰分区） | **高**（dm_agent.py 2334 行混杂 prompt + 工具 + 流程） |

---

## 三、TRPG-AI-DM 的核心亮点（按价值排序）

### 3.1 ⭐⭐⭐⭐⭐ 三层硬约束（最大可借鉴点）

**第一层：关键词触发强制检定**（`dm_agent.py:2178-2183`）

```python
perception_verbs = r'观察|聆听|嗅\b|摸\b|翻找|侦查|张望|偷看|检查|搜索|细看|倾听|嗅探|听\b|看\b|闻\b'
if re.search(perception_verbs, player_input):
    messages.append({"role":"system","content":
        "[系统提醒] B4规则：玩家正在进行感知行为。你必须判断DC和对应属性(WIS/Perception)，"
        "调用dice_roll。不允许仅用叙事代替检定。"})
```

**价值**：100% 可靠的「必须检定」触发器，零成本。
**现状对比**：Worldbook 完全靠 SOUL.md + AI 自觉，长团中容易「翻一下」「看看」被跳过。

**第二层：每轮工具调用后场景校验**（`dm_agent.py:2214-2225`）

```python
scene_check = (
    f"[系统校验——每轮工具调用后强制执行] "
    f"当前位置: {ws.scene.current_location} | "
    f"时间: {ws.scene.current_time or f'第{ws.scene.day_count}天'} | "
    f"天气: {ws.scene.weather} | "
    f"在场NPC: {', '.join(ws.scene.visible_npcs_here) if ws.scene.visible_npcs_here else '无'}"
    f"\n如果你接下来的叙事会改变以上任何一项，必须先调用update_scene。"
)
messages.append({"role":"system","content": scene_check})
```

**价值**：每轮重置场景上下文，根治「场景漂移」。
**现状对比**：Worldbook 注入一次后就靠 AI 记忆，跑着跑着忘了自己在哪。

**第三层：end_of_turn 自动同步**（`dm_agent.py:2240-2245`）

```python
ws.advance_turn()
ws.save()
await push_event(state, "journal_update", ws.to_player_journal())
```

**价值**：不再依赖 AI 主动调用 update_scene，系统替你同步。
**现状对比**：Worldbook 不会自动推进时间/天气/NPC，需要 AI 调工具。

### 3.2 ⭐⭐⭐⭐⭐ 战斗一键结算（`dm_agent.py:1345-1458`）

`_exec_combat_round` 一个工具做完所有事：
1. 自动读玩家攻击加值（角色卡推导）
2. 自动解析敌人（NPC 卡 → 图鉴卡 → 参数，三级兜底）
3. d20 命中 → 伤害 → 敌人反击
4. 写回状态（玩家受伤扣 HP + 敌人 HP 写回 NPC/图鉴实体）
5. 附带完整 extras（剩余HP/伤害量/是否死亡）

**关键点**：AI 只需要传 `player_action` 和 `enemy_name`，其他全工具算。**AI 物理上不可能编错伤害**。

**对比 Worldbook**：需要 AI 自己组合 combat_start → initiative → attack → damage → next_turn，长团中容易漏步骤。

### 3.3 ⭐⭐⭐⭐ 剧本自动生成世界（`scenario_importer.py` + `world_builder.py`）

完整流水线：
1. 上传 PDF/DOC/DOCX/TXT/MD
2. 自动切分（naive + 语义）
3. 生成 ~400 字剧本摘要
4. 调 LLM 生成完整世界大纲（世界观/主线/NPC/遭遇/规则）
5. 自动识别规则系统（5e/4e/COC/自定义）
6. 提取 NPC/怪物/法术进入图鉴
7. SSE 实时显示生成进度

**价值**：「剧本 → 可玩世界」自动化，省去手动整理世界书的劳动。
**对比 Worldbook**：LMOP 模组需要 zim 解析 → 手动归类 → 写进世界书。

### 3.4 ⭐⭐⭐⭐ 多规则系统 Skill 包（`skills/__init__.py` + `skills/prompts.py`）

每个规则系统一个 `Skill` 数据类：
- `system_prompt`：该系统的系统提示词（None = 用 D&D 5e 完整版）
- `tools`：工具集（COC 自动剔除 `death_saving_throw`）
- `max_tokens / temperature`：LLM 参数
- `history_rounds / rag_top_k`：记忆与检索参数
- `outline_limit / summary_limit`：摘要参数

加上 `DND4E_DECISION_PROMPT` / `COC_DECISION_PROMPT` 这种**紧凑 CoT 提示词**，比 Worldbook 的「DND 5e 完整版塞给所有系统」节省大量 token。

**对比 Worldbook**：SOUL.md 是单一版本，模板层只驱动状态结构（5e/coc 共用一份 SOUL）。

### 3.5 ⭐⭐⭐⭐ 本地 RAG 零 token（`knowledge_base.py`）

字符 bigram + jieba + TF-IDF + BM25 混合检索：
```python
final = 0.6 * tfidf_v + 0.4 * bm25_v
```

**价值**：完全不调用 LLM，零 token 成本，按规则系统过滤，5e 搜 5e、COC 搜 COC。
**对比 Worldbook**：依赖 OpenViking 向量，需要外部服务，且混合方式不同。

### 3.6 ⭐⭐⭐ 三档模式适配（`_play_mode`）

| 模式 | 回合记忆 | RAG top_k | token 上限 | 用途 |
|------|:-------:|:---------:|:---------:|------|
| lite | 5 轮 | 3 条 | 少 | 快速对话 |
| standard | 10 轮 | 5 条 | 中 | 正常跑团 |
| deep-thinking | 更长 | 更多 | 多 | 复杂场景 |

`compress_memory_if_needed` + `_thinking_params`（温度/最大 token 乘数）自动适配。

**对比 Worldbook**：当前只有一种模式，`max_chars=5000` 是死参数。

### 3.7 ⭐⭐⭐ 工程防护

- **每轮工具调用数限制**（lite 3、standard 5）防无限循环
- **响应缓存**（最近 50 条）省 token
- **反八股过滤**（`sanitize_narrative`）净化 AI 套话
- **每轮自动存档**（`auto_save_if_needed`）
- **SAN check / COC 理智检定**等规则细节

---

## 四、Worldbook 插件的独有优势

### 4.1 工程可靠性（5e 派系最强）

| 机制 | 作用 | 复杂度 |
|------|------|------|
| **原子写入** | 写临时文件 → fsync → os.replace，崩溃安全 | 中 |
| **双快照体系** | 版本快照（20） + 命名快照（30） | 中 |
| **回滚保险** | 滚回前自动存 pre_rollback | 低 |
| **Schema 校验** | 读取时自动补字段 + 修复类型，模板升级无感 | 高 |
| **事件日志** | 所有状态变更带 path + time，可追踪 | 中 |

TRPG-AI-DM 只有「每轮自动存档」，没有版本快照，误操作难回滚。

### 4.2 叙事结构最丰富

```
编年史（事件流）  ←→  章节（开/关/里程碑/总结）
任务（多阶段）   ←→  选择因果链（决策 + 后果 + 长期影响）
场次小结（自动注入）  ←→  章节回顾（8 维度总结）
```

TRPG-AI-DM 只有「短期记忆 + 压缩 + 长期」，没有章节/选择因果链这种叙事骨架。

### 4.3 多格式冒险导入框架

```
adventure/
├── loader.py       统一入口
├── models.py       中间数据模型
└── formats/
    ├── native.py   原生 JSON
    └── zim_wiki.py Zim Desktop Wiki
```

加新格式 = 加一个 parser，不用改核心。TRPG-AI-DM 用 AI 自动生成，但**质量不稳定**且依赖 LLM。

### 4.4 NPC 跨界（社交 ↔ 战斗）

NPC 可以关联怪物图鉴 statblock，社交 NPC 也能进战斗。`narrative/npcs.py` 实现了：
- 态度值（-100~+100，五档）
- 社交记录 + 日程 + 已知信息
- statblock 引用 + 自定义属性覆盖

TRPG-AI-DM 也有 NPC，但更偏向「实体卡」，没态度系统。

### 4.5 战斗硬约束（事后校验）

`combat_guard.py` 是 **Worldbook 独有的设计**：
- 不靠 LLM 自觉
- 事后扫描回复文本，匹配伤害/HP 数字
- 检查本轮有没有对应工具调用
- 没有就在回复末尾加 🛡️ 警告（只警告不阻断）

TRPG-AI-DM 选择了更激进的路：物理上让 AI 编不了（combat_round 一键算完）。

### 4.6 Hermes 生态

- 直接用任何 MCP 工具（dnd-rules、trpg-dice、osg-dice……）
- 复用 Hermes 的 OpenViking 长期记忆
- 不需要自己写 CLI 框架

TRPG-AI-DM 是独立服务，所有工具都得自己注册。

### 4.7 法术系统深度

- 已知 / 准备 / 法术位 三层分离
- 施法属性自动计算攻击加值和豁免 DC
- 法术位向上兼容
- **专注机制**：一次一个，受伤自动体质豁免（DC = max(10, 伤害/2)）
- 长休全部恢复，短休不恢复法术位

---

## 五、可直接借鉴到 Worldbook 的点（按 ROI 排序）

### 🟢 高价值 + 低成本（这周末可做）

| # | 借鉴点 | 工作量 | 接入位置 | 收益 |
|:-:|-------|:-----:|---------|------|
| 1 | **感知动词强制检定** | ~30 行 | `injector.py` 的 `_do_inject` 加一段 | 根治「翻一下/看看」被跳过 |
| 2 | **每轮工具调用后场景校验** | ~50 行 | 需要在工具层加 hook 或包一层 | 根治场景漂移 |
| 3 | **end_of_turn 自动同步** | ~30 行 | `tools.py` 包一层或扩展 `CombatTracker` | 自动推进时间/天气，省 AI 负担 |
| 4 | **三档模式配置** | ~40 行 | `config.py` + `state.py` | 不同场景适配 lite/标准/深度 |
| 5 | **反八股过滤** | ~80 行 | 仿 `combat_guard.py` 加个 `narrative_guard.py` | 减少「不是 X，是 Y」「血红的」「划破了寂静」等套话 |
| 6 | **感知动词扩到撬锁/说服/潜行** | ~20 行 | 复用 #1 的正则，扩展动词表 | 覆盖更多检定场景 |

### 🟡 中价值 + 中成本（1-2 个月）

| # | 借鉴点 | 工作量 | 接入位置 | 收益 |
|:-:|-------|:-----:|---------|------|
| 7 | **本地 TF-IDF/BM25 RAG** | ~370 行 | 新建 `retrieval/tfidf_bm25.py` | 零成本 fallback 检索（不依赖 OpenViking） |
| 8 | **多规则系统 CoT 提示词** | ~150 行 | `skills/` 扩 `coc-decision.md`、`dnd4e-decision.md` | COC 守密人语气更准 |
| 9 | **响应缓存** | ~30 行 | 包一层 LLM 调用 | 重复查询省 token |
| 10 | **决策建议剥离** | ~20 行 | 仿 `sanitize_narrative` | AI 输出更干净 |
| 11 | **规则系统 Skill 包架构** | 重构 | 仿 `skills/__init__.py` Skill 数据类 | 工具集 + prompt + 参数一起切 |
| 12 | **战斗可选一键结算** | 重构 | 新加 `trpg_combat_round` 工具 | 不破多步，但提供「懒人」选项 |

### 🔵 高价值 + 高成本（长期）

| # | 借鉴点 | 工作量 | 接入位置 | 收益 |
|:-:|-------|:-----:|---------|------|
| 13 | **剧本自动生成世界** | 大 | 新建 `adventure/auto_world.py` | 「导入文本 → 可玩世界」 |
| 14 | **Telegram/Discord 机器人前端** | 大 | 套壳 Hermes CLI | 解决 CLI 体验门槛 |
| 15 | **多用户支持** | 大 | 状态按用户隔离 | 多人多战役 |
| 16 | **SSE 流式输出** | 中 | 改造 LLM 调用层 | 实时流式，比 CLI 一坨吐出来体验好 |

---

## 六、关键代码引用（便于直接抄）

### 6.1 感知动词正则（`dm_agent.py:2178-2183`）

```python
PERCEPTION_VERBS = (
    r'观察|聆听|嗅\b|摸\b|翻找|侦查|张望|偷看|检查|搜索|细看|'
    r'倾听|嗅探|听\b|看\b|闻\b|瞄\b|扫\b|端详|打量'
)
SKILL_VERBS = PERCEPTION_VERBS + (
    r'|撬|锁|爬|攀|跳|跃|潜|行|偷|说服|欺|骗|演|讲|威|吓|游|说|交|涉|'
    r'搜|寻|翻|找|挖|撬|砸|砍|劈|推|拉|拖|举|抬|扛|背'
)
# 接入 injector.py:
if re.search(PERCEPTION_VERBS, user_message):
    sections.insert(0, {
        "priority": -1, "name": "感知检定强制",
        "content": "[系统提醒] 玩家进行感知行为，必须先调用 trpg_check(WIS/Perception)。",
        "max_ratio": 0.05,
    })
```

### 6.2 场景校验文本（`dm_agent.py:2214-2225`）

```python
# 接入 transform_llm_output 钩子（每个工具调用后执行）
state = self.state_mgr.get()
scene = state.get("scene", {})
scene_check = (
    f"[系统校验] 当前位置: {scene.get('current_location', '?')} | "
    f"时间: {scene.get('current_time', '?')} | "
    f"天气: {scene.get('weather', '?')} | "
    f"在场NPC: {', '.join(scene.get('npcs_here', [])) or '无'}"
    f"\n叙事若改变以上任一项，必须先调 trpg_update_scene。"
)
```

### 6.3 反八股正则（`dm_agent.py:84-103`）

```python
CLICHE_PATTERNS = [
    r'不是(?!劈|砍|刺|砸|扫|挡|闪|撞|压|缴|射|挥|捅|斩|削|挑|格|拉|推|踹|踢|抓|咬|撕|掐)[^，。；,!.\n]{2,30}，而是',
    r'殊不知[^，。]{2,30}[，。]',
    r'然而[^，。]{0,5}他[^，。]{0,5}并不知道',
    r'一个[^，。]{0,10}从未[^，。]{0,10}过的',
    r'命运的齿轮[^，。]{0,15}转动',
    r'他[^，。]{0,10}永远[^，。]{0,10}不会[^，。]{0,10}知道',
    r'仿佛[^，。]{5,30}一般',
    r'宛如[^，。]{5,30}一般',
    r'空气中[^，。]{0,10}弥漫着[^，。]{0,10}的气息',
    r'一股[^，。]{2,10}的气息[^，。]{0,10}扑面而来',
    r'血红的[^，。；]{0,15}',
    r'划破了寂静',
    r'如同一[只个条头匹缕片][^，。]{3,25}',
]
```

### 6.4 TF-IDF 简化骨架（`knowledge_base.py:227-296`）

```python
def retrieve_local(self, query: str, chunks: list[str], top_k: int = 5) -> list[dict]:
    """纯本地零成本检索，可作为 OpenViking 之外的 fallback。"""
    import math, jieba
    from rank_bm25 import BM25Okapi

    def tokenize(t):
        cleaned = re.sub(r'\s+', '', t.lower())
        terms = [cleaned[i:i+2] for i in range(len(cleaned)-1)]
        terms.extend(w for w in jieba.cut(cleaned) if len(w.strip()) > 1)
        return terms

    q_terms = tokenize(query)
    corpus = [tokenize(c) for c in chunks]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(q_terms)
    idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [{"text": chunks[i], "score": float(scores[i])} for i in idx]
```

### 6.5 Skill 数据类（`skills/__init__.py:17-91`）

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    system_prompt: str | None
    tools: list[dict[str, Any]]
    max_tokens: int
    temperature: float
    history_rounds: int
    rag_top_k: int
    outline_limit: int
    summary_limit: int

DND5E_SKILL = Skill(
    id="dnd5e", name="D&D 5e", system_prompt=None,
    tools=TRPG_TOOLS, max_tokens=4096, temperature=0.9,
    history_rounds=10, rag_top_k=5, outline_limit=2000, summary_limit=600,
)
COC_SKILL = Skill(
    id="coc", name="COC 7e", system_prompt="COC",
    tools=[t for t in TRPG_TOOLS if t["name"] != "trpg_death_save"],
    max_tokens=4096, temperature=0.8, history_rounds=10,
    rag_top_k=5, outline_limit=2000, summary_limit=600,
)
```

---

## 七、我们不用借鉴的（已更好或不适合）

| TRPG-AI-DM 特性 | 我们的情况 | 结论 |
|----------------|----------|------|
| 单体 dm_agent.py 2334 行 | 我们是 3514 行 tools.py + 各业务模块拆分 | **保持现状** |
| SQLite 数据库 | 纯 JSON 文件 | **保持现状**（数据可控性 ⭐⭐⭐⭐⭐） |
| 前后端分离 Web 应用 | Hermes CLI | **保持现状**（CLI 是差异化优势） |
| 多用户支持 | 单人 | 暂不需要（多人是另一类问题） |
| 8 套反八股正则 | 我们没有 | 借鉴（轻量） |
| 完整 D&D 4e 规则 | 暂无 | 可选（要就抄 game_systems.py） |
| 角色卡官方纸面布局 | 自有角色卡 | **保持现状**（更自由） |

---

## 八、最终建议（决策树）

```
┌─ 这周末（≤2h）
│  ├─ 抄感知动词触发 → injector.py
│  ├─ 抄场景校验文本 → transform_llm_output 钩子
│  └─ 抄反八股正则 → narrative_guard.py
│
├─ 下个迭代（≤1d）
│  ├─ 抄end_of_turn自动同步 → state advance hook
│  ├─ 抄三档模式 → config.py
│  └─ 抄决策建议剥离 → narrative_guard
│
├─ 1-2 个月（中改）
│  ├─ 抄TF-IDF/BM25 → 新的 retriever_tfidf.py
│  ├─ 抄CoT提示词 → skills/coc-decision.md 等
│  └─ 抄Skill数据类 → skills/ 扩 dataclass
│
└─ 3+ 个月（大改）
   ├─ 抄剧本自动生成 → adventure/auto_world.py
   ├─ 加Telegram/Discord机器人
   └─ 战斗一键结算作为可选工具
```

**核心思路**：在「工程可靠性 + Hermes 生态」上保持领先，吸收「AI 不会编错」的三层防护思路，但**不学它的单体架构**（dm_agent.py 2334 行是反模式）和**不学它的 Web 化**（CLI 是差异化）。

**最重要的一句话**：TRPG-AI-DM 的真正价值不在它做了什么，而在**它把什么物理上不可能错**。我们要学的是「物理上不可能错」这个思路，不是它的具体代码。

---

*生成日期：2026-08-24*
*对比基线：worldbook v2.5 / TRPG-AI-DM latest*
