import pytest

from app.core.logging import RedactPIIProcessor
from app.core.security import hash_identifier


@pytest.mark.security
def test_pii_redactor_processor() -> None:
    processor = RedactPIIProcessor()

    sample_dict = {
        "event": "User logged in with confidential_user@example.com",
        "email": "raw_user@disposable.com",
        "details": {"nested": "contact john.doe@domain.org for info"},
    }

    cleaned = processor(None, "info", sample_dict.copy())

    # Raw emails must be redacted
    assert "confidential_user" not in str(cleaned)
    assert "[REDACTED_LOCAL_PART]@example.com" in cleaned["event"]
    assert cleaned["email"] == "[REDACTED_PII]"
    assert "[REDACTED_LOCAL_PART]@domain.org" in cleaned["details"]["nested"]


@pytest.mark.security
def test_hash_identifier_salt_privacy() -> None:
    ip1 = "192.168.1.100"
    hash1 = hash_identifier(ip1)
    hash2 = hash_identifier(ip1)

    # Deterministic for same session/salt
    assert hash1 == hash2
    # Irreversible sha256 hex string
    assert len(hash1) == 64
    assert ip1 not in hash1
