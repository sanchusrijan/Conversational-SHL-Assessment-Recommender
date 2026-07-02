from pydantic import BaseModel, Field
from typing import List, Literal

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

class RecommendationItem(BaseModel):
    name: str = Field(..., description="Canonical name of the SHL assessment")
    url: str = Field(..., description="URL link to the SHL assessment")
    test_type: str = Field(..., description="Comma-separated test type codes (e.g. A, K, B, S, P, C, D)")

class ChatResponse(BaseModel):
    reply: str = Field(..., description="Natural language response showing to the user. Includes markdown table of recommendations if committing to a shortlist.")
    recommendations: List[RecommendationItem] = Field(default_factory=list, description="List of recommended assessments. Empty list when clarifying or refusing.")
    end_of_conversation: bool = Field(default=False, description="Flag indicating if the conversation has ended.")
