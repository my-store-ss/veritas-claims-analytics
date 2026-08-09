
import difflib
import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

DATE_FORMATS = [
    "%d-%m-%Y", "%d/%m/%Y", "%d/%b/%Y", "%d/%B/%Y",
    "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y",
]

def norm_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())

def compact(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", norm_text(value).lower())

def normalize_date(value) -> Optional[str]:
    text = norm_text(value)
    if not text or text.upper() in {"N/A", "NA", "NULL", "DD/MM/YYYY"}:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None

def normalize_age(value) -> Tuple[Optional[float], str]:
    text = norm_text(value)
    if not text:
        return None, ""
    # Structured age such as 33Y11M265D -> decimal years.
    m = re.fullmatch(r"(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?", text.upper())
    if m and any(m.groups()):
        years = int(m.group(1) or 0)
        months = int(m.group(2) or 0)
        days = int(m.group(3) or 0)
        return round(years + months / 12 + days / 365.25, 4), text
    try:
        return float(text), text
    except ValueError:
        return None, text

def normalize_gender(value) -> Optional[str]:
    text = norm_text(value).lower()
    mapping = {"m": "Male", "male": "Male", "f": "Female", "female": "Female",
               "o": "Other", "other": "Other"}
    return mapping.get(text, norm_text(value) or None)

def normalize_test_name(raw_name: str, mapping: Dict[str, Any]) -> Tuple[str, str, float]:
    original = norm_text(raw_name)
    if not original:
        return "", "missing", 0.0
    key = compact(original)
    candidates = []
    for canonical, variants in mapping["canonical_tests"].items():
        for variant in [canonical] + variants:
            candidates.append((compact(variant), canonical))
    exact = {k: c for k, c in candidates}
    if key in exact:
        return exact[key], "exact_dictionary", 1.0

    # Fuzzy match is intentionally conservative; unmatched values remain visible.
    best = difflib.get_close_matches(key, [k for k, _ in candidates], n=1, cutoff=mapping.get("fuzzy_threshold", .78))
    if best:
        best_key = best[0]
        canonical = next(c for k, c in candidates if k == best_key)
        score = difflib.SequenceMatcher(None, key, best_key).ratio()
        return canonical, "fuzzy_dictionary", round(score, 4)
    return original, "unmatched", 0.0

def normalize_unit(raw_unit: str, result_value: Optional[float], unit_mapping: Dict[str, Any]):
    original = norm_text(raw_unit)
    key = original.lower().replace(" ", "")
    if key in unit_mapping:
        cfg = unit_mapping[key]
        factor = float(cfg.get("factor", 1))
        return cfg["canonical"], (result_value * factor if result_value is not None else None), original
    return original or None, result_value, original or None

def parse_numeric(value: Any):
    """Return (numeric value, original text, status).
    status: numeric, empty, non_numeric, multi_value.
    A single numeric token embedded in text is accepted; multiple tokens are
    retained as text to avoid silently selecting one value from a composite.
    """
    text = norm_text(value)
    if not text:
        return None, text, "empty"
    # Comma-separated thousands are allowed.
    cleaned = text.replace(",", "")
    nums = re.findall(r"(?<![A-Za-z])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![A-Za-z])", cleaned)
    if len(nums) == 1:
        try:
            return float(nums[0]), text, "numeric"
        except ValueError:
            pass
    if len(nums) > 1:
        return None, text, "multi_value"
    return None, text, "non_numeric"

def parse_range(text: Any):
    value = norm_text(text)
    if not value:
        return None, None, ""
    cleaned = value.replace(",", "")
    # Two-sided range
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:-|to)\s*(-?\d+(?:\.\d+)?)", cleaned, re.I)
    if m:
        return float(m.group(1)), float(m.group(2)), value
    # <x / <=x / >x / >=x
    m = re.search(r"^(?:less than|<|<=)\s*(-?\d+(?:\.\d+)?)$", cleaned, re.I)
    if m:
        return None, float(m.group(1)), value
    m = re.search(r"^(?:greater than|>|>=)\s*(-?\d+(?:\.\d+)?)$", cleaned, re.I)
    if m:
        return float(m.group(1)), None, value
    # Exact numeric reference
    try:
        n = float(cleaned)
        return n, n, value
    except ValueError:
        return None, None, value

def normalize_medicine(name: str, medicine_mapping: Dict[str, Any]) -> Tuple[str, str]:
    original = norm_text(name)
    if not original or original.upper() in {"N/A", "NA"}:
        return original, ""
    # Strip dosage/form prefixes and strengths for dictionary lookup.
    cleaned = re.sub(r"^(TAB\.?|CAP\.?|INJ\.?|SYP\.?|POWDER|AMP\.?)\s*", "", original, flags=re.I)
    cleaned = re.sub(r"\s*[-–]\s*\d+(?:\.\d+)?\s*(?:MG|ML|G|MCG)?", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+\d+(?:\.\d+)?\s*(?:MG|ML|G|MCG)\b", "", cleaned, flags=re.I)
    key = cleaned.upper().strip()
    for brand, generic in medicine_mapping.get("mappings", {}).items():
        if key == brand.upper() or key.startswith(brand.upper() + " "):
            return original, generic
    return original, ""

def classify_result(value, low, high, expected_numeric=True, outlier_low=0.1, outlier_high=10):
    if value is None:
        return "Invalid" if expected_numeric else "Invalid"
    if low is not None and value < low * outlier_low:
        return "Outlier"
    if high is not None and value > high * outlier_high:
        return "Outlier"
    if low is not None and value < low:
        return "Below Range"
    if high is not None and value > high:
        return "Above Range"
    return "Within Range"
