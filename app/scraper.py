from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

MAX_BYTES = 1_500_000

class FetchError(RuntimeError):
    pass

def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FetchError("Разрешены только корректные HTTP/HTTPS URL")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise FetchError("Не удалось разрешить доменное имя") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError("Доступ к локальным и служебным адресам запрещён")

def extract_visible_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    chunks = []
    for el in soup.select("h1, h2, h3, p, li, a, button"):
        text = " ".join(el.get_text(" ", strip=True).split())
        if len(text) >= 3:
            chunks.append(text)
    deduped = list(dict.fromkeys(chunks))
    return title, "\n".join(deduped)[:45_000]

async def fetch_site(url: str) -> dict[str, str]:
    _validate_public_url(url)
    headers = {"User-Agent": "AIMETON-Site-Auditor/0.1 (+https://github.com/Dimar4713/AIMETON_site_auditor)"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers=headers) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                raise FetchError("Главная страница не является HTML-документом")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise FetchError("Страница превышает допустимый размер")
                chunks.append(chunk)
    html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    title, text = extract_visible_text(html)
    if len(text) < 80:
        raise FetchError("На странице недостаточно доступного текста для анализа")
    return {"final_url": str(response.url), "title": title, "text": text}
