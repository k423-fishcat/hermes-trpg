"""世界书检索测试：高置信度本地预过滤（跳过向量检索）"""

import pytest


@pytest.fixture
def store(wp, tmp_path):
    from wp.store import WorldBookStore
    s = WorldBookStore(tmp_path)
    s.add_entry("default", "灰港", "灰港是剑湾北端的港口小镇", keys=["灰港"], category="地点")
    s.add_entry("default", "老比尔", "醉海豹酒馆老板，知道很多传闻", keys=["老比尔"], category="NPC")
    return s


@pytest.fixture
def retriever(store):
    from wp.retriever import WorldBookRetriever
    return WorldBookRetriever(store, {
        "search_backend": "openviking",
        "enabled_books": ["default"],
        "max_entries": 5,
        "min_similarity": 0.6,
    })


class TestSearchLocalScore:
    def test_exact_title_match_scores_high(self, store):
        results = store.search_local("灰港", limit=5)
        assert results
        assert getattr(results[0], "_search_score", 0) >= 100  # 标题精确匹配

    def test_fuzzy_query_low_score(self, store):
        results = store.search_local("那个港口城市", limit=5)
        # "那个港口城市" 不精确匹配标题，可能低分或空
        top_score = getattr(results[0], "_search_score", 0) if results else 0
        assert top_score < 100


class TestPrefilter:
    def test_high_confidence_skips_viking(self, retriever, monkeypatch):
        """标题精确匹配 → 直接返回本地结果，不调用向量检索"""
        called = []
        def fake_viking(*a, **kw):
            called.append(True)
            return []
        monkeypatch.setattr(retriever, "_search_viking", fake_viking)

        results = retriever.search("灰港")
        assert results  # 有本地结果
        assert not called  # 没走 viking

    def test_low_confidence_goes_viking(self, retriever, monkeypatch):
        """模糊查询 → 走向量检索"""
        called = []
        def fake_viking(*a, **kw):
            called.append(True)
            return []
        monkeypatch.setattr(retriever, "_search_viking", fake_viking)

        retriever.search("那个港口城市")
        assert called  # 走了 viking

    def test_viking_failure_falls_back_local(self, retriever, monkeypatch):
        """向量检索失败 → 复用已算好的本地结果"""
        def fake_viking(*a, **kw):
            raise RuntimeError("viking down")
        monkeypatch.setattr(retriever, "_search_viking", fake_viking)

        results = retriever.search("老比尔")  # 标题精确匹配会预过滤，改模糊查询
        # 用模糊但能命中本地内容的查询
        results = retriever.search("酒馆老板")
        # 本地 search_local 能命中（content 含"酒馆老板"），viking 抛异常后复用本地
        assert any("老比尔" in e.title for e in results)

    def test_is_high_confidence_empty(self, retriever):
        assert retriever._is_high_confidence([]) is False


class TestLocalBackend:
    def test_local_backend_direct(self, store):
        from wp.retriever import WorldBookRetriever
        r = WorldBookRetriever(store, {
            "search_backend": "local",
            "enabled_books": ["default"],
            "max_entries": 5,
        })
        results = r.search("灰港")
        assert results
