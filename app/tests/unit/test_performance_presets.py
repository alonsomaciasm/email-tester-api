"""Unit tests for Performance Presets and Engine Feature Flags."""

import pytest

from app.core.config import Settings
from app.domain.heuristics import compute_levenshtein_distance


@pytest.mark.unit
def test_ultra_combined_preset_configuration() -> None:
    """Verifies ultra_combined preset sets all C/Rust engines."""
    s = Settings(PERFORMANCE_PRESET="ultra_combined")
    assert s.JSON_SERIALIZER_ENGINE == "orjson"
    assert s.TYPO_ENGINE_BACKEND == "rapidfuzz"
    assert s.REDIS_PARSER == "hiredis"


@pytest.mark.unit
def test_baseline_python_preset_configuration() -> None:
    """Verifies baseline_python preset sets all pure Python fallbacks."""
    s = Settings(PERFORMANCE_PRESET="baseline_python")
    assert s.JSON_SERIALIZER_ENGINE == "std_json"
    assert s.TYPO_ENGINE_BACKEND == "python_native"
    assert s.REDIS_PARSER == "python"


@pytest.mark.unit
def test_levenshtein_distance_backends_parity() -> None:
    """Verifies parity between rapidfuzz and python_native Levenshtein distance calculations."""
    from app.core.config import settings

    # RapidFuzz calculation
    settings.TYPO_ENGINE_BACKEND = "rapidfuzz"
    dist_rf = compute_levenshtein_distance("gmai.com", "gmail.com")

    # Python native calculation
    settings.TYPO_ENGINE_BACKEND = "python_native"
    dist_py = compute_levenshtein_distance("gmai.com", "gmail.com")

    assert dist_rf == dist_py == 1

    # Restore default
    settings.TYPO_ENGINE_BACKEND = "rapidfuzz"
