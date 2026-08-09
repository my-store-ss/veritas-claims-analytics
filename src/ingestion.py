
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def discover_json_files(folder: str) -> List[Path]:
    return sorted(Path(folder).glob("*.json"))

def load_json_file(path: Path) -> Dict[str, Any]:
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Malformed JSON: {exc}") from exc

    if not isinstance(data, dict) or "data" not in data:
        raise ValueError("JSON does not contain the expected top-level 'data' object")
    return data

def ingest_folder(folder: str):
    results = []
    for path in discover_json_files(folder):
        raw = path.read_bytes()
        file_hash = sha256_bytes(raw)
        try:
            payload = load_json_file(path)
            results.append({
                "path": path,
                "payload": payload,
                "file_hash": file_hash,
                "error": None,
            })
        except ValueError as exc:
            logger.exception("Failed to ingest %s", path)
            results.append({
                "path": path,
                "payload": None,
                "file_hash": file_hash,
                "error": str(exc),
            })
    return results
