"""遭遇管理器测试：战斗遭遇能正确实例化怪物（修复 monster_data_list 格式 bug）"""

import pytest


@pytest.fixture
def bestiary_with_goblin(wp, data_dir):
    from wp.bestiary import Bestiary
    b = Bestiary(data_dir)
    b.add_monster({
        "id": "goblin",
        "name": "哥布林",
        "stats": {"hp_average": 7, "ac": 15, "speed": 30},
        "abilities": {"str": 8, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 8},
    })
    return b


@pytest.fixture
def encounter_mgr(make_state, bestiary_with_goblin, wp):
    from wp.encounters import EncounterManager
    from wp.combat import CombatTracker
    sm = make_state("dnd5e")
    ct = CombatTracker(sm, bestiary_with_goblin)
    mgr = EncounterManager(sm, combat_tracker=ct, bestiary=bestiary_with_goblin)
    mgr.add_encounter(
        "fight1", "酒馆冲突", encounter_type="combat", location="酒馆",
        creatures=[{"ref": "goblin", "name": "哥布林", "count": 2}],
    )
    return mgr


class TestCombatEncounter:
    def test_start_instantiates_monsters(self, encounter_mgr):
        """战斗遭遇启动后，怪物被正确实例化（不再 0 只）"""
        r = encounter_mgr.start_encounter("fight1")
        assert r["success"] is True
        assert r["creatures_count"] == 2  # 2 只哥布林

    def test_combat_state_has_creatures(self, encounter_mgr):
        encounter_mgr.start_encounter("fight1")
        combat = encounter_mgr.state.get("combat")
        assert combat["active"] is True
        assert len(combat["creatures"]) == 2  # 战斗里有 2 个实例

    def test_inline_stats_without_bestiary(self, make_state, wp):
        """无 bestiary 但有内联 stats，也能实例化"""
        from wp.encounters import EncounterManager
        from wp.combat import CombatTracker
        sm = make_state("dnd5e")
        ct = CombatTracker(sm, None)  # 无 bestiary
        mgr = EncounterManager(sm, combat_tracker=ct, bestiary=None)
        mgr.add_encounter(
            "fight2", "野狗", encounter_type="combat",
            creatures=[{"ref": "dog", "name": "野狗", "count": 1,
                        "stats": {"hp_average": 5, "ac": 12}}],
        )
        r = mgr.start_encounter("fight2")
        assert r["success"] is True
        assert r["creatures_count"] == 1

    def test_unresolvable_creature_fails(self, make_state, wp):
        """ref 查不到且无 stats → 明确失败，不启动空战斗"""
        from wp.encounters import EncounterManager
        from wp.combat import CombatTracker
        sm = make_state("dnd5e")
        ct = CombatTracker(sm, None)
        mgr = EncounterManager(sm, combat_tracker=ct, bestiary=None)
        mgr.add_encounter(
            "fight3", "未知", encounter_type="combat",
            creatures=[{"ref": "nonexistent", "name": "未知生物", "count": 1}],
        )
        r = mgr.start_encounter("fight3")
        assert r["success"] is False
        assert "无法实例化" in r.get("error", "")


class TestNonCombatEncounter:
    def test_social_encounter(self, encounter_mgr):
        mgr = encounter_mgr
        mgr.add_encounter(
            "talk1", "酒馆打听", encounter_type="social",
            dc_info={"游说": 12}, rewards="线索",
        )
        r = mgr.start_encounter("talk1")
        assert r["success"] is True
        assert r["type"] == "social"
        assert r["dc_info"]["游说"] == 12
