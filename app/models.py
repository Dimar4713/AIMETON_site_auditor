from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


class AgentRecommendation(BaseModel):
    name: str
    purpose: str
    benefit: str
    priority: Literal["Высокий", "Средний", "Низкий"] = "Средний"


class EvidenceSource(BaseModel):
    id: str = Field(description="Короткий идентификатор источника, например S1")
    title: str
    url: str
    accessed_at: str = Field(description="Дата и время проверки в ISO 8601")
    evidence_quote: str = Field(description="Короткая дословная цитата или описание наблюдаемого элемента")
    source_type: Literal[
        "official_page",
        "registry",
        "court",
        "arbitration",
        "enforcement",
        "ownership",
        "affiliation",
        "news",
        "social",
        "review",
        "jobs",
        "tender",
        "patent",
        "external_source",
        "visual_observation",
    ] = "external_source"
    evidence_level: Literal[
        "confirmed_fact",
        "corroborated_signal",
        "weak_signal",
        "unverified_mention",
    ] = "unverified_mention"


class EconomicSignal(BaseModel):
    signal: str
    evidence: str
    business_effect: str
    confidence: Literal["Высокая", "Средняя", "Низкая"] = "Средняя"
    source_ids: list[str] = Field(default_factory=list, description="Ссылки на EvidenceSource.id")


class CommercialOpportunity(BaseModel):
    opportunity_type: str
    problem_hypothesis: str
    recommended_solution: str
    expected_value: str
    score: int = Field(ge=0, le=100)
    qualification: Literal["Приоритетная", "Перспективная", "Наблюдение", "Недостаточно данных"]


class ActionPackage(BaseModel):
    decision_maker_hypothesis: str
    contact_reason: str
    demo_scenario: list[str] = Field(default_factory=list)
    first_message: str
    next_action: str


class SiteAnalysis(BaseModel):
    url: str
    company_name: str
    business_summary: str
    evidence: list[str] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)
    economic_signals: list[EconomicSignal] = Field(default_factory=list)
    commercial_opportunity: CommercialOpportunity
    agents: list[AgentRecommendation] = Field(min_length=3, max_length=10)
    action_package: ActionPackage
    risks_and_assumptions: list[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class HuntRequest(BaseModel):
    region: str = Field(min_length=2, description="Территория экономической разведки")
    search_zone: str | None = Field(default=None, description="Район, агломерация или дополнительная зона")
    industries: list[str] = Field(default_factory=list, description="Приоритетные отрасли; пусто — агент формирует базовый набор")
    focus: list[str] = Field(default_factory=list, description="Дополнительные признаки или типы возможностей")
    max_queries: int = Field(default=20, ge=1, le=100)
    results_per_query: int = Field(default=10, ge=1, le=30)
    max_candidates: int = Field(default=100, ge=1, le=500)
    minimum_pre_score: int = Field(default=35, ge=0, le=100)
    deep_audit_score: int = Field(default=60, ge=0, le=100)
    output_limit: int = Field(default=25, ge=1, le=100)
    concurrency: int = Field(default=4, ge=1, le=12)


class HuntCandidate(BaseModel):
    company_name: str
    url: str
    source_title: str
    source_snippet: str = ""
    region_confirmed: bool
    preliminary_score: int = Field(ge=0, le=100)
    final_score: int = Field(ge=0, le=100)
    qualification: str
    business_summary: str
    recommended_solution: str
    reasons: list[str] = Field(default_factory=list)
    analysis: SiteAnalysis | None = None


class HuntResult(BaseModel):
    region: str
    search_zone: str | None = None
    queries: list[str] = Field(default_factory=list)
    discovered: int
    candidates: list[HuntCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class IntelligenceSource(BaseModel):
    id: str
    title: str
    url: str
    snippet: str = ""
    accessed_at: str
    source_class: Literal[
        "official",
        "registry",
        "court",
        "arbitration",
        "enforcement",
        "ownership",
        "affiliation",
        "news",
        "social",
        "review",
        "jobs",
        "tender",
        "patent",
        "other",
    ] = "other"
    evidence_level: Literal["confirmed_fact", "corroborated_signal", "weak_signal", "unverified_mention"] = "unverified_mention"


class CompanyIntelligenceRequest(BaseModel):
    company_name: str = Field(min_length=2)
    url: HttpUrl | None = None
    region: str | None = None
    max_sources: int = Field(default=40, ge=5, le=100)


class CompanyIntelligenceResult(BaseModel):
    company_name: str
    region: str | None = None
    official_url: str | None = None
    site_analysis: SiteAnalysis | None = None
    sources: list[IntelligenceSource] = Field(default_factory=list)
    scent_summary: list[str] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)
    commercial_score: int = Field(ge=0, le=100)
    recommended_solution: str
    status: Literal["complete", "partial"] = "partial"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    analysis: SiteAnalysis
    messages: list[ChatMessage]
