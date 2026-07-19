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


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    analysis: SiteAnalysis
    messages: list[ChatMessage]
