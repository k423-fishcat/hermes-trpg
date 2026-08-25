"""检定引擎测试：D&D 5e / D&D 3r / COC 7e 三系统"""

import pytest


def _set_abilities(sm, template, abilities):
    if template == "coc7e":
        sm.update({"characteristics": abilities}, reason="test", actor="DM")
    else:
        sm.update({"player.abilities": abilities}, reason="test", actor="DM")


@pytest.fixture
def check(wp):
    from wp import check_engine
    return check_engine


class TestDnD5eCheck:
    def test_skill_check_success(self, make_state, check):
        sm = make_state("dnd5e")
        _set_abilities(sm, "dnd5e", {"str": 16, "dex": 14, "con": 10, "int": 10, "wis": 10, "cha": 10})
        sm.update({"player.proficiency_bonus": 3, "player.skills": {"运动": True}}, reason="t", actor="DM")
        r = check.roll_check(sm, check_type="skill", check_name="运动", dc=15, description="翻墙")
        assert r["type"] == "skill"
        assert r["system"] != "coc7e"  # 走 D&D 路径
        assert r["ability_mod"] == 3  # STR 16 → +3
        assert r["proficiency_bonus"] == 3  # 熟练
        # 加值 = 3(属性) + 3(熟练) + 0 = 6
        assert r["total_bonus"] == 6
        assert r["result"] in ("crit_success", "success", "fail", "crit_fail")
        assert 1 <= r["natural_roll"] <= 20

    def test_result_correctness(self, make_state, check):
        sm = make_state("dnd5e")
        _set_abilities(sm, "dnd5e", {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10})
        r = check.roll_check(sm, check_type="ability", check_name="str", dc=25, description="t")
        # 确定性断言（不依赖掷骰结果，避免自然20随机触发 crit_success）
        assert r["total"] == r["natural_roll"]   # 无加值时 total == natural_roll
        assert r["total_bonus"] == 0
        assert r["result"] in ("success", "fail", "crit_success", "crit_fail")

    def test_death_save(self, make_state, check):
        sm = make_state("dnd5e")
        r = check.roll_check(sm, check_type="death", check_name="死亡豁免", dc=10, description="t")
        assert r["type"] == "death"


class TestDnD3rCheck:
    def test_skill_check_with_ranks(self, make_state, check):
        sm = make_state("dnd3r")
        _set_abilities(sm, "dnd3r", {"str": 16, "dex": 14, "con": 10, "int": 10, "wis": 10, "cha": 10})
        sm.update({"player.skills": {"运动": {"ranks": 4, "class_skill": True}}}, reason="t", actor="DM")
        r = check.roll_check(sm, check_type="skill", check_name="运动", dc=15, description="翻墙")
        # 加值 = STR+3(16) + 4(ranks) = 7
        assert r["total_bonus"] == 7

    def test_cross_class_halves_ranks(self, make_state, check):
        sm = make_state("dnd3r")
        _set_abilities(sm, "dnd3r", {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10})
        sm.update({"player.skills": {"运动": {"ranks": 4, "class_skill": False}}}, reason="t", actor="DM")
        r = check.roll_check(sm, check_type="skill", check_name="运动", dc=15, description="t")
        # 跨职业 4/2=2 点
        assert r["total_bonus"] == 2


class TestCocCheck:
    def test_skill_check_d100(self, make_state, check):
        sm = make_state("coc7e")
        _set_abilities(sm, "coc7e", {"str": 60, "con": 50, "siz": 65, "dex": 70, "int": 80, "pow": 50, "edu": 75})
        sm.update({"skills": {"侦查": 65, "图书馆": 50}}, reason="t", actor="DM")
        r = check.roll_check(sm, check_type="skill", check_name="侦查", description="寻找线索")
        assert r["system"] == "coc7e"
        assert r["skill_value"] == 65
        assert 1 <= r["roll"] <= 100
        # 骰值<=技能 → 成功
        assert r["success"] == (r["roll"] <= 65)

    def test_low_skill_fails_more(self, make_state, check):
        sm = make_state("coc7e")
        _set_abilities(sm, "coc7e", {"str": 60, "con": 50, "siz": 65, "dex": 70, "int": 80, "pow": 50, "edu": 75})
        sm.update({"skills": {"说服": 10}}, reason="t", actor="DM")
        r = check.roll_check(sm, check_type="skill", check_name="说服", description="t")
        assert r["skill_value"] == 10
        assert r["success"] == (r["roll"] <= 10)


class TestFormatDispatch:
    def test_coc_format(self, make_state, check):
        sm = make_state("coc7e")
        _set_abilities(sm, "coc7e", {"str": 60, "con": 50, "siz": 65, "dex": 70, "int": 80, "pow": 50, "edu": 75})
        sm.update({"skills": {"侦查": 65}}, reason="t", actor="DM")
        r = check.roll_check(sm, check_type="skill", check_name="侦查", description="t")
        out = check.format_check_result(r)
        assert "侦查" in out

    def test_dnd_format(self, make_state, check):
        sm = make_state("dnd5e")
        _set_abilities(sm, "dnd5e", {"str": 16, "dex": 14, "con": 10, "int": 10, "wis": 10, "cha": 10})
        r = check.roll_check(sm, check_type="skill", check_name="运动", dc=15, description="t")
        out = check.format_check_result(r)
        assert "运动" in out
        assert "DC" in out
