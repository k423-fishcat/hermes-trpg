"""D&D 5e 规则书审计修复测试

覆盖：
1. combat.py damage_vulnerabilities（易伤）支持
2. combat.py critical hit（暴击）支持
3. inventory.py attunement cap of 3
4. rest.py 0 HP 检查（短/长休）
5. rest.py Warlock pact magic 短休恢复
6. rest.py long rest exhaustion 减少
"""

import pytest


def _wp():
    """Helper to access wp package - call inside test"""
    from tests.conftest import PLUGIN_DIR
    import sys
    if "wp" not in sys.modules:
        from conftest import _load_wp
        _load_wp()
    return sys.modules["wp"]


# ============================================================
# combat.py: 伤害易伤（damage_vulnerabilities）
# ============================================================

class TestDamageVulnerability:
    def test_vulnerability_doubles_damage(self, make_state, wp):
        from wp.combat import CombatTracker
        from wp.bestiary import Bestiary
        from pathlib import Path

        # 创建一个易伤火焰的怪物模板
        data_dir = Path(make_state.__self__.data_dir if hasattr(make_state, '__self__') else make_state.__class__.__name__)
        # 改用：直接在内存创建 bestiary
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmp:
            bestiary = Bestiary(Path(tmp))
            bestiary.add_monster({
                "id": "fire_vuln",
                "name": "火焰易伤怪",
                "stats": {"hp_average": 30, "ac": 12, "speed": 30},
                "abilities": {"str": 10, "dex": 10, "con": 10, "int": 1, "wis": 1, "cha": 1},
                "damage_vulnerabilities": ["fire"],
                "damage_resistances": [],
                "damage_immunities": [],
                "attacks": [],
            })

            sm = make_state("dnd5e", campaign="vuln_test")
            combat = CombatTracker(sm, bestiary=bestiary)
            result = combat.start_combat(
                name="vuln_test",
                monsters=[{"monster_id": "fire_vuln", "count": 1, "display_prefix": "易伤怪", "initiative_bonus": 0}],
            )
            assert result["success"]

            # 找怪物的 ref
            combat_state = sm.get("combat")
            ref = list(combat_state["creatures"].keys())[0]

            # 火焰伤害 10 点，易伤应翻倍到 20
            dmg = combat.damage_creature(ref, 10, damage_type="fire", source="test")
            assert dmg["success"] is True
            assert dmg["vulnerabilities_applied"] == 1
            assert dmg["initial_damage"] == 10
            # HP: 30 - 20 = 10
            assert dmg["hp_current"] == 10

    def test_resistance_halves_damage(self, make_state, wp):
        from wp.combat import CombatTracker
        from wp.bestiary import Bestiary
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bestiary = Bestiary(Path(tmp))
            bestiary.add_monster({
                "id": "fire_resist",
                "name": "火焰抗性怪",
                "stats": {"hp_average": 30, "ac": 12, "speed": 30},
                "abilities": {"str": 10, "dex": 10, "con": 10, "int": 1, "wis": 1, "cha": 1},
                "damage_vulnerabilities": [],
                "damage_resistances": ["fire"],
                "damage_immunities": [],
                "attacks": [],
            })

            sm = make_state("dnd5e", campaign="resist_test")
            combat = CombatTracker(sm, bestiary=bestiary)
            result = combat.start_combat(
                name="resist_test",
                monsters=[{"monster_id": "fire_resist", "count": 1, "display_prefix": "抗性怪", "initiative_bonus": 0}],
            )
            assert result["success"]
            ref = list(sm.get("combat")["creatures"].keys())[0]

            # 火焰伤害 10 点，抗性减半到 5
            dmg = combat.damage_creature(ref, 10, damage_type="fire", source="test")
            assert dmg["resistances_applied"] == 1
            assert dmg["hp_current"] == 25  # 30 - 5

    def test_immunity_zeroes_damage(self, make_state, wp):
        from wp.combat import CombatTracker
        from wp.bestiary import Bestiary
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bestiary = Bestiary(Path(tmp))
            bestiary.add_monster({
                "id": "fire_immune",
                "name": "火焰免疫怪",
                "stats": {"hp_average": 30, "ac": 12, "speed": 30},
                "abilities": {"str": 10, "dex": 10, "con": 10, "int": 1, "wis": 1, "cha": 1},
                "damage_vulnerabilities": [],
                "damage_resistances": [],
                "damage_immunities": ["fire"],
                "attacks": [],
            })

            sm = make_state("dnd5e", campaign="immune_test")
            combat = CombatTracker(sm, bestiary=bestiary)
            result = combat.start_combat(
                name="immune_test",
                monsters=[{"monster_id": "fire_immune", "count": 1, "display_prefix": "免疫怪", "initiative_bonus": 0}],
            )
            assert result["success"]
            ref = list(sm.get("combat")["creatures"].keys())[0]

            # 火焰免疫：0 伤害
            dmg = combat.damage_creature(ref, 10, damage_type="fire", source="test")
            assert dmg["immunities_applied"] == 1
            assert dmg["hp_current"] == 30  # 没扣血

    def test_no_match_normal_damage(self, make_state, wp):
        """无抗/免/易伤：正常伤害"""
        from wp.combat import CombatTracker
        from wp.bestiary import Bestiary
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bestiary = Bestiary(Path(tmp))
            bestiary.add_monster({
                "id": "normal",
                "name": "普通怪",
                "stats": {"hp_average": 30, "ac": 12, "speed": 30},
                "abilities": {"str": 10, "dex": 10, "con": 10, "int": 1, "wis": 1, "cha": 1},
                "damage_vulnerabilities": [],
                "damage_resistances": [],
                "damage_immunities": [],
                "attacks": [],
            })

            sm = make_state("dnd5e", campaign="normal_test")
            combat = CombatTracker(sm, bestiary=bestiary)
            combat.start_combat(
                name="normal_test",
                monsters=[{"monster_id": "normal", "count": 1, "display_prefix": "怪", "initiative_bonus": 0}],
            )
            ref = list(sm.get("combat")["creatures"].keys())[0]

            dmg = combat.damage_creature(ref, 10, damage_type="fire", source="test")
            assert dmg["vulnerabilities_applied"] == 0
            assert dmg["resistances_applied"] == 0
            assert dmg["immunities_applied"] == 0
            assert dmg["hp_current"] == 20  # 30 - 10


# ============================================================
# combat.py: 暴击（critical hit）
# ============================================================

class TestCriticalHit:
    def test_critical_marked(self, make_state, wp):
        """暴击参数被正确记录到结果"""
        from wp.combat import CombatTracker
        from wp.bestiary import Bestiary
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bestiary = Bestiary(Path(tmp))
            bestiary.add_monster({
                "id": "target",
                "name": "靶子",
                "stats": {"hp_average": 50, "ac": 12, "speed": 30},
                "abilities": {"str": 10, "dex": 10, "con": 10, "int": 1, "wis": 1, "cha": 1},
                "attacks": [],
            })

            sm = make_state("dnd5e", campaign="crit_test")
            combat = CombatTracker(sm, bestiary=bestiary)
            combat.start_combat(
                name="crit_test",
                monsters=[{"monster_id": "target", "count": 1, "display_prefix": "靶子", "initiative_bonus": 0}],
            )
            ref = list(sm.get("combat")["creatures"].keys())[0]

            # 暴击伤害：调用方负责骰 2 倍（damage_creature 只是记录）
            dmg = combat.damage_creature(ref, 24, damage_type="slashing", source="剑", critical=True)
            assert dmg["critical"] is True
            assert "暴击" in "".join(dmg["calc_steps"])

    def test_critical_false_default(self, make_state, wp):
        """默认 critical=False"""
        from wp.combat import CombatTracker
        from wp.bestiary import Bestiary
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bestiary = Bestiary(Path(tmp))
            bestiary.add_monster({
                "id": "target",
                "name": "靶子",
                "stats": {"hp_average": 50, "ac": 12, "speed": 30},
                "abilities": {"str": 10, "dex": 10, "con": 10, "int": 1, "wis": 1, "cha": 1},
                "attacks": [],
            })

            sm = make_state("dnd5e", campaign="no_crit_test")
            combat = CombatTracker(sm, bestiary=bestiary)
            combat.start_combat(
                name="no_crit_test",
                monsters=[{"monster_id": "target", "count": 1, "display_prefix": "靶子", "initiative_bonus": 0}],
            )
            ref = list(sm.get("combat")["creatures"].keys())[0]

            dmg = combat.damage_creature(ref, 10, damage_type="slashing", source="剑")
            assert dmg["critical"] is False


# ============================================================
# inventory.py: 同调上限 3 件
# ============================================================

class TestAttunementCap:
    def _make_state_with_items(self, make_state, item_ids, attuned_flags):
        """建 state 并放入指定物品"""
        sm = make_state("dnd5e", campaign="attune_test")
        inv = []
        for iid, is_attuned in zip(item_ids, attuned_flags):
            inv.append({
                "id": iid,
                "name": iid,
                "type": "wondrous",
                "attunement_required": True,
                "attuned": is_attuned,
                "magical": True,
            })
        sm.update({"inventory": inv}, reason="test setup", actor="test")
        return sm

    def test_attune_first_item(self, make_state, wp):
        from wp.inventory import InventoryManager
        sm = self._make_state_with_items(make_state, ["item1"], [False])
        mgr = InventoryManager(sm)
        result = mgr.attune("item1")
        assert result["success"] is True
        assert result["attunement_count"] == 1

    def test_attune_cap_3_enforced(self, make_state, wp):
        """第 4 件同调应被拒绝"""
        from wp.inventory import InventoryManager
        sm = self._make_state_with_items(
            make_state,
            ["item1", "item2", "item3", "item4"],
            [True, True, True, False],  # 3 件已同调，第 4 件未同调
        )
        mgr = InventoryManager(sm)
        result = mgr.attune("item4")
        assert result["success"] is False
        assert "同调槽已满" in result["error"]
        assert result["attunement_count"] == 3

    def test_attune_already_attuned_fails(self, make_state, wp):
        from wp.inventory import InventoryManager
        sm = self._make_state_with_items(make_state, ["item1"], [True])
        mgr = InventoryManager(sm)
        result = mgr.attune("item1")
        assert result["success"] is False
        assert "已经同调" in result["error"]

    def test_unattune_frees_slot(self, make_state, wp):
        from wp.inventory import InventoryManager
        sm = self._make_state_with_items(
            make_state,
            ["item1", "item2", "item3", "item4"],
            [True, True, True, False],
        )
        mgr = InventoryManager(sm)
        # 解除 item1 后，attune item4 应成功
        mgr.unattune("item1")
        result = mgr.attune("item4")
        assert result["success"] is True
        assert result["attunement_count"] == 3

    def test_list_attuned(self, make_state, wp):
        from wp.inventory import InventoryManager
        sm = self._make_state_with_items(
            make_state,
            ["item1", "item2", "item3"],
            [True, True, False],
        )
        mgr = InventoryManager(sm)
        attuned = mgr.list_attuned()
        assert len(attuned) == 2
        ids = [i["id"] for i in attuned]
        assert "item1" in ids
        assert "item2" in ids
        assert "item3" not in ids


# ============================================================
# rest.py: 0 HP 不能休息
# ============================================================

class TestZeroHPRestRejected:
    def test_short_rest_zero_hp_rejected(self, make_state, wp):
        from wp.rest import RestManager
        sm = make_state("dnd5e", campaign="zero_hp_short")
        player = sm.get("player")
        player["hp"] = {"current": 0, "max": 20, "temp": 0}
        player["hit_dice"] = {"total": "3d8", "used": 0}
        sm.update({"player": player}, reason="test", actor="test")
        mgr = RestManager(sm)
        result = mgr.short_rest()
        assert result["success"] is False
        assert "濒死" in result.get("error", "") or "HP 为 0" in result.get("error", "")

    def test_long_rest_zero_hp_rejected(self, make_state, wp):
        from wp.rest import RestManager
        sm = make_state("dnd5e", campaign="zero_hp_long")
        player = sm.get("player")
        player["hp"] = {"current": 0, "max": 20, "temp": 0}
        player["hit_dice"] = {"total": "3d8", "used": 0}
        sm.update({"player": player}, reason="test", actor="test")
        mgr = RestManager(sm)
        result = mgr.long_rest()
        assert result["success"] is False
        assert "濒死" in result.get("error", "") or "HP 为 0" in result.get("error", "")

    def test_short_rest_one_hp_works(self, make_state, wp):
        """HP=1 应允许短休"""
        from wp.rest import RestManager
        sm = make_state("dnd5e", campaign="one_hp_short")
        player = sm.get("player")
        player["hp"] = {"current": 1, "max": 20, "temp": 0}
        player["hit_dice"] = {"total": "3d8", "used": 0}
        player["abilities"] = {"con": 14}
        sm.update({"player": player}, reason="test", actor="test")
        mgr = RestManager(sm)
        result = mgr.short_rest(hit_dice_count=1)
        assert result["success"] is True


# ============================================================
# rest.py: Warlock pact magic 短休恢复
# ============================================================

class TestWarlockPactMagic:
    def test_warlock_short_rest_restores_pact_magic(self, make_state, wp):
        """邪术师短休应恢复所有 Pact Magic slots（PHB p. 107）"""
        from wp.rest import RestManager
        sm = make_state("dnd5e", campaign="warlock_short")
        player = sm.get("player")
        player["class"] = "邪术师"
        player["hp"] = {"current": 10, "max": 20, "temp": 0}
        player["hit_dice"] = {"total": "3d8", "used": 0}
        player["abilities"] = {"con": 14}
        player["pact_magic_slots"] = {"1": 0}  # 0 槽
        player["pact_magic_max"] = {"1": 2}    # 但最多 2
        sm.update({"player": player}, reason="test", actor="test")
        mgr = RestManager(sm)
        result = mgr.short_rest()
        assert result["success"] is True
        assert result["pact_magic_restored"] == {"1": 2}

    def test_warlock_long_rest_restores_pact_magic(self, make_state, wp):
        from wp.rest import RestManager
        sm = make_state("dnd5e", campaign="warlock_long")
        player = sm.get("player")
        player["class"] = "邪术师"
        player["hp"] = {"current": 10, "max": 20, "temp": 0}
        player["hit_dice"] = {"total": "3d8", "used": 0}
        player["abilities"] = {"con": 14}
        player["pact_magic_slots"] = {"1": 0}
        player["pact_magic_max"] = {"1": 2}
        sm.update({"player": player}, reason="test", actor="test")
        mgr = RestManager(sm)
        result = mgr.long_rest()
        assert result["success"] is True
        assert result["pact_magic_restored"] == {"1": 2}

    def test_non_warlock_no_pact_magic(self, make_state, wp):
        """非邪术师：pact_magic 字段不变化"""
        from wp.rest import RestManager
        sm = make_state("dnd5e", campaign="non_warlock")
        player = sm.get("player")
        player["class"] = "法师"
        player["hp"] = {"current": 10, "max": 20, "temp": 0}
        player["hit_dice"] = {"total": "3d6", "used": 0}
        player["abilities"] = {"con": 14}
        # 没有 pact_magic 字段
        sm.update({"player": player}, reason="test", actor="test")
        mgr = RestManager(sm)
        result = mgr.short_rest()
        assert result["success"] is True
        assert result["pact_magic_restored"] == {}


# ============================================================
# rest.py: 长休减少 exhaustion
# ============================================================

class TestLongRestExhaustion:
    def test_long_rest_decreases_exhaustion(self, make_state, wp):
        from wp.rest import RestManager
        sm = make_state("dnd5e", campaign="exh_test")
        player = sm.get("player")
        player["hp"] = {"current": 10, "max": 20, "temp": 0}
        player["hit_dice"] = {"total": "3d8", "used": 0}
        player["abilities"] = {"con": 14}
        player["exhaustion"] = 3
        sm.update({"player": player}, reason="test", actor="test")
        mgr = RestManager(sm)
        result = mgr.long_rest()
        assert result["success"] is True
        assert result["exhaustion_before"] == 3
        assert result["exhaustion_after"] == 2

    def test_long_rest_exhaustion_floor_zero(self, make_state, wp):
        from wp.rest import RestManager
        sm = make_state("dnd5e", campaign="exh_floor")
        player = sm.get("player")
        player["hp"] = {"current": 10, "max": 20, "temp": 0}
        player["hit_dice"] = {"total": "3d8", "used": 0}
        player["abilities"] = {"con": 14}
        player["exhaustion"] = 0
        sm.update({"player": player}, reason="test", actor="test")
        mgr = RestManager(sm)
        result = mgr.long_rest()
        assert result["exhaustion_after"] == 0


# ============================================================
# rest.py: 0 命中骰的角色不获骰
# ============================================================

class TestLongRestZeroHitDice:
    def test_zero_hit_dice_no_phantom_dice(self, make_state, wp):
        """0 命中骰的角色不获骰（PHB）"""
        from wp.rest import RestManager
        sm = make_state("dnd5e", campaign="zero_dice")
        player = sm.get("player")
        player["hp"] = {"current": 10, "max": 20, "temp": 0}
        player["hit_dice"] = {"total": "0d8", "used": 0}  # 0 骰
        player["abilities"] = {"con": 14}
        sm.update({"player": player}, reason="test", actor="test")
        mgr = RestManager(sm)
        result = mgr.long_rest()
        assert result["success"] is True
        # 0 命中骰 → 0 恢复
        assert result["hit_dice_restored"] == 0
        assert result["hit_dice_total"] == 0
