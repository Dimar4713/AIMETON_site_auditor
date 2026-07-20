from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedPage:
    final_url: str
    title: str
    text: str
    provider: str
    html_bytes: int

    def validate(self) -> None:
        if not self.final_url.startswith(("http://", "https://")):
            raise ValueError("final_url must be HTTP/HTTPS")
        if not self.text.strip():
            raise ValueError("visible text is empty")
        if self.provider not in {"httpx", "playwright", "chromium-cli"}:
            raise ValueError("unknown provider")
