"""世界书插件配置管理"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "auto_inject": True,
    "max_entries": 5,
    "max_chars": 3000,
    "min_similarity": 0.6,
    "lookback_messages": 3,
    "enabled_books": ["灰港-DnD5e"],
    "categories": [],
    "cache_ttl": 60,
    "search_backend": "openviking",
    "inject_header": "## 世界书相关设定",
}


def atomic_write_json(path: Path, data: Any) -> None:
    """原子写入 JSON：写临时文件 → fsync → os.replace

    保证崩溃场景下不会产生半截文件（Windows 下 os.replace 也是原子的）。
    这是所有 JSON 写文件的统一入口，替代裸 json.dump / Path.write_text。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def get_plugin_data_dir() -> Path:
    """获取插件数据目录"""
    return Path(__file__).parent / "data"


def get_config_path() -> Path:
    return get_plugin_data_dir() / "config.json"


def load_config() -> Dict[str, Any]:
    """加载配置，不存在则返回默认配置

    配置损坏会记录错误日志并回退默认（不静默吞错）。
    """
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(user_cfg)
            return cfg
        except json.JSONDecodeError as e:
            logger.error(
                f"[config] 配置文件损坏: {config_path} ({e})，回退到默认配置。"
                f"用户自定义配置（如 enabled_books）将丢失，请手动修复或删除该文件。"
            )
        except Exception as e:
            logger.error(f"[config] 加载配置失败: {e}，回退到默认配置")
    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """保存配置（原子写入）"""
    atomic_write_json(get_config_path(), config)


def get_worldbooks_dir() -> Path:
    return get_plugin_data_dir() / "worldbooks"
