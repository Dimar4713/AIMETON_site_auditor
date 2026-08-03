from datetime import UTC, datetime, timedelta

from app.evidence_retrieval import EvidenceChunk, rank_evidence_chunks


NOW = datetime(2026, 8, 3, tzinfo=UTC)


def chunk(
    *,
    document_id: str,
    locator: str,
    text: str,
    identity_match: bool = True,
    authority: int = 80,
    age_days: int = 0,
    questions: frozenset[str] = frozenset(),
) -> EvidenceChunk:
    return EvidenceChunk(
        document_id=document_id,
        evidence_id=f"evidence:{document_id}:{locator}",
        locator=locator,
        text=text,
        identity_match=identity_match,
        source_authority=authority,
        observed_at=NOW - timedelta(days=age_days),
        mandatory_questions=questions,
    )


def test_results_preserve_document_evidence_locator_and_digest() -> None:
    source = chunk(
        document_id="doc:registry",
        locator="section:ownership",
        text="Учредитель и владелец компании указан в реестре",
    )

    result = rank_evidence_chunks("владелец компании", [source], now=NOW)[0]

    assert result.document_id == source.document_id
    assert result.evidence_id == source.evidence_id
    assert result.locator == source.locator
    assert result.digest == source.digest
    assert len(result.digest) == 64


def test_identity_mismatch_is_ranked_below_matching_document() -> None:
    matching = chunk(
        document_id="doc:matching",
        locator="p:1",
        text="оборот компании за отчетный год",
    )
    mismatched = chunk(
        document_id="doc:mismatched",
        locator="p:1",
        text="оборот компании за отчетный год",
        identity_match=False,
        authority=100,
    )

    results = rank_evidence_chunks(
        "оборот компании", [mismatched, matching], now=NOW
    )

    assert [item.document_id for item in results] == ["doc:matching", "doc:mismatched"]


def test_stale_document_is_ranked_below_fresh_equivalent() -> None:
    fresh = chunk(
        document_id="doc:fresh",
        locator="table:staff",
        text="численность персонала составляет 120 человек",
        age_days=5,
    )
    stale = chunk(
        document_id="doc:stale",
        locator="table:staff",
        text="численность персонала составляет 120 человек",
        age_days=900,
    )

    results = rank_evidence_chunks("численность персонала", [stale, fresh], now=NOW)

    assert [item.document_id for item in results] == ["doc:fresh", "doc:stale"]


def test_mandatory_question_relevance_is_explicit() -> None:
    relevant = chunk(
        document_id="doc:relevant",
        locator="section:contacts",
        text="официальный телефон компании",
        questions=frozenset({"contacts"}),
    )
    generic = chunk(
        document_id="doc:generic",
        locator="section:about",
        text="официальный телефон компании",
    )

    results = rank_evidence_chunks(
        "телефон", [generic, relevant], mandatory_question="contacts", now=NOW
    )

    assert results[0].document_id == "doc:relevant"


def test_long_document_sections_are_ranked_as_independent_chunks() -> None:
    noise = " ".join(["общая информация"] * 2_000)
    chunks = [
        chunk(document_id="doc:long", locator="section:intro", text=noise),
        chunk(
            document_id="doc:long",
            locator="section:critical-legal",
            text="арбитражный иск и судебное разбирательство",
        ),
    ]

    result = rank_evidence_chunks("арбитражный иск", chunks, now=NOW, limit=1)[0]

    assert result.locator == "section:critical-legal"


def test_ranking_is_deterministic_for_equal_scores() -> None:
    first = chunk(document_id="doc:b", locator="p:2", text="рынок продажи")
    second = chunk(document_id="doc:a", locator="p:1", text="рынок продажи")

    run_one = rank_evidence_chunks("рынок", [first, second], now=NOW)
    run_two = rank_evidence_chunks("рынок", [second, first], now=NOW)

    assert run_one == run_two
    assert [item.document_id for item in run_one] == ["doc:a", "doc:b"]
