"""PHI redaction for Python logging records."""

import logging
import re

_REDACTION_PATTERNS = (
    (re.compile(r"\b(?:PT[_-]?\d{3,}|MS-[A-Z]+-\d{3,})\b", re.IGNORECASE), "[REDACTED_MEMBER_ID]"),
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b"), "[REDACTED_DOB]"),
    (
        re.compile(r"\b(?:member_)?name\s*[=:]\s*[^,;\n]+", re.IGNORECASE),
        "name=[REDACTED_NAME]",
    ),
    (
        re.compile(r"\bpolicy(?:_number)?\s*[=:]\s*[^,;\s]+", re.IGNORECASE),
        "policy=[REDACTED_POLICY]",
    ),
)


class PHIRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            return True
        for pattern, replacement in _REDACTION_PATTERNS:
            message = pattern.sub(replacement, message)
        record.msg = message
        record.args = ()
        return True


def _redacting_record_factory(original_factory):
    redactor = PHIRedactionFilter()

    def factory(*args, **kwargs):
        record = original_factory(*args, **kwargs)
        redactor.filter(record)
        return record

    factory._phi_redacting = True
    return factory


def configure_phi_log_redaction(enabled: bool = True) -> None:
    if not enabled:
        return
    redactor = PHIRedactionFilter()
    record_factory = logging.getLogRecordFactory()
    if not getattr(record_factory, "_phi_redacting", False):
        logging.setLogRecordFactory(_redacting_record_factory(record_factory))
    root = logging.getLogger()
    root.addFilter(redactor)
    for handler in root.handlers:
        handler.addFilter(redactor)
    for logger_name in logging.root.manager.loggerDict:
        child = logging.getLogger(logger_name)
        child.addFilter(redactor)
        for handler in child.handlers:
            handler.addFilter(redactor)
