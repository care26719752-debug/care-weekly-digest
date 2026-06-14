from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    source_key: str
    source_name: str
    title: str
    link: str
    summary: str
    published: datetime | None = None
    raw_published: str = ""
    # 1차 필터 결과
    matched_keywords: list[str] = field(default_factory=list)
    is_local_brief: bool = False  # [지역명]+행사동사 휴리스틱 플래그

    def to_prompt_dict(self) -> dict:
        return {
            "source": self.source_name,
            "title": self.title,
            "summary": self.summary,
            "link": self.link,
            "date": self.published.strftime("%Y-%m-%d") if self.published else self.raw_published,
            "local_brief": self.is_local_brief,
        }
