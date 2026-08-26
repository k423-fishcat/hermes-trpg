"""世界书工具"""

from .registry import ToolRegistry


def register(reg: ToolRegistry, store):
    @reg.tool(
        name="trpg_worldbook_search",
        description="搜索世界书条目。按关键词查找相关设定、人物、地点、剧情等。",
        schema={
            "name": "trpg_worldbook_search",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "worldbook": {"type": "string", "description": "限定某个世界书（留空搜索全部）", "default": ""},
                    "limit": {"type": "integer", "description": "最多返回条数", "default": 10},
                },
                "required": ["query"],
            },
        },
        emoji="📖",
    )
    def search(args):
        from ..manager import WorldBookManager
        mgr = WorldBookManager(store, {})
        return mgr.search_entries(
            args.get("query", ""),
            worldbook=args.get("worldbook") or None,
            limit=args.get("limit", 10),
        )
