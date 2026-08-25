"""tools/ 包的注册中心：ToolRegistry + @tool 装饰器

替代 v2.5 之前 12 个 register_xxx_tools 函数 + wrap-counting 模式。
新流程：
1. ToolRegistry 包装 ctx，自动累加工具数
2. @tool 装饰器把工具注册到 registry（不再需要每写一个工具就 20 行 ctx.register_tool 模板）
3. registry.register_all() 一次性调 ctx.register_tool 全部注册

用法（每个 tools/* 文件）：
    from .registry import ToolRegistry, tool_schema

    def register(reg: ToolRegistry, state, chronicle):
        @reg.tool("trpg_state_get", "获取状态", schema=GET_SCHEMA, emoji="📊")
        def get(args): return _get(state, args.get("path", ""))

        @reg.tool("trpg_state_update", "更新状态", schema=UPDATE_SCHEMA, emoji="✏️")
        def update(args): return _update(state, ...)

外部调用（__init__.py）：
    from tools.registry import ToolRegistry
    reg = ToolRegistry(ctx)
    from tools.state import register as reg_state
    reg_state(reg, state)
    from tools.combat import register as reg_combat
    reg_combat(reg, state, combat_tracker)
    print(f"注册了 {len(reg)} 个工具")  # 自动统计
"""

from __future__ import annotations

from typing import Any, Callable


class ToolRegistry:
    """MCP 工具注册中心

    包装 ctx.register_tool，自动累加工具数。
    所有 tools/*.py 通过 @reg.tool() 装饰器注册工具。
    最后调 register_all() 一次性推给 ctx。
    """

    def __init__(self, ctx):
        self._ctx = ctx
        self._tools: list[dict] = []

    def __len__(self) -> int:
        return len(self._tools)

    def tool(
        self,
        name: str,
        description: str,
        schema: dict,
        emoji: str = "",
        toolset: str = "trpg",
    ) -> Callable:
        """@reg.tool(...) 装饰器

        把被装饰的函数注册为 MCP 工具。函数签名必须是 (args: dict) -> str。
        """
        def decorator(func: Callable) -> Callable:
            self._tools.append({
                "name": name,
                "toolset": toolset,
                "schema": schema,
                "handler": func,
                "description": description,
                "emoji": emoji,
            })
            return func
        return decorator

    def register_all(self) -> int:
        """把所有累积的工具推给 ctx，返回注册数"""
        for t in self._tools:
            self._ctx.register_tool(**t)
        return len(self._tools)


__all__ = ["ToolRegistry"]
