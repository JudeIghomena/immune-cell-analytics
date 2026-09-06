"""Make the repository root importable so tests can import load_data.

load_data.py lives in the root, not in the package, because it must run as a
standalone script. This puts the root on sys.path for the test session.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
