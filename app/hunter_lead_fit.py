from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from app.models import SiteAnalysis


LeadFit = Literal[
    "commercial_candidate",
    "unknown_candidate",
    "institutional_candidate",
    "not_applicable",
]


@dataclass(frozen=True)
class LeadFitAssessment:
    fit: LeadFit
    reason: str
    evidence: tuple[str, ...] = ()


INSTITUTIONAL_HOST_SUFFIXES = (
    "gosuslugi.ru",
    "gov.ru",
)

INSTITUTIONAL_ABBREVIATION_RE = re.compile(
    r"(?<![\wа-я])(?:кгбуз|кгауз|гбуз|гауз|мбуз|огбуз|фгбу|фгбоу|кгкуз|кгбу)(?![\wа-я])",
    re.IGNORECASE,
)

INSTITUTIONAL_PHRASE_PATTERNS = (
    re.compile(r"городск\w*\s+стоматологическ\w*\s+поликлиник\w*", re.IGNORECASE),
    re.compile(r"(?:государственн|муниципальн|бюджетн)\w*\s+(?:медицинск\w*\s+)?учрежден\w*", re.IGNORECASE),
    re.compile(r"университетск\w*\s+(?:медицинск\w*\s+)?центр\w*", re.IGNORECASE),
)

PRIVATE_PHRASE_PATTERNS = (
    re.compile(r"частн\w*\s+(?:стоматолог\w*|клиник\w*|медицинск\w*\s+центр\w*|центр\w*)", re.IGNORECASE),
    re.compile(r"первая\s+частн\w*\s+(?:стоматолог\w*|клиник\w*)", re.IGNORECASE),
)

COMMERCIAL_LEGAL_FORM_RE = re.compile(
    r"^\s*(?:ооо|ип|ао|пао)\b",
    re.IGNORECASE,
)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _normalize(text: str) -> str:
    return " ".join(text.casefold().replace("ё", "е").split())


def _host_matches_suffix(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith(f".{suffix}")


def _analysis_legal_names(analysis: SiteAnalysis | None) -> list[str]:
    if analysis is None:
        return []
    values: list[str] = []
    for fact in analysis.company_facts:
        if fact.field == "legal_name" and fact.value.strip():
            values.append(fact.value.strip())
    return values


def classify_lead_fit(
    *,
    title: str,
    snippet: str,
    url: str,
    source_role: str,
    analysis: SiteAnalysis | None = None,
) -> LeadFitAssessment:
    """Classify sales actionability separately from source identity.

    The classifier is intentionally conservative. A branded clinic, prices, online
    booking or the generic word ``клиника`` are not proof of private ownership.
    Unknown direct organizations stay discoverable and rank between explicit
    commercial and explicit institutional candidates.
    """

    if source_role != "direct_candidate":
        return LeadFitAssessment(
            "not_applicable",
            "lead-fit не применяется к вспомогательному или заблокированному источнику",
            (f"source_role:{source_role}",),
        )

    host = _host(url)
    shallow_text = _normalize(f"{title} {snippet}")

    for suffix in INSTITUTIONAL_HOST_SUFFIXES:
        if _host_matches_suffix(host, suffix):
            return LeadFitAssessment(
                "institutional_candidate",
                "домен относится к государственному сервисному пространству",
                (f"institutional_host:{suffix}",),
            )

    abbreviation = INSTITUTIONAL_ABBREVIATION_RE.search(shallow_text)
    if abbreviation:
        marker = abbreviation.group(0)
        return LeadFitAssessment(
            "institutional_candidate",
            "обнаружена явная организационно-правовая аббревиатура бюджетного/государственного учреждения",
            (f"institutional_marker:{marker.casefold()}",),
        )

    for pattern in INSTITUTIONAL_PHRASE_PATTERNS:
        match = pattern.search(shallow_text)
        if match:
            return LeadFitAssessment(
                "institutional_candidate",
                "обнаружено явное описание государственной, муниципальной или университетской организации",
                (f"institutional_phrase:{_normalize(match.group(0))}",),
            )

    for pattern in PRIVATE_PHRASE_PATTERNS:
        match = pattern.search(shallow_text)
        if match:
            return LeadFitAssessment(
                "commercial_candidate",
                "источник прямо называет организацию частной",
                (f"private_phrase:{_normalize(match.group(0))}",),
            )

    for legal_name in _analysis_legal_names(analysis):
        match = COMMERCIAL_LEGAL_FORM_RE.search(legal_name)
        if match:
            return LeadFitAssessment(
                "commercial_candidate",
                "глубокий анализ подтвердил коммерческую организационно-правовую форму",
                (f"legal_form:{match.group(0).casefold()}", f"legal_name:{legal_name}"),
            )

    if analysis is not None:
        deep_text = _normalize(
            " ".join(
                [
                    analysis.company_name,
                    analysis.business_summary,
                    *analysis.evidence[:10],
                ]
            )
        )
        abbreviation = INSTITUTIONAL_ABBREVIATION_RE.search(deep_text)
        if abbreviation:
            return LeadFitAssessment(
                "institutional_candidate",
                "глубокий анализ подтвердил признаки бюджетного/государственного учреждения",
                (f"deep_institutional_marker:{abbreviation.group(0).casefold()}",),
            )
        for pattern in INSTITUTIONAL_PHRASE_PATTERNS:
            match = pattern.search(deep_text)
            if match:
                return LeadFitAssessment(
                    "institutional_candidate",
                    "глубокий анализ подтвердил институциональный характер организации",
                    (f"deep_institutional_phrase:{_normalize(match.group(0))}",),
                )
        for pattern in PRIVATE_PHRASE_PATTERNS:
            match = pattern.search(deep_text)
            if match:
                return LeadFitAssessment(
                    "commercial_candidate",
                    "глубокий анализ прямо подтвердил частный характер организации",
                    (f"deep_private_phrase:{_normalize(match.group(0))}",),
                )

    return LeadFitAssessment(
        "unknown_candidate",
        "нет достаточно сильных признаков частной или институциональной формы; кандидат сохранён без догадки",
        (),
    )


def lead_fit_rank(fit: str) -> int:
    return {
        "commercial_candidate": 3,
        "unknown_candidate": 2,
        "institutional_candidate": 1,
        "not_applicable": 0,
    }.get(fit, 2)
