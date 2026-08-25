"""pytest 共享 fixture：加载 worldbook-plugin 为 wp 包 + 隔离 data 目录。

插件目录名是 worldbook-plugin（非标准包名），内部用相对导入，
测试用 importlib 把它挂到 `wp` 包名下。所有测试写 tmp_path，
不污染真实 data/。
"""

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PLUGIN_DIR / "data"


def _load_wp() -> None:
    """把 worldbook-plugin 加载为 wp 包（幂等）"""
    if "wp" in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        "wp", PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wp"] = mod
    spec.loader.exec_module(mod)


@pytest.fixture(scope="session", autouse=True)
def _wp_loaded():
    _load_wp()
    yield


@pytest.fixture(scope="session", autouse=True)
def _rules_book_validated():
    """启动时校验 rules/builtin/ 下所有快照，任一文件 schema 不过就让 pytest 退出。

    这把"快照坏了"提到最早——比在某个测试里发现"spell 找不到"早 100 行。
    """
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-m", "rules.validate", "--quiet"],
        cwd=str(PLUGIN_DIR),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        msg = (
            "规则书快照校验失败！先修复 rules/builtin/ 下的 JSON 才能跑测试。\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )
        pytest.exit(msg, returncode=2)
    yield


@pytest.fixture(scope="session")
def wp():
    """返回已加载的 wp 包（session 级，避免 ScopeMismatch）"""
    return sys.modules["wp"]


@pytest.fixture
def data_dir(wp, tmp_path):
    """隔离的 data 目录（复制模板，不污染真实 data/）"""
    d = tmp_path / "data"
    d.mkdir()
    shutil.copytree(DATA_DIR / "templates", d / "templates")
    return d


@pytest.fixture
def make_state(wp, data_dir):
    """StateManager 工厂：data_dir + 可选 campaign/template"""
    from wp.state import StateManager

    def _make(template: str = "dnd5e", campaign: str = "test"):
        sm = StateManager(data_dir, campaign_name=campaign, template_name=template)
        sm._state = None
        sm.load()  # 确保模板创建 state.json
        return sm

    return _make


@pytest.fixture
def patched_data_dir(wp, data_dir, monkeypatch):
    """monkeypatch config.get_plugin_data_dir → 隔离目录

    让 app_context.build() 等用真实路径的组件也指向 tmp，
    避免测试污染真实 data/。
    """
    monkeypatch.setattr("wp.config.get_plugin_data_dir", lambda: data_dir)
    return data_dir
