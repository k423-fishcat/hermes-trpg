"""法术系统测试：覆盖 D&D 5e 准备/已知型施法者规则

规则来源：Player's Handbook 2014, Chapter 10: Spellcasting

施法者类型：
- 已知型（术士/吟游诗人/邪术师）：spells_known 即可施
- 准备型（牧师/德鲁伊/圣武士/法师/游侠）：必须在 spells_prepared

测试覆盖：
1. 已知型施法者 (术士) —— spells_known 即能施，spells_prepared 不必存在
2. 准备型施法者 (法师) —— 必须 known 且 prepared 才能施
3. 准备型施法者 (牧师) —— 必须 prepared
4. 戏法永远无需准备
5. prepare() 对已知型施法者报错
6. remove_known 对准备型同步移除 prepared
"""

import pytest


# 在测试里硬编码施法者集合，避免模块加载时依赖 wp 包
KNOWN_CASTERS = {"术士", "吟游诗人", "邪术师", "sorcerer", "bard", "warlock"}
PREPARED_CASTERS = {"牧师", "德鲁伊", "圣武士", "法师", "游侠",
                    "cleric", "druid", "paladin", "wizard", "ranger"}


# 准备一个基础玩家状态
def _setup_player(make_state, class_name, *, known=None, prepared=None,
                  spell_slots=None, spell_slots_max=None):
    """建 StateManager + 装入玩家数据 + 返回 (sm, sm.player dict)"""
    sm = make_state("dnd5e", campaign=f"spell_{class_name}")
    player = sm.get("player") or {}
    player["class"] = class_name
    player["abilities"] = {"str": 10, "dex": 10, "con": 14, "int": 16, "wis": 12, "cha": 10}
    player["proficiency_bonus"] = 2
    player["hp"] = {"current": 20, "max": 20, "temp": 0}
    player["spellcasting_ability"] = "int"
    player["spells_known"] = list(known or [])
    player["spells_prepared"] = list(prepared or [])
    player["spell_slots"] = dict(spell_slots or {})
    player["spell_slots_max"] = dict(spell_slots_max or {})
    sm.update({"player": player}, reason=f"测试 setup: {class_name}", actor="测试")
    return sm


def _spell_mgr(wp):
    from wp.spells import SpellManager
    return SpellManager


def _is_known_caster(wp):
    from wp.spells import _is_known_caster
    return _is_known_caster


def _is_prepared_caster(wp):
    from wp.spells import _is_prepared_caster
    return _is_prepared_caster


# ============================================================
# _is_known_caster / _is_prepared_caster 单元测试
# ============================================================

class TestCasterTypeDetection:
    def test_known_casters_chinese(self, wp):
        f = _is_known_caster(wp)
        assert f("术士")
        assert f("吟游诗人")
        assert f("邪术师")

    def test_known_casters_english(self, wp):
        f = _is_known_caster(wp)
        assert f("Sorcerer")
        assert f("bard")
        assert f("WARLOCK")

    def test_prepared_casters_chinese(self, wp):
        f = _is_prepared_caster(wp)
        assert f("牧师")
        assert f("德鲁伊")
        assert f("圣武士")
        assert f("法师")
        assert f("游侠")

    def test_prepared_casters_english(self, wp):
        f = _is_prepared_caster(wp)
        assert f("Cleric")
        assert f("Wizard")
        assert f("Ranger")

    def test_mutual_exclusion(self, wp):
        """已知型和准备型不能同时成立"""
        fk = _is_known_caster(wp)
        fp = _is_prepared_caster(wp)
        for c in KNOWN_CASTERS:
            assert not fp(c), f"{c} 不能既是已知型又是准备型"
        for c in PREPARED_CASTERS:
            assert not fk(c), f"{c} 不能既是准备型又是已知型"

    def test_unknown_class(self, wp):
        """未识别的职业：两个判断都为 False"""
        fk = _is_known_caster(wp)
        fp = _is_prepared_caster(wp)
        for c in ["战士", "rogue", "barbarian", "", None]:
            assert not fk(c)
            assert not fp(c)


# ============================================================
# 已知型施法者测试（术士 / 吟游诗人 / 邪术师）
# ============================================================

class TestKnownCasterSorcerer:
    """术士：spells_known 即能施，spells_prepared 字段不存在也能施"""

    def _setup(self, make_state):
        return _setup_player(
            make_state, "术士",
            known=["fireball", "shield", "mage_armor"],
            spell_slots={"1": 2, "2": 1},
            spell_slots_max={"1": 2, "2": 1},
        )

    def test_cast_known_without_prepared(self, make_state, wp):
        """术士：spells_known 有就能施，无需 prepared"""
        sm = self._setup(make_state)
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("fireball", spell_level=3)
        # 3 环没 slot，应该报"没有可用的法术位"而非"没有准备"
        assert result["success"] is False
        assert "准备" not in result.get("error", "")

    def test_cast_known_with_slot(self, make_state, wp):
        """术士有 spell slot 时能正常施法"""
        sm = self._setup(make_state)
        mgr = _spell_mgr(wp)(sm)
        # 准备 2 环法术位；fireball 默认 3 环，但法术位可向上兼容
        result = mgr.cast_spell("fireball", spell_level=2)
        assert result["success"] is True
        assert result["caster_type"] == "known"
        assert result["is_cantrip"] is False
        # 2 环 slot 应被消耗
        assert sm.get("player")["spell_slots"]["2"] == 0

    def test_cantrip_no_slot_needed(self, make_state, wp):
        """术士戏法不消耗 slot、不需要 prepared"""
        sm = _setup_player(
            make_state, "术士",
            known=["fire_bolt"],  # 戏法在 known 里
            spell_slots={"1": 0},  # 0 slot
            spell_slots_max={"1": 4},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("fire_bolt", spell_data={"level": 0})
        assert result["success"] is True
        assert result["is_cantrip"] is True
        # slot 没被消耗
        assert sm.get("player")["spell_slots"]["1"] == 0

    def test_unknown_spell_rejected(self, make_state, wp):
        """术士：未知的法术拒绝施放"""
        sm = self._setup(make_state)
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("meteor_swarm")  # 不在 known
        assert result["success"] is False
        assert "不会" in result.get("error", "") or "术士" in result.get("error", "")

    def test_prepare_rejected_for_known_caster(self, make_state, wp):
        """术士调用 prepare 应报错（已知型无需准备）"""
        sm = self._setup(make_state)
        mgr = _spell_mgr(wp)(sm)
        result = mgr.prepare("fireball")
        assert result["success"] is False
        assert "已知" in result.get("error", "") or "无需" in result.get("error", "")


class TestKnownCasterWarlock:
    """邪术师：已知型 + Pact Magic（所有 slot 同级最高）"""

    def test_warlock_cast_from_known(self, make_state, wp):
        sm = _setup_player(
            make_state, "邪术师",
            known=["eldritch_blast", "hex"],
            spell_slots={"1": 2, "2": 0, "3": 0},
            spell_slots_max={"1": 2, "2": 0, "3": 0},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("hex", spell_level=1)
        assert result["success"] is True
        assert result["caster_type"] == "known"


# ============================================================
# 准备型施法者测试（法师 / 牧师 / 游侠）
# ============================================================

class TestPreparedCasterWizard:
    """法师：必须在 known（法术书）+ prepared 才能施"""

    def _setup(self, make_state, prepared=None):
        return _setup_player(
            make_state, "法师",
            known=["fireball", "shield", "magic_missile"],
            prepared=prepared or ["shield", "magic_missile"],
            spell_slots={"1": 3, "2": 2, "3": 1},
            spell_slots_max={"1": 3, "2": 2, "3": 1},
        )

    def test_cast_prepared_succeeds(self, make_state, wp):
        """法师：prepared 里的法术能施"""
        sm = self._setup(make_state)
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("shield", spell_level=1)
        assert result["success"] is True
        assert result["caster_type"] == "prepared"

    def test_known_but_not_prepared_fails(self, make_state, wp):
        """法师：known 但没准备 → 失败"""
        sm = self._setup(make_state)
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("fireball", spell_level=3)
        assert result["success"] is False
        assert "准备" in result.get("error", "")

    def test_unknown_spell_fails(self, make_state, wp):
        """法师：法术书里都没有 → 失败"""
        sm = self._setup(make_state)
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("wish")
        assert result["success"] is False
        # 错误信息应该反映"尚未习得"
        assert "习得" in result.get("error", "") or "不会" in result.get("error", "")

    def test_prepare_from_known(self, make_state, wp):
        """法师：能从法术书（known）里准备法术"""
        sm = self._setup(make_state, prepared=[])
        mgr = _spell_mgr(wp)(sm)
        result = mgr.prepare("fireball")
        assert result["success"] is True
        assert "fireball" in sm.get("player")["spells_prepared"]

    def test_remove_known_syncs_prepared(self, make_state, wp):
        """法师：remove_known 同时从 prepared 移除"""
        sm = self._setup(make_state)
        mgr = _spell_mgr(wp)(sm)
        mgr.remove_known("shield")
        player = sm.get("player")
        assert "shield" not in player["spells_known"]
        assert "shield" not in player["spells_prepared"]


class TestPreparedCasterCleric:
    """牧师：准备型，全职业法术列表可准备（不限制必须先 known）"""

    def test_cleric_prepared_cast(self, make_state, wp):
        sm = _setup_player(
            make_state, "牧师",
            known=["cure_wounds", "bless"],
            prepared=["cure_wounds"],
            spell_slots={"1": 2},
            spell_slots_max={"1": 2},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("cure_wounds", spell_level=1)
        assert result["success"] is True
        assert result["caster_type"] == "prepared"

    def test_cleric_not_prepared_fails(self, make_state, wp):
        sm = _setup_player(
            make_state, "牧师",
            known=["bless", "cure_wounds"],
            prepared=["bless"],  # cure_wounds 没准备
            spell_slots={"1": 2},
            spell_slots_max={"1": 2},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("cure_wounds", spell_level=1)
        assert result["success"] is False
        assert "准备" in result.get("error", "")


class TestPreparedCasterRanger:
    """游侠：准备型但法术位少（半职业等级向上取整）"""

    def test_ranger_cast(self, make_state, wp):
        sm = _setup_player(
            make_state, "游侠",
            known=["hunters_mark"],
            prepared=["hunters_mark"],
            spell_slots={"1": 2},
            spell_slots_max={"1": 2},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("hunters_mark", spell_level=1)
        assert result["success"] is True
        assert result["caster_type"] == "prepared"


# ============================================================
# 戏法（Cantrip）通用规则
# ============================================================

class TestCantripRules:
    def test_cantrip_no_slot_for_known_caster(self, make_state, wp):
        """已知型施法者：戏法不消耗 slot，无需 prepared"""
        sm = _setup_player(
            make_state, "吟游诗人",
            known=["vicious_mockery"],
            spell_slots={"1": 0},
            spell_slots_max={"1": 0},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("vicious_mockery", spell_data={"level": 0})
        assert result["success"] is True
        assert result["is_cantrip"] is True

    def test_cantrip_no_slot_for_prepared_caster(self, make_state, wp):
        """准备型施法者：戏法不消耗 slot，无需 prepared"""
        sm = _setup_player(
            make_state, "法师",
            known=[],
            prepared=[],
            spell_slots={"1": 0},
            spell_slots_max={"1": 0},
        )
        mgr = _spell_mgr(wp)(sm)
        # 戏法直接通过 spell_data 标识
        result = mgr.cast_spell("fire_bolt", spell_data={"level": 0})
        assert result["success"] is True
        assert result["is_cantrip"] is True

    def test_cantrip_via_spell_level_zero(self, make_state, wp):
        """spell_level=0 也应识别为戏法"""
        sm = _setup_player(
            make_state, "术士",
            known=["fire_bolt"],
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("fire_bolt", spell_level=0)
        assert result["success"] is True
        assert result["is_cantrip"] is True


# ============================================================
# 边缘情况：未识别职业
# ============================================================

class TestUnknownClassFallback:
    def test_unknown_class_conservative_fallback(self, make_state, wp):
        """未识别的职业走保守路径：必须 prepared 才允许施放"""
        sm = _setup_player(
            make_state, "战士",  # 非施法职业
            known=["fireball"],
            prepared=["fireball"],
            spell_slots={"1": 1},
            spell_slots_max={"1": 1},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("fireball", spell_level=1)
        assert result["success"] is True
        assert result["caster_type"] == "unknown"

    def test_unknown_class_no_prepared(self, make_state, wp):
        """未识别职业：known 但不 prepared → 失败（保守）"""
        sm = _setup_player(
            make_state, "战士",
            known=["fireball"],
            prepared=[],
            spell_slots={"1": 1},
            spell_slots_max={"1": 1},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("fireball", spell_level=1)
        assert result["success"] is False


# ============================================================
# 法术位管理
# ============================================================

class TestSpellSlotManagement:
    def test_slot_consumed(self, make_state, wp):
        sm = _setup_player(
            make_state, "术士",
            known=["fireball"],
            spell_slots={"3": 1},
            spell_slots_max={"3": 1},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("fireball", spell_level=3)
        assert result["success"] is True
        assert sm.get("player")["spell_slots"]["3"] == 0

    def test_no_available_slot(self, make_state, wp):
        sm = _setup_player(
            make_state, "术士",
            known=["fireball"],
            spell_slots={},  # 没法术位
            spell_slots_max={"3": 1},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("fireball", spell_level=3)
        assert result["success"] is False
        assert "法术位" in result.get("error", "")

    def test_upsell_to_higher_slot(self, make_state, wp):
        """请求 3 环但只有 4 环 slot → 用 4 环（向上兼容）"""
        sm = _setup_player(
            make_state, "术士",
            known=["fireball"],
            spell_slots={"3": 0, "4": 1},
            spell_slots_max={"3": 0, "4": 1},
        )
        mgr = _spell_mgr(wp)(sm)
        result = mgr.cast_spell("fireball", spell_level=3)
        assert result["success"] is True
        assert result["level_used"] == 4
        assert sm.get("player")["spell_slots"]["4"] == 0
