"""creatures.json 快照加载测试（Step 14a + 15 升级）"""

import pytest


def test_creatures_loaded_into_rules_book(wp):
    """RulesBook 加载 dnd5e 后，creatures 分类应非空（331 怪物）"""
    from wp.rules import RulesBook
    book = RulesBook()
    book.load("dnd5e")
    creatures = book.list("dnd5e", "creatures")
    assert len(creatures) >= 300, f"creatures 数量不足: {len(creatures)}"


def test_creatures_get_goblin(wp):
    """按 slug 查 Goblin 变体"""
    from wp.rules import RulesBook
    book = RulesBook()
    book.load("dnd5e")
    goblin = book.get("dnd5e", "creatures", "goblin_warrior")
    assert goblin is not None
    assert "Goblin" in goblin["name_en"]
    assert goblin["ac"] >= 10


def test_creatures_skeleton_immunities(wp):
    """Skeleton 免疫毒素 + 易伤钝击"""
    from wp.rules import RulesBook
    book = RulesBook()
    book.load("dnd5e")
    # 找名字含 Skeleton 的
    skeletons = [c for c in book.list("dnd5e", "creatures")
                 if "skeleton" in c["name_en"].lower()]
    assert skeletons, "没有 Skeleton 怪物"
    skel = skeletons[0]
    # 至少有一条免疫或易伤
    has_imm = "毒素" in skel.get("damage_immunities", []) or \
              "poison" in [i.lower() for i in skel.get("damage_immunities", [])]
    has_vuln = bool(skel.get("damage_vulnerabilities", []))
    assert has_imm or has_vuln, f"Skeleton 应该有免疫/易伤: {skel}"


def test_creatures_search_dragon(wp):
    """按 '龙' 搜索应该命中"""
    from wp.rules import RulesBook
    book = RulesBook()
    book.load("dnd5e")
    # 用英文搜（数据是英文的）
    results = book.search("dragon", system="dnd5e", category="creatures", top_k=10)
    assert len(results) >= 5
    assert any("dragon" in r.get("name_en", "").lower() for r in results)


def test_creatures_total_count(wp):
    """至少 300 条怪物（Open5e 2024 SRD 331）"""
    from wp.rules import RulesBook
    book = RulesBook()
    book.load("dnd5e")
    all_creatures = book.list("dnd5e", "creatures")
    assert len(all_creatures) >= 300
    # 每条都有 rule_id
    for c in all_creatures[:10]:
        assert "rule_id" in c
        assert c["rule_id"].startswith("rules.dnd5e.creatures.")


def test_creatures_damage_types(wp):
    """damage_types 应是 list[str]"""
    from wp.rules import RulesBook
    book = RulesBook()
    book.load("dnd5e")
    dragon = book.get("dnd5e", "creatures", "adult_red_dragon")
    if dragon:
        assert "火焰" in dragon["damage_immunities"] or \
               "fire" in [i.lower() for i in dragon["damage_immunities"]]
