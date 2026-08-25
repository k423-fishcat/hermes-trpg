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
    reset_app()
    app = get_app()
    yield app
    reset_app()


class TestRegistration:
    def test_all_tools_registered(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        n = register_all_tools(ctx, isolated_app)
        assert n == 74
        assert len(ctx.tools) == 74

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
            "trpg_log_event", "trpg_quest_list", "trpg_milestone_add",
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

    def test_invalid_args_handled(self, isolated_app):
        from wp.tools import register_all_tools
        ctx = FakeCtx()
        register_all_tools(ctx, isolated_app)
        # 缺参调用不应崩
        r = ctx.tools["trpg_combat_damage"]["handler"]({})
        assert isinstance(r, str)
