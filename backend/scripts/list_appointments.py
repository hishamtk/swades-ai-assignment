"""Print appointments as JSON for the Next.js API route."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from booking import list_appointments

if __name__ == "__main__":
    print(json.dumps(list_appointments()))
