# hermes-trpg

> A D&D 5e AI Dungeon Master plugin for Hermes Agent.
> 基于 Hermes Agent 的 D&D 5e AI 地牢主脑插件。

A single-player / small-group tabletop RPG system where an LLM acts as the
Dungeon Master, with state tracking, combat resolution, and a rules engine
backed by D&D 5e SRD (2014 + 2024 editions).

## Features

- 🎲 **检定引擎**：d20 / d100 多系统检定（5e/3r/COC 7e 模板）
- ⚔️ **战斗追踪**：回合管理 + 数值硬校验（combat guard）
- 📜 **本地规则书快照**：Open5e SRD 离线缓存（2014/2024 双版本）
- 🗣️ **中文翻译**：核心规则、怪物、法术、物品中英对照（覆盖 100% 法术/子职）
- 🔌 **MCP 工具**：约 77 个 `trpg_*` 工具（角色/法术/战斗/世界书/叙事）
- 💾 **状态原子写入**：JSON + Schema 校验 + 快照回滚
- 🧪 **221 个测试覆盖核心逻辑**

## 项目结构

```
hermes-trpg/
├── worldbook-plugin/          核心 Hermes 插件
│   ├── __init__.py            插件入口（注册钩子/命令/工具）
│   ├── state.py               状态管理（原子写入 + 快照 + Schema校验）
│   ├── check_engine.py        检定引擎（d20/d100 多系统）
│   ├── combat.py              战斗追踪
│   ├── spells.py              法术系统
│   ├── rules/                 本地规则书 + Open5e 同步
│   │   ├── builtin/dnd5e/2024/  SRD 2024 快照
│   │   ├── builtin/dnd5e/2014/  SRD 2014 快照
│   │   └── zh_mapping.json    中文名映射表
│   ├── adapter/               适配器层（pre_llm_call 等钩子）
│   ├── data/                  玩家数据（gitignore，不推）
│   ├── tests/                 pytest 套件（221 个测试）
│   └── docs/                  设计文档
│       └── 原理/              核心模块原理
└── LICENSE                    MIT
```

## 快速开始

### 部署到 Hermes

```bash
# 1. 克隆
git clone <repo-url> hermes-trpg
cd hermes-trpg

# 2. 复制到 Hermes 插件目录
cp -r worldbook-plugin/* /path/to/hermes/plugins/worldbook/

# 3. 启动 Hermes，系统自动加载 worldbook 插件
```

### 开发测试

```bash
cd worldbook-plugin/tests
python -m pytest          # 跑 221 个测试
```

## 版本

- 当前：**v2.10**
- 工具数：约 77 个 `trpg_*` MCP 工具
- 代码量：约 15,000 行 Python
- 测试：221 passed

## 文档

深入设计文档在 `worldbook-plugin/docs/原理/`：
- `11-多规则系统.md` — D&D 5e / 3.5 / COC 7e 模板路由
- 多规则系统、中文翻译、规则快照等专题

## License

MIT — see [LICENSE](LICENSE).

游戏规则数据来自 [Open5e API](https://api.open5e.com/)，基于
[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/) 授权。
