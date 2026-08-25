"""深度 bug 审查回归测试

覆盖修复的 7 个 bug：
1. rest 短休/长休调用不存在的 clock.advance() → AttributeError 崩溃
2. apply_to_state 把 player.skills 设成 list，检定引擎期望 dict → 崩
3. CharacterSheet.ac 穿甲忽略盾牌 +2
4. inventory.spend_gold 负数金额会加钱
5. inventory.add/remove_item 负数数量
6. clock.advance_minutes 负数时间
7. clock.set_time 越界值不截断
"""

import pytest


class TestRestClock:
    def test_short_rest_no_crash(self, make_state, wp):
        """短休不再因 clock.advance() 不存在而崩溃"""
        from wp.rest import RestManager
        from wp.narrative import WorldClock
        from wp.state import get_default_state_mgr
        sm = make_state("dnd5e")
        sm.update({"player.hp": {"max": 20, "current": 10, "temp": 0}}, reason="t")
        sm.update({"player.hit_dice": {"total": "2d8", "used": 0}}, reason="t")
        clock = WorldClock(sm)
        rm = RestManager(sm, clock=clock)
        r = rm.short_rest(hit_dice_count=1)
        assert r["success"] is True

    def test_long_rest_no_crash(self, make_state, wp):
        from wp.rest import RestManager
        from wp.narrative import WorldClock
        sm = make_state("dnd5e")
        sm.update({"player.hp": {"max": 20, "current": 5, "temp": 2}}, reason="t")
        sm.update({"player.hit_dice": {"total": "2d8", "used": 2}}, reason="t")
        clock = WorldClock(sm)
        rm = RestManager(sm, clock=clock)
        r = rm.long_rest()
        assert r["success"] is True
        assert r["hp_after"] == 20


class TestApplyToStateSkills:
    def test_skills_is_dict(self, make_state, wp):
        """apply_to_state 后 player.skills 是 dict（非 list）"""
        from wp.characters import CharacterSheet, CharacterManager
        char = CharacterSheet(name="测试", level=1, hp_max=10)
        char.skill_proficiencies = ["athletics", "perception"]
        sm = make_state("dnd5e")
        CharacterManager(sm.data_dir).apply_to_state(char, sm)
        skills = sm.get("player.skills")
        assert isinstance(skills, dict)  # 关键：不再崩 .items()
        assert skills.get("运动") is True

    def test_skill_check_after_apply(self, make_state, wp):
        """apply_to_state 后做技能检定不崩（get_skill_modifier 读 dict）"""
        from wp.characters import CharacterSheet, CharacterManager
        from wp.check_engine import roll_check
        char = CharacterSheet(name="测试", level=1, hp_max=10)
        char.abilities["str"] = 16
        char.skill_proficiencies = ["athletics"]
        char.save_proficiencies = ["str"]
        sm = make_state("dnd5e")
        CharacterManager(sm.data_dir).apply_to_state(char, sm)
        sm.update({"player.proficiency_bonus": 2}, reason="t")
        r = roll_check(sm, check_type="skill", check_name="运动", dc=15, description="翻墙")
        assert r["total_bonus"] == 5  # STR16 +3 + 熟练2


class TestCharacterSheetAc:
    def test_shield_with_armor(self, wp):
        """穿甲+盾牌：AC = 护甲AC + 盾牌2 + 敏捷（按类型）"""
        from wp.characters import CharacterSheet
        char = CharacterSheet()
        char.abilities["dex"] = 14  # +2
        char.armor = {"type": "light", "ac": 11}
        char.shield = True
        assert char.ac == 11 + 2 + 2  # 护甲11 + 盾牌2 + 敏2

    def test_heavy_armor_shield(self, wp):
        from wp.characters import CharacterSheet
        char = CharacterSheet()
        char.abilities["dex"] = 18  # +4（重甲忽略）
        char.armor = {"type": "heavy", "ac": 18}
        char.shield = True
        assert char.ac == 18 + 2  # 重甲18 + 盾牌2（不加固敏）

    def test_no_armor_shield(self, wp):
        from wp.characters import CharacterSheet
        char = CharacterSheet()
        char.abilities["dex"] = 14
        char.shield = True
        assert char.ac == 10 + 2 + 2  # 基础10 + 盾牌2 + 敏2


class TestGoldNegative:
    def test_spend_negative_rejected(self, make_state, wp):
        """spend_gold 负数应拒绝（原会加钱）"""
        from wp.inventory import InventoryManager
        sm = make_state("dnd5e")
        sm.update({"player.gold": 100}, reason="t")
        inv = InventoryManager(sm)
        r = inv.spend_gold(-50)
        assert r["success"] is False
        assert sm.get("player.gold") == 100  # 金额未变


class TestQuantityBoundary:
    def test_add_negative_rejected(self, make_state, wp):
        from wp.inventory import InventoryManager
        sm = make_state("dnd5e")
        inv = InventoryManager(sm)
        r = inv.add_item({"name": "药水", "type": "potion"}, quantity=-5)
        assert r["success"] is False

    def test_remove_negative_rejected(self, make_state, wp):
        from wp.inventory import InventoryManager
        sm = make_state("dnd5e")
        inv = InventoryManager(sm)
        inv.add_item({"name": "药水", "type": "potion"}, quantity=3)
        r = inv.remove_item("药水", quantity=-2)
        assert r["success"] is False
        # 数量未变
        items = inv.list_items()
        assert items[0]["quantity"] == 3


class TestClockBoundary:
    def test_advance_negative_rejected(self, make_state, wp):
        from wp.narrative import WorldClock
        sm = make_state("dnd5e")
        clock = WorldClock(sm)
        r = clock.advance_minutes(-30)
        assert r["success"] is False

    def test_set_time_clamps(self, make_state, wp):
        from wp.narrative import WorldClock
        sm = make_state("dnd5e")
        clock = WorldClock(sm)
        clock.set_time(month=13, day=40, hour=25, minute=70)
        info = clock.now()
        assert info["month"] == 12  # 截断到 12
        assert info["day"] == 30    # 截断到 30
        assert info["hour"] == 23
        assert info["minute"] == 59
