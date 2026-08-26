"""状态层测试：模板加载 / I/O / 快照 / 回滚 / 规则路由 / 战役管理"""

import pytest


class TestTemplate:
    def test_load_dnd5e(self, make_state):
        sm = make_state("dnd5e")
        assert sm.get("template") == "dnd5e"

    def test_load_dnd3r(self, make_state):
        sm = make_state("dnd3r")
        assert sm.get("player.abilities.str") == 10

    def test_load_coc7e(self, make_state):
        sm = make_state("coc7e")
        assert sm.get("investigator") is not None
        assert sm.get("characteristics.str") == 50

    def test_list_templates(self, make_state, data_dir):
        sm = make_state()
        names = {t["name"] for t in sm.list_templates()}
        assert {"dnd5e", "dnd3r", "coc7e"} <= names


class TestStateIO:
    def test_update_and_get(self, make_state):
        sm = make_state()
        r = sm.update({"player.hp.current": 15}, reason="test")
        assert r["success"] is True
        assert sm.get("player.hp.current") == 15

    def test_version_increments(self, make_state):
        sm = make_state()
        v0 = sm.get("version")
        sm.update({"player.hp.current": 1}, reason="t")
        sm.update({"player.hp.current": 2}, reason="t")
        assert sm.get("version") == v0 + 2

    def test_get_nested_missing(self, make_state):
        sm = make_state()
        assert sm.get("player.nonexistent.deep") is None

    def test_ability_scores_migrated_to_abilities(self, make_state):
        sm = make_state()
        # 模拟旧状态：player.ability_scores 使用大写键
        sm.update({
            "player.ability_scores": {
                "STR": 16, "DEX": 14, "CON": 15,
                "INT": 10, "WIS": 12, "CHA": 8,
            }
        }, reason="inject legacy ability_scores")
        # 触发 load() 迁移
        sm._state = None
        sm.load()
        assert sm.get("player.ability_scores") is None
        assert sm.get("player.abilities.str") == 16
        assert sm.get("player.abilities.dex") == 14
        assert sm.get("player.abilities.con") == 15

    def test_undo(self, make_state):
        sm = make_state()
        sm.update({"player.hp.current": 20}, reason="t")
        v = sm.get("version")
        r = sm.undo(steps=1)
        assert r["success"] is True
        assert sm.get("version") < v


class TestSnapshot:
    def test_update_default_writes_snapshot(self, make_state):
        sm = make_state()
        sm.update({"player.hp.current": 5}, reason="t")
        assert len(list(sm.history_dir.glob("state_v*.json"))) >= 1

    def test_update_snapshot_false_skips(self, make_state):
        sm = make_state()
        sm.update({"player.hp.current": 5}, reason="t")  # 默认 True → 1 快照
        before = len(list(sm.history_dir.glob("state_v*.json")))
        sm.update({"player.hp.current": 4}, reason="t", snapshot=False)
        sm.update({"player.hp.current": 3}, reason="t", snapshot=False)
        after = len(list(sm.history_dir.glob("state_v*.json")))
        assert after == before  # snapshot=False 不增加快照
        assert sm.get("player.hp.current") == 3  # 但 state.json 保存了

    def test_named_snapshot_rollback(self, make_state):
        sm = make_state()
        sm.update({"player.hp.current": 30}, reason="t")
        r = sm.save_named_snapshot("checkpoint", reason="test")
        assert r["success"] is True
        file = r["snapshot_file"]
        # 修改状态
        sm.update({"player.hp.current": 1}, reason="t")
        # 回滚
        r2 = sm.rollback_to_snapshot(file)
        assert r2["success"] is True
        assert sm.get("player.hp.current") == 30

    def test_list_named_snapshots(self, make_state):
        sm = make_state()
        sm.save_named_snapshot("s1")
        snaps = sm.list_named_snapshots()
        assert any(s["name"] == "s1" for s in snaps)


class TestRuleRouting:
    def test_dnd5e_modifier(self, make_state):
        sm = make_state("dnd5e")
        sm.update({"player.abilities": {"str": 16, "dex": 14, "con": 10,
                                        "int": 10, "wis": 10, "cha": 10}}, reason="t")
        assert sm.get_modifier("str") == 3
        assert sm.get_modifier("dex") == 2

    def test_dnd3r_modifier_same_formula(self, make_state):
        sm = make_state("dnd3r")
        sm.update({"player.abilities": {"str": 16, "dex": 14, "con": 10,
                                        "int": 10, "wis": 10, "cha": 10}}, reason="t")
        assert sm.get_modifier("str") == 3

    def test_dnd3r_bab_and_save(self, make_state):
        sm = make_state("dnd3r")
        sm.update({"player.abilities": {"str": 14, "dex": 10, "con": 12,
                                        "int": 10, "wis": 10, "cha": 10}}, reason="t")
        sm.update({"player.level": 5, "player.class": "fighter"}, reason="t")
        # 战士 5 级：BAB=5, Fort 强豁免=2+5//2=4 + con mod=1 → 5
        assert sm.get_bab() == 5
        assert sm.get_saving_throw("fortitude") == 5

    def test_coc_modifier_is_raw(self, make_state):
        sm = make_state("coc7e")
        sm.update({"characteristics": {"str": 60, "con": 50, "siz": 65,
                                       "dex": 70, "int": 80, "pow": 50, "edu": 75}}, reason="t")
        assert sm.get_modifier("str") == 60  # COC 返回原始值

    def test_coc_derived_stats(self, make_state):
        sm = make_state("coc7e")
        sm.update({"characteristics": {"str": 60, "con": 50, "siz": 65,
                                       "dex": 70, "int": 80, "pow": 50, "edu": 75}}, reason="t")
        d = sm.get_derived_stats()
        assert d["hp_max"] == (50 + 65) // 10  # (CON+SIZ)/10
        assert d["san_max"] == 50  # POW
        assert d["luck"] == 250  # POW*5
        assert d["mp_max"] == 10  # POW/5


class TestCampaigns:
    def test_create_and_switch(self, make_state, data_dir):
        sm = make_state()
        r = sm.create_campaign("newcamp", "dnd5e", "新战役")
        assert r["success"] is True
        r2 = sm.switch_campaign("newcamp")
        assert r2["success"] is True
        assert sm.campaign_name == "newcamp"

    def test_list_and_delete(self, make_state, data_dir):
        sm = make_state()
        sm.create_campaign("todelete", "dnd5e")
        assert any(c["name"] == "todelete" for c in sm.list_campaigns())
        sm.delete_campaign("todelete")
        assert not any(c["name"] == "todelete" for c in sm.list_campaigns())


class TestAtomicWrite:
    def test_atomic_write_roundtrip(self, data_dir):
        from wp.config import atomic_write_json
        import json
        p = data_dir / "test.json"
        atomic_write_json(p, {"a": 1, "中文": "值"})
        with open(p, encoding="utf-8") as f:
            assert json.load(f) == {"a": 1, "中文": "值"}
        # 无残留 tmp
        assert not p.with_suffix(".json.tmp").exists()
