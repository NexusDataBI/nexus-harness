import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from nexus_harness.memory.guard import MemoryGuardError, validate_memory_text
from nexus_harness.memory.models import (
    MemoryDraft,
    MemoryScope,
    MemorySource,
    MemoryType,
)
from nexus_harness.memory.store import init_project_memory, write_memory


class MemoryGuardTests(unittest.TestCase):
    def test_rejects_private_key_material(self):
        with self.assertRaises(MemoryGuardError):
            validate_memory_text("-----BEGIN OPENSSH PRIVATE KEY----- secret")

    def test_rejects_env_secret_assignment(self):
        with self.assertRaises(MemoryGuardError):
            validate_memory_text("DATABASE_PASSWORD=super-secret-value")

    def test_allows_ordinary_engineering_text(self):
        validate_memory_text("The API is authoritative for persisted lead state.")

    def _assert_rule_rejects(self, text: str, rule: str, secret: str) -> None:
        with self.assertRaises(MemoryGuardError) as ctx:
            validate_memory_text(text)
        message = str(ctx.exception)
        self.assertEqual(message, f"memory rejected by guard rule: {rule}")
        self.assertNotIn(secret, message)

    def test_rejects_openssh_and_pem_private_keys_without_echoing_secret(self):
        cases = (
            (
                "-----BEGIN OPENSSH PRIVATE KEY-----\nopenssh-secret-payload",
                "openssh-secret-payload",
            ),
            (
                "-----BEGIN PRIVATE KEY-----\npem-secret-payload",
                "pem-secret-payload",
            ),
            (
                "-----BEGIN RSA PRIVATE KEY-----\nrsa-secret-payload",
                "rsa-secret-payload",
            ),
            (
                "-----BEGIN EC PRIVATE KEY-----\nec-secret-payload",
                "ec-secret-payload",
            ),
        )
        for text, secret in cases:
            with self.subTest(text=text):
                self._assert_rule_rejects(text, "private_key", secret)

    def test_rejects_secret_assignments_without_echoing_payload(self):
        cases = (
            "DATABASE_PASSWORD=assignment-password-payload",
            "APP_SECRET=assignment-secret-payload",
            "AUTH_TOKEN=assignment-token-payload",
            "SERVICE_API_KEY=assignment-api-key-payload",
            "SSH_PRIVATE_KEY=assignment-private-key-payload",
        )
        for text in cases:
            secret = text.split("=", 1)[1]
            with self.subTest(text=text):
                self._assert_rule_rejects(text, "secret_assignment", secret)

    def test_rejects_authorization_bearer_without_echoing_token(self):
        secret = "eyJhbGciOiJIUzI1NiIsInR5cCI"
        self._assert_rule_rejects(
            f"Authorization: Bearer {secret}",
            "bearer",
            secret,
        )

    def test_rejects_github_and_api_token_prefixes_without_echoing_secret(self):
        cases = (
            ("github_token", "ghp_abcdefghijklmnopqrstuvwxyz01"),
            ("github_token", "github_pat_abcdefghijklmnopqrst"),
            ("api_token", "sk-abcdefghijklmnopqrstuvwxyz"),
        )
        for rule, secret in cases:
            with self.subTest(secret=secret):
                self._assert_rule_rejects(f"token material {secret}", rule, secret)

    def test_write_memory_rejects_secret_and_does_not_persist(self):
        secret = "ghp_abcdefghijklmnopqrstuvwxyz01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            draft = MemoryDraft(
                type=MemoryType.COMPONENT,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Leaked credential",
                body=f"do not store {secret}",
                sources=(MemorySource(kind="note", ref="safe-ref"),),
            )
            with self.assertRaises(MemoryGuardError) as ctx:
                write_memory(root, draft.to_record())
            message = str(ctx.exception)
            self.assertEqual(message, "memory rejected by guard rule: github_token")
            self.assertNotIn(secret, message)
            memory_root = root / ".nexus" / "memory" / "components"
            self.assertEqual(list(memory_root.glob("*.md")), [])
            self.assertEqual(list(memory_root.glob("*.json")), [])

    def test_write_memory_rejects_secret_in_tag_without_echoing(self):
        secret = "sk-abcdefghijklmnopqrstuvwxyz"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            draft = MemoryDraft(
                type=MemoryType.COMPONENT,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Safe title",
                body="Safe body",
                tags=(secret,),
            )
            with self.assertRaises(MemoryGuardError) as ctx:
                write_memory(root, draft.to_record())
            message = str(ctx.exception)
            self.assertEqual(message, "memory rejected by guard rule: api_token")
            self.assertNotIn(secret, message)
            memory_root = root / ".nexus" / "memory" / "components"
            self.assertEqual(list(memory_root.glob("*.md")), [])
            self.assertEqual(list(memory_root.glob("*.json")), [])

    def test_write_memory_rejects_secret_in_verified_at_without_persisting(self):
        secret = "sk-abcdefghijklmnopqrstuvwxyz"
        record = replace(
            MemoryDraft(
                type=MemoryType.COMPONENT,
                scope=MemoryScope.PROJECT,
                project_id="repo-1",
                title="Safe title",
                body="Safe body",
            ).to_record(),
            verified_at=secret,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_memory(root)
            with self.assertRaises(MemoryGuardError) as ctx:
                write_memory(root, record)
            message = str(ctx.exception)
            self.assertEqual(message, "memory rejected by guard rule: api_token")
            self.assertNotIn(secret, message)
            memory_root = root / ".nexus" / "memory" / "components"
            self.assertEqual(list(memory_root.glob("*.md")), [])
            self.assertEqual(list(memory_root.glob("*.json")), [])

    def test_write_memory_rejects_secret_in_sidecar_strings(self):
        secret = "sk-abcdefghijklmnopqrstuvwxyz"
        safe = MemoryDraft(
            type=MemoryType.COMPONENT,
            scope=MemoryScope.PROJECT,
            project_id="repo-1",
            title="Safe title",
            body="Safe body",
            sources=(MemorySource(kind="note", ref="safe-ref"),),
        )
        cases = (
            replace(safe.to_record(), related_paths=(secret,)),
            replace(safe.to_record(), evidence_ids=(secret,)),
            replace(safe.to_record(), project_id=secret),
            replace(safe.to_record(), created_at=secret),
            replace(safe.to_record(), valid_at_commit=secret),
            replace(
                safe.to_record(),
                sources=(MemorySource(kind=secret, ref="safe-ref"),),
            ),
            replace(
                safe.to_record(),
                id="mem-lesson-sk-abcdefghijklmnopqrst-deadbeef",
            ),
        )
        for record in cases:
            with self.subTest(record=record):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    init_project_memory(root)
                    with self.assertRaises(MemoryGuardError) as ctx:
                        write_memory(root, record)
                    message = str(ctx.exception)
                    self.assertEqual(
                        message, "memory rejected by guard rule: api_token"
                    )
                    self.assertNotIn(secret, message)
                    self.assertNotIn("sk-abcdefghijklmnopqrst", message)
                    memory_root = root / ".nexus" / "memory" / "components"
                    self.assertEqual(list(memory_root.glob("*.md")), [])
                    self.assertEqual(list(memory_root.glob("*.json")), [])
