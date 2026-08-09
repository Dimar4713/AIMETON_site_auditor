from __future__ import annotations

from urllib.parse import urlparse


SUPPORTING_SOURCE_HOSTS = frozenset(
    {
        "1dentist.ru",
        "2gis.ru",
        "32top.ru",
        "alldantist.ru",
        "audit-it.ru",
        "barb.pro",
        "checko.ru",
        "companies.rbc.ru",
        "dentalclinics.care",
        "dentistfind.ru",
        "dentistpro.ru",
        "dent-list.ru",
        "docdoc.ru",
        "doctu.ru",
        "flamp.ru",
        "gdevrach.com",
        "infodoctor.ru",
        "interfax.ru",
        "irecommend.ru",
        "jsprav.ru",
        "kleos.ru",
        "kommersant.ru",
        "kp.ru",
        "krasotaimedicina.ru",
        "like.doctor",
        "list-org.com",
        "napopravku.ru",
        "poidata.io",
        "prodoctorov.ru",
        "rbc.ru",
        "ria.ru",
        "rusprofile.ru",
        "sbis.ru",
        "spark-interfax.ru",
        "startsmile.ru",
        "stomatologiya-info.ru",
        "stomotologiya.ru",
        "tass.ru",
        "totadres.ru",
        "vc.ru",
        "vedomosti.ru",
        "vk.com",
        "vk.ru",
        "wikipedia.org",
        "yandex.com",
        "yandex.ru",
        "yp.ru",
        "zdravzdrav.ru",
        "zoon.ru",
        "zubbo.ru",
    }
)

SUPPORTING_TITLE_MARKERS = (
    "адреса компаний",
    "адреса, отзывы",
    "бьюти-гид",
    "каталог клиник",
    "каталог компаний",
    "каталог организаций",
    "каталог стоматолог",
    "лучшие стоматолог",
    "рядом со мной",
    "рейтинг клиник",
    "рейтинг стоматолог",
    "список стоматолог",
    "топ-",
    "топ ",
)

BLOCKED_OR_CHALLENGE_MARKERS = (
    "ограничение доступа",
    "проверка браузера",
    "проверка пользователя",
)


def domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def is_supporting_host(host: str) -> bool:
    normalized = host.lower().removeprefix("www.")
    return any(normalized == known or normalized.endswith(f".{known}") for known in SUPPORTING_SOURCE_HOSTS)


def classify_source_role(title: str, snippet: str, url: str) -> str:
    """Classify a search result before expensive deep analysis.

    `supporting_source` means the result is useful for discovery/corroboration but
    must not compete with an official company site in the direct-lead ranking.
    `blocked_source` is a source/challenge page that likewise cannot be a direct lead.
    The default stays `direct_candidate` so unknown official sites are not lost.
    """

    host = domain(url)
    text = f"{title} {snippet}".casefold().replace("ё", "е")
    if any(marker in text for marker in BLOCKED_OR_CHALLENGE_MARKERS):
        return "blocked_source"
    if is_supporting_host(host) or any(marker in text for marker in SUPPORTING_TITLE_MARKERS):
        return "supporting_source"
    return "direct_candidate"


def role_rank(role: str) -> int:
    return {
        "direct_candidate": 3,
        "possible_candidate": 2,
        "supporting_source": 1,
        "blocked_source": 0,
        "noise": 0,
    }.get(role, 1)
