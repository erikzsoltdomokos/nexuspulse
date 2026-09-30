import os
import sys
import tempfile
from pathlib import Path

# Isolate every test run in its own data dir, before nexuspulse.config is imported.
_TMP = tempfile.mkdtemp(prefix="nexuspulse-test-", dir=os.environ.get("TMPDIR"))
os.environ["NEXUSPULSE_DATA_DIR"] = _TMP
os.environ["NEXUSPULSE_AUTO_BOOTSTRAP"] = "0"
os.environ["RIOT_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
