"""工具注册与 handler 测试"""

import pytest


class FakeCtx:
    """模拟 PluginContext（只收集 register_tool 的名字）"""

    def __init__(self):
        self.tools = {}

    def register_tool(self, **kw):
        self.tools[kw["name"]] = {
            "handler": kw["handler"],
            "schema": kw["schema"],
            "description": kw.get("description", ""),
            "emoji": kw.get("emoji", ""),
        }


@pytest.fixture
def isolated_app(patched_data_dir):
    """隔离 data 目录的 AppContext（每个测试重建）"""
    from wp.app_context import get_app, reset_app
    from wp.state import reset_default_state_mgr
    reset_app()
    reset_default_state_mgr()
    app = get_app()
    yield app
    reset_app()
    reset_default_state_mgr()


class TestRegistration:
    def test_all_tools_registered(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        n = register_all_tools(ctx, isolated_app)
        assert n == 78
        assert len(ctx.tools) == 78

    def test_key_tools_present(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        for name in [
            "trpg_state_get", "trpg_state_update",
            "trpg_check", "trpg_combat_start", "trpg_combat_damage",
            "trpg_inventory_list", "trpg_spell_cast", "trpg_session_start",
            "trpg_snapshot_save", "trpg_time_advance", "trpg_npc_attitude_change",
            "trpg_monster_search", "trpg_module_list", "trpg_encounter_start",
            "trpg_short_rest", "trpg_char_status", "trpg_choice_add",
            "trpg_log_event", "trpg_quest_list", "trpg_quest_add",
            "trpg_milestone_add",
            "trpg_npc_list", "trpg_chapter_list", "trpg_worldbook_search",
        ]:
            assert name in ctx.tools, f"缺少工具: {name}"

    def test_no_duplicate_names(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        assert len(ctx.tools) == len(set(ctx.tools.keys()))  # 无重名


class TestHandlerCalls:
    def test_state_get(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_state_get"]["handler"]({"path": "template"})
        assert "dnd5e" in r or r  # 返回当前模板名或摘要

    def test_state_get_overview(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        # 空 path 应返回总览，而不是报错
        r = ctx.tools["trpg_state_get"]["handler"]({})
        assert "📊 角色状态" in r
        assert "版本:" in r

    def test_state_update(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_state_update"]["handler"](
            {"changes": {"player.hp.current": 25}, "reason": "test"})
        assert "状态更新" in r

    def test_check_handler(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_check"]["handler"](
            {"check_name": "运动", "dc": 15, "description": "翻墙"})
        assert "检定" in r or "运动" in r

    def test_time_now(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_time_now"]["handler"]({})
        assert r  # 非空时间输出

    def test_snapshot_save(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_snapshot_save"]["handler"]({"name": "test_snap"})
        assert "快照" in r

    def test_quest_add(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        h = ctx.tools["trpg_quest_add"]["handler"]

        # 基础创建
        r = h({"quest_id": "side_test_01", "title": "测试任务"})
        assert "任务已创建" in r
        assert "side_test_01" in r

        # 带步骤 / 前置 / 触发器
        r = h({
            "quest_id": "main_test_01",
            "title": "主线测试",
            "quest_type": "main",
            "steps": '[{"id":"s1","title":"找线索"}]',
            "prerequisites": '["side_test_01"]',
            "triggers": '[{"type":"flag","key":"met_king"}]',
        })
        assert "任务已创建" in r
        assert "main" in r

        # 重复创建应失败
        r = h({"quest_id": "side_test_01", "title": "重复任务"})
        assert "❌" in r

        # 非法 JSON 应失败
        r = h({"quest_id": "bad_01", "title": "坏任务", "steps": "not json"})
        assert "❌" in r
        assert "JSON" in r

    def test_combat_start_missing_monster_warns(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_combat_start"]["handler"]({
            "name": "测试遭遇",
            "player_initiative": 15,
            "monsters": [{"monster_id": "不存在的怪物", "count": 2}],
        })
        assert "战斗开始" in r
        assert "未在图鉴中找到" in r
        assert "不存在的怪物" in r
        assert "共 0 只怪物" in r

    def test_monster_search_chinese(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        h = ctx.tools["trpg_monster_search"]["handler"]
        r = h({"query": "哥布林"})
        assert "goblin" in r or "哥布林" in r

    def test_hermes_kwargs_compatible(self, isolated_app):
        """Hermes 调用工具时会传 task_id 等系统 kwargs，handler 必须兼容"""
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_state_get"]["handler"]({"path": "template"}, task_id="t1", session_id="s1")
        assert isinstance(r, str)
        r = ctx.tools["trpg_check"]["handler"](
            {"check_name": "运动", "dc": 15}, task_id="t2")
        assert isinstance(r, str)

    def test_invalid_args_handled(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        # 缺参调用不应崩
        r = ctx.tools["trpg_combat_damage"]["handler"]({})
        assert isinstance(r, str)

    def test_npc_list_handler(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_npc_list"]["handler"]({})
        assert isinstance(r, str) and "NPC" in r

    def test_chapter_list_handler(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_chapter_list"]["handler"]({})
        assert isinstance(r, str)

    def test_worldbook_search_handler(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        r = ctx.tools["trpg_worldbook_search"]["handler"]({"query": "测试"})
        assert isinstance(r, str)
