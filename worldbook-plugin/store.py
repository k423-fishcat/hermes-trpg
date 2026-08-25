"""世界书数据模型与本地存储管理"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import get_worldbooks_dir, atomic_write_json

logger = logging.getLogger(__name__)


CATEGORY_MAP = {
    "loc": "地点",
    "npc": "NPC",
    "mon": "怪物",
    "item": "物品",
    "org": "组织",
    "rule": "规则",
    "plot": "剧情",
    "misc": "其他",
}

VALID_CATEGORIES = set(CATEGORY_MAP.values())


@dataclass
class WorldBookEntry:
    """世界书条目"""
    id: str
    title: str
    keys: List[str]
    category: str
    content: str
    extras: Dict[str, Any] = field(default_factory=dict)
    priority: int = 100
    enabled: bool = True
    worldbook: str = "default"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class WorldBookStore:
    """世界书本地存储（JSON 文件）"""

    def __init__(self, worldbooks_dir: Optional[Path] = None):
        self.base_dir = worldbooks_dir or get_worldbooks_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, List[WorldBookEntry]] = {}

    def list_books(self) -> List[Dict]:
        """列出所有世界书"""
        books = []
        for f in self.base_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                books.append({
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "version": data.get("version", "0.1"),
                    "entry_count": len(data.get("entries", [])),
                    "path": str(f),
                })
            except json.JSONDecodeError as e:
                logger.error(
                    f"[worldbook] 世界书 JSON 损坏: {f} ({e})。"
                    f"该世界书将不会出现在列表中。请检查文件或用 /worldbook export 备份后删除。"
                )
                continue
            except Exception as e:
                logger.error(f"[worldbook] 加载世界书失败: {f} ({type(e).__name__}: {e})")
                continue
        return books

    def load_book(self, name: str) -> List[WorldBookEntry]:
        """加载一个世界书的所有条目"""
        if name in self._cache:
            return self._cache[name]

        path = self.base_dir / f"{name}.json"
        entries = []
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for e in data.get("entries", []):
                    entries.append(WorldBookEntry(
                        id=e.get("id", ""),
                        title=e.get("title", ""),
                        keys=e.get("keys", []),
                        category=e.get("category", "其他"),
                        content=e.get("content", ""),
                        priority=e.get("priority", 100),
                        enabled=e.get("enabled", True),
                        worldbook=name,
                        created_at=e.get("created_at", time.time()),
                        updated_at=e.get("updated_at", time.time()),
                    ))
            except json.JSONDecodeError as e:
                logger.error(
                    f"[worldbook] 世界书 JSON 损坏: {path} ({e})。"
                    f"返回空列表 —— 原有条目将无法使用，请检查文件。"
                )
            except Exception as e:
                logger.error(f"[worldbook] 加载世界书 {name} 失败: {type(e).__name__}: {e}")

        self._cache[name] = entries
        return entries

    def _save_book(self, name: str, entries: List[WorldBookEntry]) -> None:
        """保存世界书到文件（原子写入）"""
        path = self.base_dir / f"{name}.json"
        data = {
            "name": name,
            "description": f"世界书: {name}",
            "version": "0.1",
            "entries": [
                {
                    "id": e.id,
                    "title": e.title,
                    "keys": e.keys,
                    "category": e.category,
                    "content": e.content,
                    "priority": e.priority,
                    "enabled": e.enabled,
                    "created_at": e.created_at,
                    "updated_at": e.updated_at,
                }
                for e in entries
            ],
        }
        atomic_write_json(path, data)
        self._cache[name] = entries

    def add_entry(self, worldbook: str, title: str, content: str,
                  keys: Optional[List[str]] = None, category: str = "其他",
                  priority: int = 100) -> WorldBookEntry:
        """添加条目"""
        entries = self.load_book(worldbook)
        entry = WorldBookEntry(
            id=f"wb-{int(time.time())}-{uuid.uuid4().hex[:6]}",
            title=title,
            keys=keys or [title],
            category=category if category in VALID_CATEGORIES else "其他",
            content=content,
            priority=priority,
            worldbook=worldbook,
        )
        entries.append(entry)
        self._save_book(worldbook, entries)
        return entry

    def list_entries(self, worldbook: Optional[str] = None,
                     category: Optional[str] = None,
                     limit: int = 50, offset: int = 0) -> List[WorldBookEntry]:
        """列出条目"""
        if worldbook:
            entries = self.load_book(worldbook)
        else:
            entries = []
            for book in [b["name"] for b in self.list_books()]:
                entries.extend(self.load_book(book))

        if category:
            entries = [e for e in entries if e.category == category]

        entries.sort(key=lambda e: (-e.priority, e.title))
        return entries[offset:offset + limit]

    def search_local(self, query: str, worldbooks: Optional[List[str]] = None,
                     categories: Optional[List[str]] = None,
                     limit: int = 10) -> List[WorldBookEntry]:
        """本地关键词搜索（fallback 方案）"""
        if worldbooks:
            all_entries = []
            for wb in worldbooks:
                all_entries.extend(self.load_book(wb))
        else:
            all_entries = []
            for book in [b["name"] for b in self.list_books()]:
                all_entries.extend(self.load_book(book))

        if categories:
            all_entries = [e for e in all_entries if e.category in categories]

        all_entries = [e for e in all_entries if e.enabled and e.content.strip()]

        # 简单关键词打分（适配中文：不用分词，直接子串匹配）
        query_lower = query.lower()
        scored = []
        for e in all_entries:
            score = 0
            title_lower = e.title.lower()
            keys_lower = [k.lower() for k in e.keys]
            content_lower = e.content.lower()

            # 标题匹配（双向）
            if query_lower == title_lower:
                score += 100
            elif query_lower in title_lower:
                score += 50
            elif title_lower in query_lower:
                score += 60  # 标题是查询的子串，命中更准确

            # 关键词匹配（双向）
            for k in keys_lower:
                if not k:
                    continue
                if query_lower == k:
                    score += 80
                elif k in query_lower:
                    score += 45  # 关键词出现在查询里（更常用的方向）
                elif query_lower in k:
                    score += 30

            # 内容中出现
            if query_lower in content_lower:
                score += 10

            if score > 0:
                scored.append((score, e))

        scored.sort(key=lambda x: (-x[0], -x[1].priority))
        # 附加分数到 entry，供 retriever 做高置信度预过滤判断（跳过向量检索）
        for score, e in scored[:limit]:
            e._search_score = score
        return [e for _, e in scored[:limit]]

    def edit_entry(self, entry_id: str, worldbook: Optional[str] = None,
                   **fields) -> Optional[WorldBookEntry]:
        """编辑条目"""
        # 确定在哪本书里
        if worldbook:
            books = [worldbook]
        else:
            books = [b["name"] for b in self.list_books()]

        for book in books:
            entries = self.load_book(book)
            for i, e in enumerate(entries):
                if e.id == entry_id:
                    for k, v in fields.items():
                        if hasattr(e, k) and k not in ("id", "worldbook", "created_at"):
                            setattr(e, k, v)
                    e.updated_at = time.time()
                    self._save_book(book, entries)
                    return e
        return None

    def delete_entry(self, entry_id: str, worldbook: Optional[str] = None) -> bool:
        """删除条目"""
        if worldbook:
            books = [worldbook]
        else:
            books = [b["name"] for b in self.list_books()]

        for book in books:
            entries = self.load_book(book)
            new_entries = [e for e in entries if e.id != entry_id]
            if len(new_entries) < len(entries):
                self._save_book(book, new_entries)
                return True
        return False

    def import_book(self, name: str, data: Dict) -> int:
        """导入世界书"""
        entries_data = data.get("entries", [])
        entries = []
        for e in entries_data:
            entries.append(WorldBookEntry(
                id=e.get("id", f"imp-{uuid.uuid4().hex[:8]}"),
                title=e.get("title", ""),
                keys=e.get("keys", []),
                category=e.get("category", "其他"),
                content=e.get("content", ""),
                priority=e.get("priority", 100),
                enabled=e.get("enabled", True),
                worldbook=name,
            ))
        self._save_book(name, entries)
        return len(entries)
