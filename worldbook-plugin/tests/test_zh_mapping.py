"""zh_mapping 测试（v2.10 中文翻译）"""

import pytest


def test_zh_mapping_loads(wp):
    """zh_mapping.json 应能加载"""
    from wp.rules.zh_mapping import _load_mapping
    mapping = _load_mapping()
    assert "spells" in mapping
    assert "creatures" in mapping
    assert "classes" in mapping
    assert "conditions" in mapping
    assert "items" in mapping
    # 至少有 100 条
    total = sum(len(v) for v in mapping.values())
    assert total >= 100, f"映射总数太少: {total}"


def test_zh_mapping_get_zh(wp):
    """查具体条目"""
    from wp.rules.zh_mapping import get_zh
    assert get_zh("spells", "fireball") == "火球术"
    assert get_zh("creatures", "orc") == "兽人"
    assert get_zh("classes", "wizard") == "法师"
    assert get_zh("conditions", "frightened") == "恐慌"
    assert get_zh("items", "bag_of_holding") == "次元袋"


def test_zh_mapping_fallback(wp):
    """没找到的 slug 返回 None（不抛异常）"""
    from wp.rules.zh_mapping import get_zh
    assert get_zh("spells", "nonexistent_spell_xyz") is None
    # 默认值
    assert get_zh("spells", "nonexistent_xyz", default="默认") == "默认"


def test_translate_function_fills_zh(wp):
    """translate() 自动从 rule_id 抽 category + slug 查中文"""
    from wp.rules.zh_mapping import translate
    rule = {
        "rule_id": "rules.dnd5e.spells.fireball",
        "name_zh": "Fireball",  # 当前是英文
        "name_en": "Fireball",
    }
    result = translate(rule)
    assert result["name_zh"] == "火球术"


def test_translate_skips_chinese(wp):
    """已有中文名时跳过"""
    from wp.rules.zh_mapping import translate
    rule = {
        "rule_id": "rules.dnd5e.spells.fireball",
        "name_zh": "火焰球（玩家手填）",
        "name_en": "Fireball",
    }
    result = translate(rule)
    # 不覆盖已有中文
    assert result["name_zh"] == "火焰球（玩家手填）"


def test_translate_no_match_keeps_english(wp):
    """无映射时保留英文"""
    from wp.rules.zh_mapping import translate
    rule = {
        "rule_id": "rules.dnd5e.spells.never_existed_xyz",
        "name_zh": "Never Existed",
        "name_en": "Never Existed",
    }
    result = translate(rule)
    # 没找到映射，保持原样
    assert result["name_zh"] == "Never Existed"


def test_creatures_have_zh_names(wp):
    """creatures.json 应有中文名（拉取时 normalize 自动翻译）"""
    from wp.rules import RulesBook
    book = RulesBook()
    book.load("dnd5e")
    goblin = book.get("dnd5e", "creatures", "goblin_warrior")
    assert goblin["name_zh"] == "哥布林战士"
    dragon = book.get("dnd5e", "creatures", "adult_red_dragon")
    assert dragon["name_zh"] == "成年红龙"


def test_spells_have_zh_names(wp):
    """spells.json 核心法术有中文"""
    from wp.rules import RulesBook
    book = RulesBook()
    book.load("dnd5e")
    fireball = book.get("dnd5e", "spells", "fireball")
    assert fireball["name_zh"] == "火球术"
    magic_missile = book.get("dnd5e", "spells", "magic_missile")
    assert magic_missile["name_zh"] == "魔法飞弹"


def test_injector_uses_zh_title(wp):
    """RulesInjector 注入时优先用中文标题"""
    from wp.rules import RulesBook
    from wp.adapter.rules_injector import RulesInjector
    book = RulesBook()
    book.load("dnd5e")
    injector = RulesInjector(book)
    # 玩家说"火球术"
    result = injector.inject_for_context("我对敌人施放火球术", system="dnd5e")
    assert "火球术" in result
    assert "Fireball" in result
    assert "rules.dnd5e.spells.fireball" in result


def test_injector_creature_trigger(wp):
    """玩家说"哥布林"也能注入怪物摘要"""
    from wp.rules import RulesBook
    from wp.adapter.rules_injector import RulesInjector
    book = RulesBook()
    book.load("dnd5e")
    injector = RulesInjector(book)
    result = injector.inject_for_context("我攻击一只哥布林战士", system="dnd5e")
    assert "哥布林" in result
    assert "rules.dnd5e.creatures.goblin_warrior" in result


def test_injector_no_zh_fallback_en(wp):
    """没中文的规则用英文显示"""
    from wp.rules import RulesBook
    from wp.adapter.rules_injector import RulesInjector
    book = RulesBook()
    book.load("dnd5e")
    injector = RulesInjector(book)
    # 找一个中文名缺失的法术：acid_splash 在 mapping 里，但 'aid' 不在
    aid = book.get("dnd5e", "spells", "aid")
    if aid and aid.get("name_zh") == aid.get("name_en"):
        # 假设 zh 还是英文——验证 inject 不会崩
        result = injector.inject_for_context("我施放 Aid", system="dnd5e")
        # 只在 "Aid" 命中（英文），至少不报错
        assert "rules.dnd5e.spells.aid" in result or result == ""
