from __future__ import annotations

import os
import tempfile
from pathlib import Path

_db_dir = Path(tempfile.mkdtemp(prefix="jarvis-test-"))
os.environ["DATABASE_URL"] = "sqlite:///" + (_db_dir / "leads.db").as_posix()
os.environ["DASHBOARD_PASSWORD"] = "test-password"
os.environ["APP_ENV"] = "development"
