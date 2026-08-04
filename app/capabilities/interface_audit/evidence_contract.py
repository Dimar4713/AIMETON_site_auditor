from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceArtifact:
    ref: str
    content_type: str
    size_bytes: int
    sha256: str

    @classmethod
    def from_bytes(cls, ref: str, content_type: str, payload: bytes) -> "EvidenceArtifact":
        if not ref or ref.startswith(("/", "..")):
            raise ValueError("artifact ref must be a stable relative identifier")
        if not content_type:
            raise ValueError("content_type is required")
        return cls(
            ref=ref,
            content_type=content_type,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )


@dataclass(frozen=True)
class InterfaceEvidenceManifest:
    final_url: str
    title: str
    language: str | None
    viewport: dict[str, int]
    color_scheme: str
    reduced_motion: str
    rule_pack_version: str
    rule_pack_digest: str
    artifacts: tuple[EvidenceArtifact, ...]
    console_messages: tuple[dict[str, Any], ...]
    page_errors: tuple[str, ...]
    failed_requests: tuple[dict[str, str], ...]
    redirects: tuple[dict[str, str], ...]

    def validate(self) -> None:
        if not self.final_url.startswith(("http://", "https://")):
            raise ValueError("final_url must be HTTP/HTTPS")
        if not self.rule_pack_version or len(self.rule_pack_digest) != 64:
            raise ValueError("exact rule-pack version and SHA-256 digest are required")
        refs = [artifact.ref for artifact in self.artifacts]
        if len(refs) != len(set(refs)):
            raise ValueError("artifact refs must be unique")
        if not self.artifacts:
            raise ValueError("at least one evidence artifact is required")
