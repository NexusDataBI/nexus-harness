import re

from nexus_harness.memory.models import MemoryRecord


class MemoryGuardError(ValueError):
    """Raised when content violates the durable-memory persistence boundary."""


SECRET_RULES = (
    (
        "private_key",
        re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----", re.I),
    ),
    ("github_token", re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{16,}\b")),
    ("api_token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    (
        "bearer",
        re.compile(r"Authorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{12,}", re.I),
    ),
    (
        "secret_assignment",
        re.compile(
            r"(?im)^\s*[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)[A-Z0-9_]*\s*=\s*\S+"
        ),
    ),
)


def validate_memory_text(text: str) -> None:
    for rule_name, pattern in SECRET_RULES:
        if pattern.search(text):
            raise MemoryGuardError(f"memory rejected by guard rule: {rule_name}")


def validate_memory_record(record: MemoryRecord) -> None:
    validate_memory_text(record.title)
    validate_memory_text(record.body)
    for source in record.sources:
        validate_memory_text(source.ref)
