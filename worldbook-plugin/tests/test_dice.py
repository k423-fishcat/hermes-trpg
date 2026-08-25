"""骰子引擎测试（纯 stdlib，不依赖插件状态）"""

import pytest


@pytest.fixture(scope="module")
def dice(wp):
    from wp import dice
    return dice


class TestRollDice:
    def test_basic(self, dice):
        r = dice.roll_dice(3, 6)
        assert len(r) == 3
        assert all(1 <= x <= 6 for x in r)

    def test_invalid_count(self, dice):
        with pytest.raises(ValueError):
            dice.roll_dice(0, 6)

    def test_invalid_sides(self, dice):
        with pytest.raises(ValueError):
            dice.roll_dice(1, 1)


class TestRollExpression:
    def test_simple(self, dice):
        r = dice.roll("2d6")
        assert 2 <= r["total"] <= 12

    def test_modifier(self, dice):
        r = dice.roll("1d8+3")
        assert 4 <= r["total"] <= 11

    def test_negative_modifier(self, dice):
        r = dice.roll("1d8-2")
        assert -1 <= r["total"] <= 6

    def test_multi_group(self, dice):
        r = dice.roll("2d6+1d4+3")
        assert 6 <= r["total"] <= 19

    def test_advantage(self, dice):
        r = dice.roll("adv")
        assert r["expression"] == "2d20kh1 (优势)"
        assert 1 <= r["total"] <= 20
        assert "rolls" in r["details"]

    def test_disadvantage(self, dice):
        r = dice.roll("dis")
        assert 1 <= r["total"] <= 20
        assert r["details"]["took"] == "min"

    def test_keep_high_4d6kh3(self, dice):
        # 4d6 取最高 3
        r = dice.roll("4d6kh3")
        assert 3 <= r["total"] <= 18
        detail = r["details"][0]
        assert len(detail["kept"]) == 3
        assert len(detail["dropped"]) == 1
        assert len(detail["rolls"]) == 4

    def test_invalid(self, dice):
        with pytest.raises(ValueError):
            dice.roll("xyz")


class TestRollD20:
    def test_single(self, dice):
        r = dice.roll_d20()
        assert 1 <= r["nat_roll"] <= 20
        assert len(r["all_rolls"]) == 1

    def test_advantage_takes_max(self, dice):
        r = dice.roll_d20(advantage=True)
        assert r["nat_roll"] == max(r["all_rolls"])
        assert len(r["all_rolls"]) == 2

    def test_disadvantage_takes_min(self, dice):
        r = dice.roll_d20(disadvantage=True)
        assert r["nat_roll"] == min(r["all_rolls"])
        assert len(r["all_rolls"]) == 2


class TestDamage:
    def test_normal(self, dice):
        r = dice.roll_damage("1d8", modifier=3)
        assert 4 <= r["total"] <= 11
        assert r["crit"] is False
        assert len(r["rolls"]) == 1

    def test_crit_doubles_dice(self, dice):
        r = dice.roll_damage("1d8", modifier=3, crit=True)
        assert len(r["rolls"]) == 2  # 暴击骰子数翻倍
        assert 5 <= r["total"] <= 19


class TestHitDice:
    def test_single(self, dice):
        r = dice.roll_hit_dice(8)
        assert 1 <= r <= 8

    def test_total(self, dice):
        r = dice.roll_hit_dice_total("2d10", con_modifier=2)
        assert len(r["rolls"]) == 2
        # 每颗至少 1（含 con_mod），两颗至少 2
        assert r["heal_total"] >= 2
        assert r["heal_total"] <= 22


class TestHealing:
    def test_with_modifier(self, dice):
        r = dice.roll_healing("2d4+2", modifier=1)
        assert 5 <= r["total"] <= 11

    def test_plain(self, dice):
        r = dice.roll_healing("1d4")
        assert 1 <= r["total"] <= 4


class TestAbilityScores:
    @pytest.mark.parametrize("method", ["standard", "classic", "heroic", "flat"])
    def test_all_methods(self, dice, method):
        r = dice.roll_ability_scores(method)
        assert len(r["abilities"]) == 6  # str/dex/con/int/wis/cha
        assert r["total"] > 0

    def test_standard_range(self, dice):
        r = dice.roll_ability_scores("standard")
        for ab in r["abilities"].values():
            assert 3 <= ab["score"] <= 18

    def test_invalid_method(self, dice):
        with pytest.raises(ValueError):
            dice.roll_ability_scores("unknown")


class TestCocCheck:
    def test_skill_50(self, dice):
        r = dice.coc_check(50)
        assert 1 <= r["roll"] <= 100
        assert r["skill_value"] == 50
        assert r["level"] in ("大成功", "极难成功", "困难成功", "成功", "失败", "大失败")

    def test_invalid_skill(self, dice):
        with pytest.raises(ValueError):
            dice.coc_check(200)

    def test_roll_is_consistent(self, dice):
        # 成功等级与 roll<=skill 一致
        r = dice.coc_check(50)
        if r["roll"] <= 50:
            assert r["success"] is True
        else:
            assert r["success"] is False


class TestFormat:
    def test_roll_expr(self, dice):
        r = dice.roll("1d20+5")
        out = dice.format_roll_result(r)
        assert "1d20+5" in out
        assert str(r["total"]) in out

    def test_damage(self, dice):
        r = dice.roll_damage("1d8", modifier=3, crit=True)
        out = dice.format_roll_result(r)
        assert "暴击" in out
