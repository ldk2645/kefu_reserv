from __future__ import annotations

import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["R0", "R1", "R2", "R3"]
Intent = Literal["greeting", "product_specs", "how_to_use", "troubleshooting",
                 "logistics", "refund", "complaint", "safety", "other"]


class OCRLine(BaseModel):
    text: str
    bbox: tuple[int, int, int, int]
    confidence: float = Field(ge=0, le=1)
    speaker: Literal["unknown", "customer", "agent"] = "unknown"


class ConfirmedContext(BaseModel):
    session_local_id: str
    capture_id: str = ""
    confirmed_by_user: bool = False
    latest_customer_message: str = ""
    conversation_context: str = ""
    product_id: str | None = None
    sku: str | None = None

    @property
    def fingerprint(self) -> str:
        fields = self.model_dump(exclude={"capture_id", "confirmed_by_user"})
        return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class KnowledgeHit(BaseModel):
    chunk_id: str
    source_id: str
    product_id: str
    source_type: str
    verified_status: str
    title: str
    section: str
    page: int | None = None
    excerpt: str
    path: str
    source_url: str = ""
    is_demo: bool = False
    score: float = 0


class VideoSuggestion(BaseModel):
    video_id: str
    product_id: str
    title: str
    url: str
    intent_tags: list[str]
    verified_status: str
    official_source_name: str
    official_source_url: str
    customer_shareable: bool = False
    is_demo: bool = False
    link_status: str = "unknown"
    verified_by: str = ""
    verified_at: str = ""
    last_checked_at: str = ""


class RiskAssessment(BaseModel):
    intent: Intent
    risk_level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class ModelReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    risk_level: RiskLevel
    missing_information: list[str]
    customer_reply: str = Field(min_length=1, max_length=1500)
    operator_note: str
    used_knowledge_ids: list[str]
    used_video_ids: list[str]


class Draft(ModelReply):
    context_fingerprint: str
    requires_human_review: Literal[True] = True
    mode: str = "本地保守草稿"
    is_demo: bool = False
    stale: bool = False
