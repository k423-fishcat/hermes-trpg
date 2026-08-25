"""v2.9 规则书快照集成测试

覆盖：
- RulesBook 加载 + 检索
- check_engine._rule_reference() 走 RulesBook
- spells.cast_spell() 返回 rule_id
- 整个规则书 API 基础用法
"""

import pytest
import sys
from pathlib import Path


# ═════════════════════════════════════════════════════════════
# 基础 API
# ═════════════════════════════════════════════════════════════

def test_rule_id_make_and_parse():
    """rule_id 命名 + 解析"""
    from wp.rules import make_rule_id, parse_rule_id
    rid = make_rule_id("dnd5e", "spells", "fireball")
    assert rid == "rules.dnd5e.spells.fireball"

    parsed = parse_rule_id(rid)
    assert parsed is not None
    assert parsed.system == "dnd5e"
    assert parsed.category == "spells"
    assert parsed.name == "fireball"
    assert str(parsed) == rid


def test_rule_id_parse_invalid():
    """非法 rule_id 返回 None"""
    from wp.rules import parse_rule_id
    assert parse_rule_id("not.a.rule") is None
    assert parse_rule_id("rules.dnd5e") is None  # 段数不够
    assert parse_rule_id("rules.unknown.spells.x") is None  # system 不合法
    assert parse_rule_id("") is None
    assert parse_rule_id(None) is None


def test_rules_book_load_and_get(wp):
    """加载 dnd5e 后能 get fireball"""
    from wp.rules import RulesBook
    book = RulesBook(Path(wp.__file__).parent / "rules" / "builtin")
    book.load("dnd5e")

    fireball = book.get("dnd5e", "spells", "fireball")
    assert fireball is not None
    assert fireball["rule_id"] == "rules.dnd5e.spells.fireball"
    assert fireball["level"] == 3
    assert "尺" in fireball["range"]


def test_rules_book_search(wp):
    """搜索 fireball 应该返回 fireball 第一名"""
    from wp.rules import RulesBook
    book = RulesBook(Path(wp.__file__).parent / "rules" / "builtin")
    book.load("dnd5e")

    results = book.search("fireball", system="dnd5e", top_k=3)
    assert len(results) >= 1
    assert results[0]["name_en"].lower() == "fireball"


def test_rules_book_classes_caster_type(wp):
    """职业 caster_type 区分已知/准备型"""
    from wp.rules import RulesBook
    book = RulesBook(Path(wp.__file__).parent / "rules" / "builtin")
    book.load("dnd5e")

    wizard = book.get("dnd5e", "classes", "wizard")
    assert wizard is not None
    assert wizard["caster_type"] == "prepared"

    sorcerer = book.get("dnd5e", "classes", "sorcerer")
    assert sorcerer is not None
    assert sorcerer["caster_type"] == "known"

    warlock = book.get("dnd5e", "classes", "warlock")
    assert warlock is not None
    assert warlock["caster_type"] == "known"


def test_rules_book_spell_slots(wp):
    """法术位表查询"""
    from wp.rules import RulesBook
    book = RulesBook(Path(wp.__file__).parent / "rules" / "builtin")
    book.load("dnd5e")

    slots = book.get("dnd5e", "spell_slots", "_default")
    assert slots is not None
    # 法师 5 级
    assert slots["full_caster"]["5"] == {"1": 4, "2": 3, "3": 2}
    # 邪术师 1 级：1 个 1 环契约法术位
    assert slots["warlock"]["1"] == {"pact": 1, "level": 1}


# ═════════════════════════════════════════════════════════════
# AppContext 集成
# ═════════════════════════════════════════════════════════════

def test_app_context_has_rules(wp):
    """get_app().rules 应该可用"""
    from wp.app_context import get_app
    app = get_app()
    assert app.rules is not None
    assert app.rules.is_loaded("dnd5e")
    # 至少 8 个分类
    assert len(app.rules.list_categories("dnd5e")) >= 8


# ═════════════════════════════════════════════════════════════
# check_engine 集成
# ═════════════════════════════════════════════════════════════

def test_rule_reference_uses_rules_book(wp):
    """_rule_reference 命中规则书时返回 rule_id 格式"""
    from wp.check_engine import _rule_reference
    # 察觉：命中 checks.json
    text = _rule_reference("skill", "察觉")
    assert "rules.dnd5e.checks.perception" in text
    assert "PHB" in text  # 包含 PHB p.xxx

    # 死亡豁免：命中 combat.json
    text = _rule_reference("death", "")
    assert "rules.dnd5e.combat.death_saving_throw" in text


def test_rule_reference_fallback(wp):
    """_rule_reference 未命中时回退到硬编码字符串"""
    from wp.check_engine import _rule_reference
    # 不存在的技能名（中文）→ fallback
    text = _rule_reference("skill", "不存在的技能名XYZ")
    # fallback 是包含"规则依据"的字符串
    assert "规则依据" in text


# ═════════════════════════════════════════════════════════════
# spells 集成
# ═════════════════════════════════════════════════════════════

def test_cast_spell_returns_rule_id(make_state, wp):
    """cast_spell 成功时返回 rule_id"""
    from wp.app_context import get_app
    from wp.spells import SpellManager
    state = make_state()
    app = get_app()
    sm = SpellManager(state)
    sm.state.update({
        "player": {
            "name": "测试法师",
            "class": "法师",
            "level": 5,
            "spells_known": ["Fireball"],  # 法师是 prepared caster，仍需在 known 列表
            "spells_prepared": ["Fireball"],
            "spell_slots": {"1": 4, "2": 3, "3": 2},
            "spell_slots_max": {"1": 4, "2": 3, "3": 2},
            "abilities": {"int": 16, "dex": 12},
        }
    })
    result = sm.cast_spell("Fireball", spell_level=3)
    assert result.get("success") is True
    assert result.get("rule_id") == "rules.dnd5e.spells.fireball"
    # phb_page 可能为 None（Open5e v2 该字段经常缺失）—— 只要不抛异常即可
    assert "phb_page" in result


# ═════════════════════════════════════════════════════════════
# RulesInjector 按需注入
# ═════════════════════════════════════════════════════════════

def test_rules_injector_spell(wp):
    """提到 'fireball' 时注入法术摘要"""
    from wp.app_context import get_app
    from wp.adapter.rules_injector import RulesInjector
    app = get_app()
    inj = RulesInjector(app.rules)

    block = inj.inject_for_context("我想施放 Fireball 法术")
    assert "fireball" in block.lower()
    assert "rules.dnd5e.spells.fireball" in block
    assert "## 📖 规则速查" in block


def test_rules_injector_keyword(wp):
    """提到 '长休' 时注入长休规则"""
    from wp.app_context import get_app
    from wp.adapter.rules_injector import RulesInjector
    app = get_app()
    inj = RulesInjector(app.rules)

    block = inj.inject_for_context("我们决定长休一下恢复 HP")
    assert "rules.dnd5e.rest.long_rest" in block


def test_rules_injector_no_trigger(wp):
    """无关 prompt 不应注入"""
    from wp.app_context import get_app
    from wp.adapter.rules_injector import RulesInjector
    app = get_app()
    inj = RulesInjector(app.rules)

    block = inj.inject_for_context("今天天气不错")
    assert block == ""


def test_rules_injector_max_three(wp):
    """最多注入 3 条"""
    from wp.app_context import get_app
    from wp.adapter.rules_injector import RulesInjector
    app = get_app()
    inj = RulesInjector(app.rules)

    # 一次提到多个：fireball、long_rest、stealth
    block = inj.inject_for_context("我用 Fireball 攻击，然后找地方长休，再潜行")
    # 至少有内容
    assert "## 📖 规则速查" in block
    # 行数（"- " 开头）应该 ≤ 3
    rule_lines = [line for line in block.split("\n") if line.startswith("- ")]
    assert len(rule_lines) <= 3
    assert len(rule_lines) >= 2
