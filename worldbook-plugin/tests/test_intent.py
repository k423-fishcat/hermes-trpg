"""Intent Detector 测试（D&D 5e）"""

import pytest


@pytest.fixture(scope="module")
def intent(wp):
    from wp import intent
    intent.clear_cache()
    yield intent
    intent.clear_cache()


class TestStrongTrigger:
    def test_perception_search(self, intent):
        out = intent.detect_intent("我搜索这个房间")
        assert "Perception" in out
        assert "trpg_check" in out
        assert "必须" in out  # 强触发

    def test_investigation(self, intent):
        out = intent.detect_intent("我调查地上的脚印")
        assert "Investigation" in out
        assert "trpg_check" in out

    def test_stealth(self, intent):
        out = intent.detect_intent("我悄悄潜行过去")
        assert "Stealth" in out

    def test_sleight_of_hand_lock(self, intent):
        out = intent.detect_intent("我撬开这把锁")
        assert "Sleight of Hand" in out

    def test_athletics_door(self, intent):
        out = intent.detect_intent("我撞开这扇门")
        assert "Athletics" in out

    def test_persuasion(self, intent):
        out = intent.detect_intent("我说服守卫放我们进去")
        assert "Persuasion" in out


class TestWeakTrigger:
    def test_casual_look(self, intent):
        """弱触发：不强制检定，只提示判断"""
        out = intent.detect_intent("我看了一眼地图")
        assert "判断" in out
        assert "必须" not in out  # 弱触发不强检

    def test_strong_overrides_weak(self, intent):
        """同技能强触发命中时，不再注入弱触发"""
        out = intent.detect_intent("我搜索并查看房间")
        assert out.count("Perception") == 1  # 只注入一次（强）
        assert "必须" in out


class TestNoTrigger:
    def test_greeting(self, intent):
        assert intent.detect_intent("我打个招呼") == ""

    def test_weather(self, intent):
        assert intent.detect_intent("今天天气不错") == ""

    def test_empty(self, intent):
        assert intent.detect_intent("") == ""
        assert intent.detect_intent("   ") == ""

    def test_non_5e_system(self, intent):
        # coc7e 规则表未实现，返回空
        assert intent.detect_intent("我搜索房间", template_name="coc7e") == ""


class TestEventDetail:
    def test_events_list(self, intent):
        events = intent.get_events("我搜索房间")
        assert len(events) >= 1
        assert events[0].type == "skill_check"
        assert events[0].rule == "Perception"
        assert events[0].tool == "trpg_check"

    def test_multi_trigger(self, intent):
        """一句话命中多个技能事件（都保留）"""
        events = intent.get_events("我搜索并调查房间")
        rules = {e.rule for e in events}
        assert "Perception" in rules
        assert "Investigation" in rules


class TestHardTrigger:
    def test_attack(self, intent):
        out = intent.detect_intent("我挥剑攻击守卫")
        assert "trpg_combat_damage" in out
        events = intent.get_events("我挥剑攻击守卫")
        assert any(e.rule == "Attack" and e.type == "attack" for e in events)

    def test_initiative(self, intent):
        out = intent.detect_intent("我拔剑进入战斗")
        assert "trpg_combat_start" in out

    def test_spell(self, intent):
        out = intent.detect_intent("我施放火球术")
        assert "trpg_spell_cast" in out

    def test_short_rest(self, intent):
        out = intent.detect_intent("我坐下来短休一会")
        assert "trpg_short_rest" in out

    def test_long_rest(self, intent):
        out = intent.detect_intent("我扎营睡一觉")
        assert "trpg_long_rest" in out

    def test_loot(self, intent):
        out = intent.detect_intent("我摸尸搜刮战利品")
        assert "trpg_inventory_add" in out
        events = intent.get_events("我摸尸搜刮战利品")
        assert any(e.rule == "Loot" and e.type == "loot" for e in events)

    def test_combat_sequence(self, intent):
        """组合触发：潜行偷袭守卫 → Stealth → Initiative → Attack（顺序）"""
        events = intent.get_events("我潜行过去偷袭守卫")
        types = [e.type for e in events]
        assert "skill_check" in types  # 潜行检定
        assert "initiative" in types   # 进入先攻
        assert "attack" in types       # 攻击
        # 顺序断言：skill_check 在 initiative 前，initiative 在 attack 前
        assert types.index("skill_check") < types.index("initiative") < types.index("attack")

    def test_loot_after_combat(self, intent):
        """搜刮尸体通常滞后于战斗"""
        events = intent.get_events("我击败守卫后摸尸")
        types = [e.type for e in events]
        assert "loot" in types
