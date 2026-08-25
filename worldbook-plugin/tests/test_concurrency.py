"""并发写入安全测试

Hermes 用线程池并发执行多个工具（execute_tool_calls_concurrent），
两个工具可能同时调用 state.update()。StateManager 用 RLock 串行化
同战役的写，防止「读-改-写」竞争导致版本号丢失 / 数据覆盖。
"""

import threading

import pytest


class TestConcurrentUpdate:
    def test_version_no_loss(self, make_state):
        """并发 N 次 update，version 必须精确 +N（无丢失）"""
        sm = make_state("dnd5e")
        v0 = sm.get("version")
        N = 20

        def do():
            sm.update({"player.hp.current": 1}, reason="t", snapshot=False)

        threads = [threading.Thread(target=do) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sm.get("version") == v0 + N

    def test_different_fields_both_kept(self, make_state):
        """并发写不同字段，两个字段都保留"""
        sm = make_state("dnd5e")

        def set_hp():
            for _ in range(10):
                sm.update({"player.hp.current": 7}, reason="t", snapshot=False)

        def set_gold():
            for _ in range(10):
                sm.update({"player.gold": 99}, reason="t", snapshot=False)

        t1 = threading.Thread(target=set_hp)
        t2 = threading.Thread(target=set_gold)
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert sm.get("player.hp.current") == 7
        assert sm.get("player.gold") == 99

    def test_event_log_count_consistent(self, make_state):
        """并发 update 后 event_log 长度与 update 次数一致（无丢失）"""
        sm = make_state("dnd5e")
        sm.update({"player.hp.current": 0}, reason="init", snapshot=False)
        before = len(sm.get("event_log") or [])
        N = 15

        def do():
            sm.update({"player.hp.current": 2}, reason="t", snapshot=False)

        threads = [threading.Thread(target=do) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        after = len(sm.get("event_log") or [])
        assert after - before == N


class TestConcurrentSnapshot:
    def test_snapshot_no_corruption(self, make_state):
        """并发 update（snapshot=True）不产生半截文件"""
        sm = make_state("dnd5e")
        N = 10

        def do(i):
            sm.update({"player.hp.current": i}, reason="t", snapshot=True)

        threads = [threading.Thread(target=do, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # state.json 应能正常读取（无损坏）
        import json
        with open(sm.state_file, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert "player" in data
