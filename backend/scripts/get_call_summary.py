"""Print the latest call summary for a room as JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from booking import get_call_summary

if __name__ == "__main__":
    room_name = sys.argv[1] if len(sys.argv) > 1 else ""
    print(json.dumps(get_call_summary(room_name)))
