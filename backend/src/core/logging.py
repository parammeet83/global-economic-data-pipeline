"""JSON-lines application logging (TRD §6 step 9, D-40).

Each record becomes one JSON object: ``ts`` (UTC ISO 8601), ``level``, ``logger``,
``message`` plus any fields passed with ``extra={...}`` (for example ``event``,
``run_id``, ``stage``, counts, ``duration_s``). Before output, credentials embedded
in URLs are masked anywhere in the record and values of fields whose names suggest a
secret are replaced, so passwords and connection secrets never reach the logs.
Exceptions are reduced to their type and a redacted message; no traceback text is
written.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

REDACTED = "***"
# scheme://user:password@host -> scheme://user:***@host
URL_CREDENTIALS = re.compile(r"(?P<prefix>[a-zA-Z][a-zA-Z0-9+.\-]*://[^:/@\s]*:)[^@\s]*@")
# password=..., pwd: ..., secret=... inside free text
KEY_VALUE_SECRET = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)(\s*[=:]\s*)([^\s,;&]+)")
SECRET_FIELD = re.compile(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|database_url|dsn|credential)")

# Attributes every LogRecord has; anything else came from ``extra``.
_STANDARD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "taskName"}


def redact(text: str) -> str:
    text = URL_CREDENTIALS.sub(lambda m: f"{m.group('prefix')}{REDACTED}@", text)
    return KEY_VALUE_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)


def _clean(key: str, value: Any) -> Any:
    if SECRET_FIELD.search(key):
        return REDACTED
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _clean(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(key, v) for v in value]
    return redact(str(value))  # UUID, Decimal, datetime, ...


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                entry[key] = _clean(key, value)
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            entry["error_type"] = type(exc).__name__
            entry["error"] = redact(str(exc))[:500]
        return json.dumps(entry, ensure_ascii=False, default=str)


def json_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler._gedp_json = True  # type: ignore[attr-defined]  # marks our handler so it is added once
    return handler


def configure_logging(level: str) -> None:
    """Install one JSON handler on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(h, "_gedp_json", False) for h in root.handlers):
        root.addHandler(json_handler())
