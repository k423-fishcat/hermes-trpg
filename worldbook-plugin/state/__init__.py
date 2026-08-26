"""state/ 包 — 跑团状态管理（模板驱动 + 多战役）

v2.5 之前是单一 state.py（22 个方法、4 件事混在一起）。
v2.5 起拆为子包：

- state/_core.py         模板加载 + 状态 I/O（load/get/update/undo）
- state/_campaigns.py    战役生命周期（create/switch/list/delete）
- state/_snapshots.py    版本快照 + 命名快照 + 回滚
- state/_rules_dnd5e.py  D&D 5e 规则（属性/技能调整值）

StateManager 保留为薄 facade，对外 API 完全兼容，60+ 调用方零修改。
新增规则（D&D 4e / COC）只需加 _rules_dnd4e.py / _rules_coc7e.py。

核心原则（不变）：
- 模板与数据解耦：DnD/COC/其他系统各有模板
- 多战役切换：每个战役独立目录
- 单入口更新：所有变更走 update()，自动版本号 + Event Log + 回滚
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..schema import validate_and_fill, validate_write  # re-exported for backward compat

from . import _core, _campaigns, _snapshots, _rules_dnd5e, _rules_dnd3r, _rules_coc7e
from ._core import _format_status_summary

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# 全局单例（v2.5 加，保留向后兼容）
# ----------------------------------------------------------------

_default_state_mgr: Optional["StateManager"] = None


def get_default_state_mgr() -> "StateManager":
    """获取（或懒加载）全局默认 StateManager 单例"""
    global _default_state_mgr
    if _default_state_mgr is None:
        from ..config import get_plugin_data_dir
        _default_state_mgr = StateManager(
            get_plugin_data_dir(),
            campaign_name="灰港失踪案",
            template_name="dnd5e",
        )
    return _default_state_mgr


def reset_default_state_mgr() -> None:
    """重置全局单例（仅供测试）"""
    global _default_state_mgr
    _default_state_mgr = None


# ----------------------------------------------------------------
# StateManager — 薄 facade，所有方法委托给 4 个 ops 模块
# ----------------------------------------------------------------

class StateManager:
    """跑团状态管理器（Facade）

    实际逻辑分散在 state/_core.py / _campaigns.py / _snapshots.py / _rules_dnd5e.py。
    本类只保留：
    - 构造（路径 + 名字）
    - 路径属性（campaign_dir/state_file/history_dir/named_snapshots_dir）
    - 委托方法（每个 public 方法 = 1 行 delegate）
    """

    def __init__(self, data_dir: Path, campaign_name: str = "default",
                 template_name: str = "dnd5e"):
        self.data_dir = Path(data_dir)
        self.templates_dir = self.data_dir / "templates"
        self.campaigns_dir = self.data_dir / "campaigns"
        self.campaign_name = campaign_name
        self.template_name = template_name
        self._state = None
        self._template = None
        # 写互斥锁：Hermes 用线程池并发执行多个工具，两个工具同时 update()
        # 会导致「读-改-写」竞争（后读的旧版本覆盖先写的新版本）。
        # RLock 可重入，包裹 load+modify+save 全过程，串行化同战役的写。
        self._lock = threading.RLock()

    # ----------------------------------------------------------------
    # 路径属性
    # ----------------------------------------------------------------

    @property
    def campaign_dir(self) -> Path:
        return self.campaigns_dir / self.campaign_name

    @property
    def state_file(self) -> Path:
        return self.campaign_dir / "state.json"

    @property
    def history_dir(self) -> Path:
        return self.campaign_dir / "history"

    @property
    def named_snapshots_dir(self) -> Path:
        return self.campaign_dir / "snapshots"

    # ----------------------------------------------------------------
    # 模板 (→ _core)
    # ----------------------------------------------------------------

    def load_template(self, name: str) -> dict:
        return _core.load_template(self, name)

    def list_templates(self) -> List[Dict]:
        return _core.list_templates(self)

    # ----------------------------------------------------------------
    # 战役管理 (→ _campaigns)
    # ----------------------------------------------------------------

    def create_campaign(self, name: str, template: str = "dnd5e",
                        display_name: str = "") -> Dict[str, Any]:
        return _campaigns.create(self, name, template, display_name)

    def switch_campaign(self, name: str) -> Dict[str, Any]:
        return _campaigns.switch(self, name)

    def list_campaigns(self) -> List[Dict]:
        return _campaigns.list_all(self)

    def delete_campaign(self, name: str) -> Dict[str, Any]:
        return _campaigns.delete(self, name)

    # ----------------------------------------------------------------
    # 核心 I/O (→ _core)
    # ----------------------------------------------------------------

    def load(self) -> dict:
        return _core.load(self)

    def get(self, path: str = "") -> Any:
        return _core.get(self, path)

    def update(self, changes: Dict[str, Any], reason: str = "",
               actor: str = "DM", snapshot: bool = True) -> Dict[str, Any]:
        with self._lock:
            return _core.update(self, changes, reason, actor, snapshot=snapshot)

    def undo(self, steps: int = 1) -> Dict[str, Any]:
        with self._lock:
            return _core.undo(self, steps)

    # ----------------------------------------------------------------
    # 快照 (→ _snapshots)
    # ----------------------------------------------------------------

    def save_named_snapshot(self, name: str, reason: str = "") -> Dict[str, Any]:
        with self._lock:
            return _snapshots.save_named(self, name, reason)

    def list_named_snapshots(self) -> List[Dict[str, Any]]:
        return _snapshots.list_named(self)

    def rollback_to_snapshot(self, snapshot_file: str) -> Dict[str, Any]:
        with self._lock:
            return _snapshots.rollback(self, snapshot_file)

    # ----------------------------------------------------------------
    # 规则适配 (按 template_name 自动路由)
    # ----------------------------------------------------------------

    def _rules_adapter(self):
        """根据当前 template_name 返回对应的规则适配器

        路由表：
        - dnd5e → _rules_dnd5e
        - dnd3r / dnd3.5 → _rules_dnd3r
        - coc / coc7e → _rules_coc7e
        其它回退到 dnd5e
        """
        t = (self.template_name or "").lower()
        if t in ("dnd3r", "dnd3.5", "dnd35e"):
            return _rules_dnd3r
        if t in ("coc", "coc7e", "coc7"):
            return _rules_coc7e
        return _rules_dnd5e

    def get_modifier(self, ability: str) -> int:
        return self._rules_adapter().get_modifier(self, ability)

    def get_skill_modifier(self, skill_name: str) -> int:
        return self._rules_adapter().get_skill_modifier(self, skill_name)

    def get_bab(self) -> int:
        """D&D 3.5 基础攻击加值。其他系统返回 0。"""
        if self._rules_adapter() is _rules_dnd3r:
            return _rules_dnd3r.get_bab(self)
        return 0

    def get_saving_throw(self, save_key: str) -> int:
        """D&D 3.5 豁免值（fortitude/reflex/will）。其他系统返回 0。"""
        if self._rules_adapter() is _rules_dnd3r:
            return _rules_dnd3r.get_saving_throw(self, save_key)
        return 0

    def get_derived_stats(self) -> Dict[str, int]:
        """COC 7e 派生属性（HP/MP/SAN/LUCK/IDEA/KNOWLEDGE/DODGE）。其他系统返回空 dict。"""
        if self._rules_adapter() is _rules_coc7e:
            return _rules_coc7e.get_derived_stats(self)
        return {}


__all__ = [
    "StateManager",
    "get_default_state_mgr",
    "reset_default_state_mgr",
    "validate_and_fill",
    "validate_write",
]
