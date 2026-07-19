from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

class AgentRecommendation(BaseModel):
    name: str
    purpose: str
    benefit: str
    priority: Literal["Высокий", "Средний", "Низкий"] = "Средний"

class SiteAnalysis(BaseModel):
    url: str
    company_name: str
    business_summary: str
    evidence: list[str] = Field(default_factory=list)
    agents: list[AgentRecommendation] = Field(min_length=5, max_length=10)
    risks_and_assumptions: list[str] = Field(default_factory=list)

class AnalyzeRequest(BaseModel):
    url: HttpUrl

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    analysis: SiteAnalysis
    messages: list[ChatMessage]
