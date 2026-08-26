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
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
        ),
    ),
    (
        "dsn",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:]+:[^/\s@]+@", re.I),
    ),
    (
        "cookie",
        re.compile(r"(?im)^\s*(?:Set-Cookie|Cookie)\s*:\s*\S+"),
    ),
    (
        "cloud_token",
        re.compile(r"\b(?:AKIA[0-9A-Z]{16}|xox[baprs]-|sk_live_)[A-Za-z0-9/_+=-]*"),
    ),
    (
        "customer_pii",
        re.compile(
            r"(?is)\b(?:cpf\s*[:=]?\s*\d{3}\.?\d{3}\.?\d{3}-?\d{2}|raw[_ -]?customer[_ -]?payload)\b"
        ),
    ),
)


def validate_memory_text(text: str) -> None:
    for rule_name, pattern in SECRET_RULES:
        if pattern.search(text):
            raise MemoryGuardError(f"memory rejected by guard rule: {rule_name}")


def validate_memory_record(record: MemoryRecord) -> None:
    texts = [record.id, record.title, record.body, record.created_at]
    if record.project_id is not None:
        texts.append(record.project_id)
    if record.verified_at is not None:
        texts.append(record.verified_at)
    if record.valid_at_commit is not None:
        texts.append(record.valid_at_commit)
    for source in record.sources:
        texts.append(source.kind)
        texts.append(source.ref)
    texts.extend(record.evidence_ids)
    texts.extend(record.related_paths)
    texts.extend(record.tags)
    texts.extend(record.supersedes)
    for text in texts:
        validate_memory_text(text)
