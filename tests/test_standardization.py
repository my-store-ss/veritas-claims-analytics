
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_configs
from src.standardization import (
    normalize_test_name, parse_numeric, parse_range, normalize_date,
    normalize_gender, normalize_age, classify_result, normalize_medicine
)

def test_typo_and_alias_normalization():
    cfg = load_configs()["test_mapping"]
    name, method, score = normalize_test_name("aemoglobin", cfg)
    assert name == "HAEMOGLOBIN"
    assert method in {"fuzzy_dictionary", "exact_dictionary"}
    assert score > 0.78

def test_numeric_conversion_with_units():
    value, text, status = parse_numeric("13.7 g/dl")
    assert value == 13.7 and status == "numeric"

def test_multi_value_is_not_silently_collapsed():
    value, text, status = parse_numeric("Neutrophil - 72.4, Lymphocyte - 23.5")
    assert value is None and status == "multi_value"

def test_range_parser():
    assert parse_range("8.0 - 23.0")[:2] == (8.0, 23.0)
    assert parse_range("<50")[:2] == (None, 50.0)

def test_demographics():
    assert normalize_gender("M") == "Male"
    assert normalize_date("08/Oct/2025") == "2025-10-08"
    age, text = normalize_age("33Y11M265D")
    assert age > 33

def test_validation_classes():
    assert classify_result(14, 13, 17) == "Within Range"
    assert classify_result(10, 13, 17) == "Below Range"
    assert classify_result(200, 13, 17) == "Outlier"

def test_medicine_mapping():
    original, generic = normalize_medicine("TAB. AZITHRAL 500 mg", load_configs()["medicines"])
    assert original.startswith("TAB.")
    assert generic == "azithromycin"
