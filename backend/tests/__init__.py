import os
import tempfile
import atexit
import shutil
from backend.app.config.settings import settings
from backend.security.database import init_db

# Global isolated test environment root
TEST_TEMP_DIR = tempfile.mkdtemp(prefix="aegis_global_test_")
TEST_GLOBAL_DB_PATH = os.path.join(TEST_TEMP_DIR, "isolated_test_auth.db")

# Point default auth DB path to the isolated test database
settings.AUTH_DB_PATH = TEST_GLOBAL_DB_PATH
init_db()

def _cleanup_test_dir():
    shutil.rmtree(TEST_TEMP_DIR, ignore_errors=True)

atexit.register(_cleanup_test_dir)
