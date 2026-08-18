import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.types import EventDict, Processor

# Regex matching email addresses to redact any residual local-parts or full emails
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b",
    re.IGNORECASE,
)


class RedactPIIProcessor:
    """Structlog processor that automatically redacts any email addresses in log values.

    If an email pattern is found, it strips the local-part and leaves only [REDACTED_LOCAL_PART]@domain.com.
    """

    def __call__(self, logger: structlog.types.WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        return self._redact_dict(event_dict)

    def _redact_value(self, val: Any) -> Any:
        if isinstance(val, str):
            # Replace local-part with REDACTED while preserving domain for debugging context
            return EMAIL_REGEX.sub(r"[REDACTED_LOCAL_PART]@\1", val)
        elif isinstance(val, dict):
            return self._redact_dict(val)
        elif isinstance(val, list):
            return [self._redact_value(item) for item in val]
        return val

    def _redact_dict(self, d: MutableMapping[str, Any]) -> EventDict:
        for k, v in list(d.items()):
            if k in ("email", "raw_email", "user_email", "local_part", "password", "secret", "token"):
                # Remove sensitive key altogether or scrub
                if k in ("email", "raw_email", "user_email"):
                    d[k] = "[REDACTED_PII]"
                elif k in ("password", "secret", "token"):
                    d[k] = "[REDACTED_SECRET]"
            else:
                d[k] = self._redact_value(v)
        return dict(d)


def configure_logging(log_level: str = "INFO") -> None:
    """Configures structlog for production zero-PII JSON output."""
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        RedactPIIProcessor(),
    ]

    level_num = getattr(sys.modules.get("logging", None), log_level.upper(), 20)

    structlog.configure(
        processors=shared_processors
        + [
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "email_verifier") -> Any:
    return structlog.get_logger(name)
