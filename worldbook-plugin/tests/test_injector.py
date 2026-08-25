"""上下文注入器测试：按句子边界截断（避免截断在词中间）"""

import pytest


@pytest.fixture
def truncate(wp):
    from wp.injector import ContextInjector
    return ContextInjector._truncate_by_sentence


class TestTruncateBySentence:
    def test_short_content_unchanged(self, truncate):
        assert truncate("短内容", 100) == "短内容"

    def test_cut_at_period(self, truncate):
        content = "这是第一句。这是第二句"
        r = truncate(content, 8)
        assert r == "这是第一句。"  # 截断到句号后，句子完整
        assert r.endswith("。")

    def test_cut_at_newline(self, truncate):
        content = "第一行\n第二行内容"
        r = truncate(content, 5)
        assert r.endswith("\n") or r == "第一行"

    def test_cut_at_comma(self, truncate):
        content = "甲乙丙，丁戊己庚辛"
        r = truncate(content, 5)
        assert r == "甲乙丙，"  # 逗号在 index 3，>= 一半，截断到逗号

    def test_no_boundary_hard_cut(self, truncate):
        content = "一二三四五六七八九十"  # 无任何标点
        r = truncate(content, 5)
        assert len(r) == 5  # 无边界符，硬切到 max_len

    def test_boundary_too_early_fallback(self, truncate):
        """边界太靠前（< 一半）时退化为硬切，避免只截出开头一个字"""
        content = "短。后面是很长很长很长很长很长很长的内容"
        r = truncate(content, 20)
        assert len(r) == 20  # 句号在 index 1 太靠前，退化硬切

    def test_result_never_exceeds_max(self, truncate):
        content = "一些内容，需要被截断到指定长度以内。"
        for max_len in (5, 10, 15, 20):
            r = truncate(content, max_len)
            assert len(r) <= max_len
