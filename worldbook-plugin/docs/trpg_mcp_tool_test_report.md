# TRPG MCP 工具测试报告

测试时间：2026-08-26
测试环境：Hermes worldbook 插件 (E:/CodeTools/hermes/plugins/worldbook/)
测试范围：模组管理 + 世界书 + 遭遇 + 记忆层

## 测试结果汇总表

| # | 工具名 | 调用参数 | 是否成功 | 返回结果摘要 | 备注 |
|---|--------|----------|----------|-------------|------|
| 1 | trpg_module_list | (无参数) | ❌ 失败 | TypeError: register.<locals>.list_modules() got an unexpected keyword argument 'task_id' | 所有工具存在相同根因 |
| 2 | trpg_encounter_list | (无参数) | ❌ 失败 | TypeError: register.<locals>.list_enc() got an unexpected keyword argument 'task_id' | 同上 |
| 3 | trpg_monster_list | (无参数) | ❌ 失败 | TypeError: register.<locals>.list_m() got an unexpected keyword argument 'task_id' | 工具实际名为 trpg_monster_list，非 trpg_bestiary_list |
| 4 | trpg_monster_get | monster_id="goblin" | ❌ 失败 | TypeError: register.<locals>.get_m() got an unexpected keyword argument 'task_id' | 工具实际名为 trpg_monster_get，非 trpg_bestiary_get |
| 5 | trpg_snapshot_list | (无参数) | ❌ 失败 | TypeError: register.<locals>.list_snaps() got an unexpected keyword argument 'task_id' | 同上 |
| 6 | trpg_snapshot_save | name="test_snapshot_001", reason="MCP tool availability test" | ❌ 失败 | TypeError: register.<locals>.save() got an unexpected keyword argument 'task_id' | 同上 |
| 7 | trpg_session_recap | sessions_back=1 | ❌ 失败 | TypeError: register.<locals>.recap() got an unexpected keyword argument 'task_id' | 同上 |
| 8 | trpg_milestone_list | N/A | ⚠️ 不存在 | 工具列表中无 trpg_milestone_list | 只有 trpg_milestone_add 和 trpg_milestone_update；可能需要通过 trpg_chapter_review 获取里程碑列表 |
| 9 | trpg_choice_timeline | (无参数) | ❌ 失败 | TypeError: register.<locals>.timeline() got an unexpected keyword argument 'task_id' | 工具实际名为 trpg_choice_timeline，非 trpg_choice_list |
| 10 | trpg_milestone_add | title="Test Milestone", description="Testing milestone add tool", milestone_type="objective" | ❌ 失败 | TypeError: register.<locals>.add_milestone() got an unexpected keyword argument 'task_id' | 额外测试：验证所有 trpg 工具均受影响 |

## 根因分析

**核心 Bug：ToolRegistry 中 handler 函数签名不兼容 Hermes MCP 框架**

- Hermes 框架调用工具 handler 时会传递 `task_id`、`session_id`、`tool_name` 等系统关键字参数
- worldbook 插件的 `ToolRegistry.tool()` 装饰器注册的 handler 函数签名均为 `def xxx(args):`，只接受一个位置参数（参数字典）
- 框架以 kwargs 方式调用时，`task_id` 等参数无法被接收，触发 `TypeError: unexpected keyword argument 'task_id'`
- 影响范围：**全部 ~76 个 trpg_* MCP 工具** 均受此问题影响

## 修复状态

✅ **修复代码已写入磁盘**（`E:/CodeTools/hermes/plugins/worldbook/tools/registry.py` 第 73-96 行）

修复方案：在 `register_all()` 方法中为每个 handler 包一层适配函数，支持两种调用方式：
1. 位置参数调用：`handler(args_dict)`（测试/内部调用）
2. 关键字参数调用：`handler(**kwargs)`（Hermes MCP 调用）—— 自动过滤掉 `task_id`/`session_id`/`tool_name` 等系统参数

⚠️ **注意**：当前运行中的 Hermes 进程加载的是修复前的旧代码，需要重启 Hermes 后修复才能生效。

## 命名差异说明

任务中提到的工具名与实际工具名存在差异：
- `trpg_bestiary_list` → 实际为 `trpg_monster_list`
- `trpg_bestiary_get` → 实际为 `trpg_monster_get`
- `trpg_choice_list` → 实际为 `trpg_choice_timeline`
- `trpg_milestone_list` → **不存在**（只有 `trpg_milestone_add` / `trpg_milestone_update`，里程碑列表可能通过 `trpg_chapter_review` 获取）
