"""Data contracts. Extractor reads only the operator-selected visible DOM region."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    brand: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    model: str = Field(default="", max_length=150)
    category: str = Field(default="", max_length=150)
    model_evidence: str = Field(default="", max_length=500)
    is_demo: bool = False


class Capture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: Product
    source_url: str
    frame_url: str
    page_title: str
    title: str
    frame_path: list[int]
    root_selector: str
    blocks: list[dict]
    links: list[dict]
    displayed_times: list[str]
    characters: int
    withheld_links: int = 0
    captured_at: str
    status: Literal["pending_review"] = "pending_review"
    issues: list[str] = Field(default_factory=list)
    faq: list[dict] = Field(default_factory=list)
    videos: list[dict] = Field(default_factory=list)
    content_hash: str = ""
    id: str = ""
    local_only: Literal[True] = True
