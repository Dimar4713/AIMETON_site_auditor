from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


class AgentRecommendation(BaseModel):
    name: str
    purpose: str
    benefit: str
    priority: Literal["Высокий", "Средний", "Низкий"] = "Средний"


class EconomicSignal(BaseModel):
    signal: str
    evidence: str
    business_effect: str
    confidence: Literal["Высокая", "Средняя", "Низкая"] = "Средняя"


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
    economic_signals: list[EconomicSignal] = Field(default_factory=list)
    commercial_opportunity: CommercialOpportunity
    agents: list[AgentRecommendation] = Field(min_length=3, max_length=10)
    action_package: ActionPackage
    risks_and_assumptions: list[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    url: HttpUrl


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


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    analysis: SiteAnalysis
    messages: list[ChatMessage]
