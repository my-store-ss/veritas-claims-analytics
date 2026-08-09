
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

def load_json(name: str):
    with open(ROOT / "config" / name, "r", encoding="utf-8") as f:
        return json.load(f)

def load_configs():
    return {
        "test_mapping": load_json("test_name_mapping.json"),
        "units": load_json("unit_mapping.json"),
        "medicines": load_json("medicine_mapping.json"),
        "ranges": load_json("reference_ranges.json"),
    }
