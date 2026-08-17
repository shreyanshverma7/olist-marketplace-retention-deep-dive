"""Shared fixtures for the test suite.

DB_PATH mirrors common.py / analysis/statistical_tests.py's own
Path(__file__).resolve().parent.parent / "database" / "olist.db" pattern, so
tests read the same committed, deterministic database the app and the CLI
stats pass use -- not a synthetic stand-in -- which is what makes the
golden-value regression tests in test_statistical_tests.py and
test_sql_deliverables.py legitimate (fixed dataset -> fixed expected output).
"""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database" / "olist.db"


@pytest.fixture(scope="session")
def db_conn():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    yield conn
    conn.close()


def load_module(name: str, path: Path):
    """Import a script file that isn't a valid dotted module path (e.g. a
    numeric-prefixed Streamlit page like pages/5_Revenue_Concentration.py) so
    its top-level functions become directly testable.

    Executes the file's full top-level code, same as Streamlit itself would --
    confirmed safe outside a real app: st.* calls and @st.cache_data /
    @st.cache_resource degrade to silent no-ops/stub objects (with stderr
    warnings only) rather than raising, so pages that build/render charts on
    import still complete and leave their module-level functions callable.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def page5():
    return load_module("page5_revenue_concentration", ROOT / "streamlit_app" / "pages" / "5_Revenue_Concentration.py")


@pytest.fixture(scope="session")
def page8():
    return load_module("page8_statistical_tests", ROOT / "streamlit_app" / "pages" / "8_Statistical_Tests.py")
