from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_rules(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
