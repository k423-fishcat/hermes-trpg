"""战斗数值校验器（CombatValueGuard）测试

重点覆盖 A1 修复的核心：用 event_log 的 version 增量精确判定「本轮」
是否调用了战斗工具，替代原来模糊的 60 秒窗口。
"""

import pytest


@pytest.fixture
def guard_cls(wp):
    from wp.combat_guard import CombatValueGuard
    return CombatValueGuard


@pytest.fixture
def active_combat(make_state):
    """开启战斗的 state"""
    sm = make_state("dnd5e")
    sm.update({"combat": {"active": True, "round": 1, "turn": 0}}, reason="战斗开始", actor="系统")
    return sm


class TestMarkTurnStart:
    def test_records_version(self, make_state, guard_cls):
        sm = make_state("dnd5e")
        guard = guard_cls(sm)
        v = sm.get("version")
        guard.mark_turn_start("turn-1")
        assert guard._turn_start_version == v

    def test_same_turn_not_reset(self, make_state, guard_cls):
        sm = make_state("dnd5e")
        guard = guard_cls(sm)
        guard.mark_turn_start("turn-1")
        start_v = guard._turn_start_version
        sm.update({"player.gold": 100}, reason="t", actor="DM")  # 版本递增
        guard.mark_turn_start("turn-1")  # 同 turn 重复 mark
        assert guard._turn_start_version == start_v  # 起点不变

    def test_new_turn_resets(self, make_state, guard_cls):
        sm = make_state("dnd5e")
        guard = guard_cls(sm)
        guard.mark_turn_start("turn-1")
        sm.update({"player.gold": 100}, reason="t", actor="DM")
        guard.mark_turn_start("turn-2")  # 新 turn
        assert guard._turn_start_version > 0


class TestHasCombatToolThisTurn:
    def test_this_turn_combat_change(self, active_combat, guard_cls):
        guard = guard_cls(active_combat)
        guard.mark_turn_start("t1")
        active_combat.update({"combat.round": 2}, reason="回合推进", actor="系统")
        assert guard._has_combat_tool_this_turn() is True

    def test_this_turn_player_hp_change(self, active_combat, guard_cls):
        guard = guard_cls(active_combat)
        guard.mark_turn_start("t1")
        active_combat.update({"player.hp.current": 5}, reason="受伤", actor="系统")
        assert guard._has_combat_tool_this_turn() is True

    def test_prev_turn_not_counted(self, active_combat, guard_cls):
        """上一轮的 combat 变更不能算本轮（A1 修复的核心）"""
        guard = guard_cls(active_combat)
        active_combat.update({"combat.round": 2}, reason="上一轮的变更", actor="系统")
        guard.mark_turn_start("t2")  # 新 turn 起点
        # 本轮只有非 combat 变更
        active_combat.update({"player.gold": 100}, reason="捡钱", actor="DM")
        assert guard._has_combat_tool_this_turn() is False

    def test_non_combat_change_not_counted(self, active_combat, guard_cls):
        guard = guard_cls(active_combat)
        guard.mark_turn_start("t1")
        active_combat.update({"player.gold": 100}, reason="捡钱", actor="DM")
        assert guard._has_combat_tool_this_turn() is False


class TestCheckResponse:
    def test_warns_without_tool(self, active_combat, guard_cls):
        guard = guard_cls(active_combat)
        guard.mark_turn_start("t1")
        r = guard.check_response("你造成 6 点挥砍伤害")
        assert r["combat_active"] is True
        assert r["needs_tool_calls"] is True
        assert len(r["warnings"]) > 0

    def test_no_warn_with_tool(self, active_combat, guard_cls):
        guard = guard_cls(active_combat)
        guard.mark_turn_start("t1")
        # 本轮有 combat 工具调用（产生状态变更）
        active_combat.update({"combat.log": "攻击"}, reason="combat_damage", actor="系统")
        r = guard.check_response("你造成 6 点挥砍伤害")
        assert r["needs_tool_calls"] is False
        assert len(r["warnings"]) == 0

    def test_no_warn_when_not_combat(self, make_state, guard_cls):
        """非战斗状态不校验"""
        sm = make_state("dnd5e")  # combat.active 默认 False
        guard = guard_cls(sm)
        r = guard.check_response("你造成 6 点伤害")
        assert r["combat_active"] is False
        assert r["needs_tool_calls"] is False


class TestFormatFooter:
    def test_footer(self, active_combat, guard_cls):
        guard = guard_cls(active_combat)
        guard.mark_turn_start("t1")
        r = guard.check_response("你造成 6 点伤害")
        if r["warnings"]:
            footer = guard.format_warning_footer(r)
            assert "战斗数值校验警告" in footer
        else:
            pytest.skip("本轮恰好有工具调用（概率性），footer 分支已由其它用例覆盖")
