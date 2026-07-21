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
    evidence_quote: str = Field(description="Короткая дословная цитата из загруженного первичного документа")
    source_type: Literal[
        "official_page", "registry", "court", "arbitration", "enforcement",
        "ownership", "affiliation", "finance", "workforce", "contact",
        "news", "social", "review", "jobs", "tender", "patent",
        "external_source", "visual_observation",
    ] = "external_source"
    evidence_level: Literal[
        "confirmed_fact", "corroborated_signal", "weak_signal", "unverified_mention"
    ] = "unverified_mention"
    document_url: str | None = None
    document_title: str | None = None
    document_accessed_at: str | None = None


class EconomicSignal(BaseModel):
    signal: str
    evidence: str
    business_effect: str
    confidence: Literal["Высокая", "Средняя", "Низкая"] = "Средняя"
    source_ids: list[str] = Field(default_factory=list, description="Ссылки на EvidenceSource.id")


class CompanyFact(BaseModel):
    field: Literal[
        "legal_name", "brand_name", "inn", "ogrn", "registration_status",
        "address", "phones", "emails", "website", "social_accounts",
        "headcount", "revenue", "profit", "assets", "taxes",
        "founders", "executives", "beneficial_owners", "affiliates",
        "geography", "products", "customers", "suppliers", "other",
    ]
    value: str
    period: str | None = None
    confidence: Literal["Высокая", "Средняя", "Низкая"] = "Средняя"
    source_ids: list[str] = Field(default_factory=list)
    note: str = ""


class BusinessMachineCell(BaseModel):
    code: Literal[
        "I-I", "I-II", "I-III", "I-IV",
        "II-I", "II-II", "II-III", "II-IV",
        "III-I", "III-II", "III-III", "III-IV",
        "IV-I", "IV-II", "IV-III", "IV-IV",
    ]
    detail_operator: Literal[
        "I — Коммуникационные системы",
        "II — Люди",
        "III — Технологии",
        "IV — Менеджмент",
    ]
    vertex: Literal[
        "Взаимодействие", "Влияние", "Зависимость", "Противодействие",
        "Учредители и собственники", "Ось люди-управленцы", "Обслуживающий персонал и роботы", "Виртуозы и специалисты",
        "Знания и наука", "Стандартная процедура", "Рабочая процедура", "Продукты, товар и услуга",
        "Управление коммуникационными системами", "Управление людьми", "Управление технологиями", "Самоуправление",
    ]
    finding: str
    status: Literal["Подтверждено", "Частично", "Гипотеза", "Нет данных"] = "Нет данных"
    confidence: Literal["Высокая", "Средняя", "Низкая"] = "Низкая"
    source_ids: list[str] = Field(default_factory=list)
    sales_relevance: str = Field(default="", description="Как узел влияет на AI-продажу, пилот или ценностное предложение")


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
    company_facts: list[CompanyFact] = Field(default_factory=list)
    business_machine_4x4: list[BusinessMachineCell] = Field(default_factory=list, max_length=16)
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
    region_confirmed: bool | None = None
    preliminary_score: int | None = Field(default=None, ge=0, le=100)
    pre_score_status: Literal["calculated", "insufficient_data"] = "calculated"
    pre_score_factors: dict[str, int | None] = Field(default_factory=dict)
    deep_analysis_performed: bool = False
    final_score: int | None = Field(default=None, ge=0, le=100)
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


SourceKind = Literal[
    "official", "registry", "court", "arbitration", "enforcement",
    "ownership", "affiliation", "finance", "workforce", "contact",
    "news", "social", "review", "jobs", "tender", "patent",
    "aggregator", "other", "unknown",
]


class IntelligenceSource(BaseModel):
    id: str
    title: str
    url: str
    snippet: str = ""
    accessed_at: str
    source_class: SourceKind = "unknown"
    query_kind: SourceKind = "unknown"
    result_kind: SourceKind = "unknown"
    classification_state: Literal["classified", "ambiguous", "unknown"] = "unknown"
    lifecycle_state: Literal["discovery_hint", "source_candidate", "evidence"] = "discovery_hint"
    evidence_level: Literal["confirmed_fact", "corroborated_signal", "weak_signal", "unverified_mention"] = "unverified_mention"
    document_url: str | None = None
    document_title: str | None = None
    document_accessed_at: str | None = None
    evidence_quote: str | None = None
    verification_note: str = "Поисковый сниппет; первичный документ не проверен."


class CompanyIntelligenceRequest(BaseModel):
    company_name: str = Field(min_length=2)
    url: HttpUrl | None = None
    region: str | None = None
    max_sources: int = Field(default=60, ge=5, le=140)


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
