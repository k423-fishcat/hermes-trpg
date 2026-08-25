"""模组导入 NPC 冲突检测测试"""

import pytest


@pytest.fixture
def npc_mgr(make_state):
    from wp.narrative.npcs import NPCManager
    return NPCManager(make_state("dnd5e"))


@pytest.fixture
def mod_with_npc():
    from wp.adventure.models import AdventureModule, AdventureNPC
    m = AdventureModule(id="test", name="测试模组")
    m.npcs = [
        AdventureNPC(id="n1", name="酒馆老板", description="测试描述",
                     initial_attitude=5, location="酒馆"),
    ]
    return m


def _import(npc_mgr, mod, strategy="skip"):
    from wp.adventure.loader import import_module
    return import_module(mod, npc_mgr=npc_mgr, conflict_strategy=strategy)


class TestNoConflict:
    def test_normal_import(self, npc_mgr, mod_with_npc):
        stats = _import(npc_mgr, mod_with_npc)
        assert stats["npcs_imported"] == 1
        assert stats["npcs_skipped"] == 0
        assert npc_mgr._get_npc("酒馆老板")["description"] == "测试描述"


class TestSkipStrategy:
    def test_skip_existing(self, npc_mgr, mod_with_npc):
        npc_mgr._ensure_npc("酒馆老板")  # 已有同名
        stats = _import(npc_mgr, mod_with_npc, "skip")
        assert stats["npcs_skipped"] == 1
        assert stats["npcs_imported"] == 0
        # 原 NPC 未被覆盖
        assert npc_mgr._get_npc("酒馆老板").get("description", "") == ""
        # 有冲突警告
        assert any("冲突" in e for e in stats["errors"])

    def test_invalid_strategy_falls_back_skip(self, npc_mgr, mod_with_npc):
        npc_mgr._ensure_npc("酒馆老板")
        stats = _import(npc_mgr, mod_with_npc, "bogus")
        assert stats["npcs_skipped"] == 1  # 非法策略回退 skip


class TestOverwriteStrategy:
    def test_overwrite_existing(self, npc_mgr, mod_with_npc):
        npc_mgr._ensure_npc("酒馆老板")
        stats = _import(npc_mgr, mod_with_npc, "overwrite")
        assert stats["npcs_imported"] == 1
        assert npc_mgr._get_npc("酒馆老板")["description"] == "测试描述"
        assert npc_mgr._get_npc("酒馆老板")["location"] == "酒馆"


class TestRenameStrategy:
    def test_rename_existing(self, npc_mgr, mod_with_npc):
        npc_mgr._ensure_npc("酒馆老板")
        stats = _import(npc_mgr, mod_with_npc, "rename")
        assert stats["npcs_imported"] == 1
        # 新名字导入
        assert npc_mgr._get_npc("酒馆老板（测试模组）") is not None
        assert npc_mgr._get_npc("酒馆老板（测试模组）")["description"] == "测试描述"
        # 原 NPC 保留
        assert npc_mgr._get_npc("酒馆老板") is not None
