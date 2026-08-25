"""世界书检索引擎

支持两种后端：
1. openviking - 向量检索（默认，质量高但有延迟）
2. local - 本地关键词匹配（fallback，快）
"""

import logging
import time
from typing import Dict, List, Optional

from .store import WorldBookEntry, WorldBookStore

logger = logging.getLogger(__name__)


class WorldBookRetriever:
    """世界书检索引擎"""

    def __init__(self, store: WorldBookStore, config: Dict):
        self.store = store
        self.config = config
        self.backend = config.get("search_backend", "openviking")
        self._viking_client = None

    def _get_viking_client(self):
        """懒加载 OpenViking 客户端"""
        if self._viking_client is not None:
            return self._viking_client
        try:
            # 尝试通过 Hermes 的 viking 工具模块获取
            from hermes_tools import viking_search
            self._viking_client = viking_search
            return self._viking_client
        except Exception:
            pass
        # fallback: 直接调 OpenViking HTTP API
        try:
            self._viking_client = _HTTPVikingClient()
            return self._viking_client
        except Exception as e:
            logger.warning(f"[worldbook] OpenViking 不可用，降级到本地搜索: {e}")
            self.backend = "local"
            return None

    def search(self, query: str,
               worldbooks: Optional[List[str]] = None,
               categories: Optional[List[str]] = None,
               limit: Optional[int] = None,
               min_score: Optional[float] = None) -> List[WorldBookEntry]:
        """
        检索相关世界书条目

        Args:
            query: 检索查询
            worldbooks: 限定世界书列表，None=全部启用
            categories: 限定分类，None=全部
            limit: 最大返回条数，默认取配置
            min_score: 最低相似度，默认取配置

        Returns:
            按相关性排序的条目列表
        """
        limit = limit or self.config.get("max_entries", 5)
        min_score = min_score if min_score is not None else self.config.get("min_similarity", 0.6)

        if not query or not query.strip():
            return []

        enabled_books = worldbooks or self.config.get("enabled_books", [])

        if self.backend == "openviking":
            # 高置信度本地预过滤：先走毫秒级本地检索，
            # 若 top1 标题精确匹配（score>=100）直接返回，跳过 200-500ms 的向量检索。
            local_hits = self._search_local(query, enabled_books, categories, limit)
            if self._is_high_confidence(local_hits):
                return local_hits
            try:
                return self._search_viking(query, enabled_books, categories, limit, min_score)
            except Exception as e:
                logger.warning(f"[worldbook] viking 搜索失败，降级本地: {e}")
                return local_hits  # 复用刚才的本地结果，避免重复计算
        else:
            return self._search_local(query, enabled_books, categories, limit)

    @staticmethod
    def _is_high_confidence(entries: List[WorldBookEntry]) -> bool:
        """本地检索 top1 标题精确匹配（score>=100）视为高置信度，可跳过向量检索"""
        if not entries:
            return False
        return getattr(entries[0], "_search_score", 0) >= 100

    def _search_viking(self, query: str, worldbooks: List[str],
                       categories: Optional[List[str]], limit: int,
                       min_score: float) -> List[WorldBookEntry]:
        """使用 OpenViking 向量检索"""
        # 优先使用 Hermes 内置的 viking_search 工具
        client = self._get_viking_client()

        # 构造更精准的查询
        search_query = query
        if worldbooks:
            search_query = f"{query} {' '.join(worldbooks)} 跑团世界书设定"

        try:
            # 尝试调用工具函数形式
            results = client(query=search_query, limit=limit * 3, mode="fast")
        except Exception:
            # fallback: 本地搜索
            return self._search_local(query, worldbooks, categories, limit)

        # 解析结果并映射到本地条目
        entries = []
        seen_ids = set()

        if isinstance(results, dict) and "results" in results:
            items = results["results"]
        elif isinstance(results, list):
            items = results
        else:
            items = []

        for item in items:
            score = item.get("score", 0) if isinstance(item, dict) else 0
            if score < min_score:
                continue

            title = item.get("title", "") if isinstance(item, dict) else str(item)
            uri = item.get("uri", "") if isinstance(item, dict) else ""
            abstract = item.get("abstract", "") if isinstance(item, dict) else ""

            # 用标题去本地世界书里找匹配
            local_entries = self.store.search_local(
                title, worldbooks=worldbooks, categories=categories, limit=1
            )

            if local_entries:
                entry = local_entries[0]
                if entry.id not in seen_ids:
                    entry._search_score = score
                    entries.append(entry)
                    seen_ids.add(entry.id)
            elif abstract:
                # 如果本地没有，就用 viking 返回的摘要构造一个临时条目
                tmp_id = f"viking-{hash(uri)}"
                if tmp_id not in seen_ids:
                    from .store import WorldBookEntry
                    entry = WorldBookEntry(
                        id=tmp_id,
                        title=title,
                        keys=[title],
                        category="其他",
                        content=abstract,
                        priority=50,
                        worldbook="viking",
                    )
                    entry._search_score = score
                    entries.append(entry)
                    seen_ids.add(tmp_id)

            if len(entries) >= limit:
                break

        return entries[:limit]

    def _search_local(self, query: str, worldbooks: List[str],
                      categories: Optional[List[str]], limit: int) -> List[WorldBookEntry]:
        """本地关键词搜索"""
        return self.store.search_local(
            query,
            worldbooks=worldbooks,
            categories=categories,
            limit=limit,
        )

    def format_for_injection(self, entries: List[WorldBookEntry],
                             header: str = "## 世界书相关设定") -> str:
        """
        将条目格式化为注入文本

        格式：
        ## 世界书相关设定

        ### 灰港（地点）
        灰港是剑湾北端的港口小镇...

        ### 老比尔（NPC）
        老比尔是醉海豹酒馆老板...
        """
        if not entries:
            return ""

        lines = [header, ""]
        for e in entries:
            lines.append(f"### {e.title}（{e.category}）")
            lines.append(e.content.strip() if e.content else "(暂无详细描述)")

            # 交互点（如果有的话）
            extras = e.extras or {}
            interactions = extras.get("interactions", [])
            if interactions:
                lines.append("")
                lines.append("**可交互点：**")
                for ia in interactions:
                    lines.append(self._format_interaction(ia))
            lines.append("")

        return "\n".join(lines).strip()

    @staticmethod
    def _format_interaction(ia: Dict) -> str:
        """格式化单个交互点为简洁文本"""
        trigger = ia.get("trigger", "?")
        itype = ia.get("type", "skill")
        check = ia.get("check", {})
        hidden = ia.get("hidden", False)

        skill = check.get("skill", "")
        ability = check.get("ability", "")
        dc = check.get("dc", "?")
        check_label = skill or ability or itype

        icon = {
            "skill": "🎲",
            "ability": "💪",
            "save": "🛡️",
            "item": "📦",
            "dialogue": "💬",
            "trap": "💣",
            "puzzle": "🧩",
        }.get(itype, "▶")

        parts = [f"  {icon} {trigger} — {check_label} DC{dc}"]

        if hidden:
            disc_skill = ia.get("discovery_skill", "察觉")
            disc_dc = ia.get("discovery_dc", 12)
            parts.append(f"（隐藏，需 {disc_skill} DC{disc_dc} 发现）")

        # 后果简述
        outcomes = ia.get("outcomes", {})
        succ = outcomes.get("success", "")
        if succ:
            parts.append(f"\n     ✅ {succ[:50]}")

        result = "".join(parts)
        return result


class _HTTPVikingClient:
    """直接调 OpenViking HTTP API 的 fallback 客户端（预留）"""

    def __init__(self):
        # 从环境变量或配置读取 endpoint
        import os
        self.endpoint = os.environ.get("OPENVIKING_ENDPOINT", "")
        if not self.endpoint:
            raise ValueError("未配置 OPENVIKING_ENDPOINT")

    def search(self, query: str, limit: int = 10, mode: str = "fast") -> dict:
        import urllib.request
        import json
        req = urllib.request.Request(
            f"{self.endpoint}/search",
            data=json.dumps({"query": query, "limit": limit, "mode": mode}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
