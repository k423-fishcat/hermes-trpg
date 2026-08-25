"""世界书管理工具

提供给 AI 调用的工具函数，通过插件工具注册机制暴露。
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from .store import WorldBookStore, VALID_CATEGORIES
from .config import load_config, save_config, atomic_write_json

logger = logging.getLogger(__name__)


class WorldBookManager:
    """世界书管理器"""

    def __init__(self, store: WorldBookStore, config: dict):
        self.store = store
        self.config = config

    def add_entry(self, title: str, content: str,
                  keys: Optional[List[str]] = None,
                  category: str = "其他",
                  worldbook: Optional[str] = None,
                  priority: int = 100) -> str:
        """添加世界书条目

        Args:
            title: 条目标题
            content: 条目详细内容
            keys: 关键词列表，用于触发匹配
            category: 分类（地点/NPC/怪物/物品/组织/规则/剧情/其他）
            worldbook: 所属世界书，默认使用第一个启用的
            priority: 优先级，越高越先注入

        Returns:
            添加结果信息
        """
        if category not in VALID_CATEGORIES:
            return f"错误：无效分类 '{category}'。有效分类：{', '.join(sorted(VALID_CATEGORIES))}"

        wb = worldbook or (self.config.get("enabled_books", ["default"])[0] if self.config.get("enabled_books") else "default")

        if not keys:
            keys = [title]

        entry = self.store.add_entry(
            worldbook=wb,
            title=title,
            content=content,
            keys=keys,
            category=category,
            priority=priority,
        )

        return f"✅ 已添加条目「{title}」（ID: {entry.id}，分类: {category}，世界书: {wb}）"

    def list_entries(self, worldbook: Optional[str] = None,
                     category: Optional[str] = None,
                     limit: int = 20, offset: int = 0) -> str:
        """列出世界书条目

        Args:
            worldbook: 世界书名，不填=全部
            category: 分类过滤
            limit: 条数
            offset: 偏移

        Returns:
            条目列表文本
        """
        entries = self.store.list_entries(
            worldbook=worldbook,
            category=category,
            limit=limit,
            offset=offset,
        )

        if not entries:
            return "（没有条目）"

        lines = [f"共找到 {len(entries)} 条（显示 {offset+1}-{offset+len(entries)}）：", ""]
        for i, e in enumerate(entries, 1):
            status = "✅" if e.enabled else "❌"
            content_preview = e.content[:50] + "..." if len(e.content) > 50 else e.content
            lines.append(f"{i}. {status} [{e.category}] {e.title} (ID: {e.id}, 优先级: {e.priority})")
            if content_preview.strip():
                lines.append(f"   {content_preview}")
            lines.append("")

        return "\n".join(lines)

    def search_entries(self, query: str,
                       worldbook: Optional[str] = None,
                       limit: int = 10) -> str:
        """搜索世界书条目

        Args:
            query: 搜索关键词
            worldbook: 限定世界书
            limit: 最多返回条数

        Returns:
            搜索结果
        """
        entries = self.store.search_local(
            query,
            worldbooks=[worldbook] if worldbook else None,
            limit=limit,
        )

        if not entries:
            return f"没有找到与「{query}」相关的条目。"

        lines = [f"搜索「{query}」，找到 {len(entries)} 条：", ""]
        for i, e in enumerate(entries, 1):
            lines.append(f"{i}. [{e.category}] {e.title}（{e.worldbook}）")
            content_preview = e.content[:80] + "..." if len(e.content) > 80 else e.content
            if content_preview.strip():
                lines.append(f"   {content_preview}")
            lines.append("")

        return "\n".join(lines)

    def edit_entry(self, entry_id: str,
                   title: Optional[str] = None,
                   content: Optional[str] = None,
                   keys: Optional[List[str]] = None,
                   category: Optional[str] = None,
                   priority: Optional[int] = None,
                   enabled: Optional[bool] = None) -> str:
        """编辑世界书条目

        Args:
            entry_id: 条目ID
            title: 新标题
            content: 新内容
            keys: 新关键词列表
            category: 新分类
            priority: 新优先级
            enabled: 是否启用

        Returns:
            编辑结果
        """
        fields = {}
        if title is not None:
            fields["title"] = title
        if content is not None:
            fields["content"] = content
        if keys is not None:
            fields["keys"] = keys
        if category is not None:
            if category not in VALID_CATEGORIES:
                return f"错误：无效分类 '{category}'。有效分类：{', '.join(sorted(VALID_CATEGORIES))}"
            fields["category"] = category
        if priority is not None:
            fields["priority"] = priority
        if enabled is not None:
            fields["enabled"] = enabled

        if not fields:
            return "错误：没有指定要修改的字段。"

        entry = self.store.edit_entry(entry_id, **fields)
        if entry:
            return f"✅ 已更新条目「{entry.title}」"
        return f"❌ 未找到 ID 为 '{entry_id}' 的条目。"

    def delete_entry(self, entry_id: str) -> str:
        """删除世界书条目

        Args:
            entry_id: 条目ID

        Returns:
            删除结果
        """
        if self.store.delete_entry(entry_id):
            return f"✅ 已删除条目 '{entry_id}'"
        return f"❌ 未找到 ID 为 '{entry_id}' 的条目。"

    def list_books(self) -> str:
        """列出所有世界书"""
        books = self.store.list_books()
        if not books:
            return "（没有世界书）"

        lines = [f"共 {len(books)} 个世界书：", ""]
        enabled = set(self.config.get("enabled_books", []))
        for b in books:
            status = "✅ 已启用" if b["name"] in enabled else "⏸️ 未启用"
            lines.append(f"- {b['name']} {status}（{b['entry_count']} 条）{b.get('description', '')}")

        return "\n".join(lines)

    def enable_book(self, name: str, enabled: bool = True) -> str:
        """启用或禁用世界书

        Args:
            name: 世界书名
            enabled: True=启用，False=禁用
        """
        cfg = load_config()
        books = list(cfg.get("enabled_books", []))

        if enabled:
            if name not in books:
                books.append(name)
            action = "启用"
        else:
            if name in books:
                books.remove(name)
            action = "禁用"

        cfg["enabled_books"] = books
        save_config(cfg)
        self.config = cfg
        return f"✅ 已{action}世界书「{name}」"

    def import_book(self, file_path: str, name: Optional[str] = None) -> str:
        """导入世界书

        Args:
            file_path: JSON 文件路径
            name: 世界书名称，不填则用文件名

        Returns:
            导入结果
        """
        path = Path(file_path)
        if not path.exists():
            return f"❌ 文件不存在：{file_path}"

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"❌ 读取文件失败：{e}"

        book_name = name or data.get("name") or path.stem
        count = self.store.import_book(book_name, data)

        # 自动启用
        cfg = load_config()
        books = list(cfg.get("enabled_books", []))
        if book_name not in books:
            books.append(book_name)
            cfg["enabled_books"] = books
            save_config(cfg)
            self.config = cfg

        return f"✅ 导入成功：「{book_name}」，共 {count} 条，已启用"

    def export_book(self, name: str, output_path: str) -> str:
        """导出世界书

        Args:
            name: 世界书名
            output_path: 输出文件路径

        Returns:
            导出结果
        """
        entries = self.store.load_book(name)
        if not entries:
            return f"❌ 世界书「{name}」不存在或为空。"

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
                }
                for e in entries
            ],
        }

        try:
            atomic_write_json(Path(output_path), data)
            return f"✅ 已导出 {len(entries)} 条到 {output_path}"
        except Exception as e:
            return f"❌ 导出失败：{e}"

    def status(self) -> str:
        """查看世界书系统状态"""
        books = self.store.list_books()
        enabled = self.config.get("enabled_books", [])
        total_entries = sum(b["entry_count"] for b in books)

        lines = [
            "🌍 世界书系统状态",
            "=" * 30,
            f"后端: {self.config.get('search_backend', 'openviking')}",
            f"自动注入: {'✅ 开启' if self.config.get('auto_inject') else '⏸️ 关闭'}",
            f"每次最多注入: {self.config.get('max_entries', 5)} 条 / {self.config.get('max_chars', 3000)} 字符",
            f"最低相似度: {self.config.get('min_similarity', 0.6)}",
            f"回看消息: {self.config.get('lookback_messages', 3)} 条",
            "",
            f"世界书: {len(books)} 个 / {total_entries} 条",
        ]

        for b in books:
            status = "✅" if b["name"] in enabled else "⏸️"
            lines.append(f"  {status} {b['name']} ({b['entry_count']} 条)")

        return "\n".join(lines)
