"""1차 키워드 필터 + 지역단신 탐지.

키워드 필터는 recall용 느슨한 거름망(복지부/복지타임스에만). 요양뉴스는 무필터 통과.
지역단신 탐지는 [지역명]+행사동사 휴리스틱으로 플래그만 부착(삭제 아님) — 최종 판정은 2차 LLM.
"""
from __future__ import annotations

import re

import config
from .models import Article

# 비교 정규화: 공백·특수문자 무시 부분문자열 매칭
_NORM_RE = re.compile(r"[\s\W]+", re.UNICODE)


def _norm(text: str) -> str:
    return _NORM_RE.sub("", text or "")


def _find(haystack: str, needles: list[str]) -> list[str]:
    return [n for n in needles if _norm(n) in haystack]


def keyword_pass(article: Article) -> bool:
    """True면 채택. matched_keywords를 채워준다."""
    hay = _norm(article.title) + _norm(article.summary)

    core = _find(hay, config.INCLUDE_CORE)
    general = _find(hay, config.INCLUDE_GENERAL)
    context = _find(hay, config.INCLUDE_CONTEXT)
    excluded = _find(hay, config.EXCLUDE)

    article.matched_keywords = core + general + context

    if core:
        return True  # CORE는 exclude 무시하고 무조건 채택
    if not (general or context):
        return False  # include 무매칭
    return not excluded


# --- 지역단신 탐지 ---
# 제목이 [지역명](시/군/구/광역시/도)으로 시작 AND 행사성 동사 포함
_REGION_RE = re.compile(
    r"^\W*[가-힣]{2,10}(?:특별자치시|특별자치도|특별시|광역시|시|군|구|도)[\s,·]"
)
_EVENT_WORDS = [
    "개최", "실시", "운영", "성료", "개관", "수여", "지원", "진행",
    "마련", "열려", "선정", "체결", "방문", "교육",
]


def detect_local_brief(article: Article) -> bool:
    if not _REGION_RE.match(article.title):
        return False
    return any(w in article.title for w in _EVENT_WORDS)


def apply(sources: list[dict], collected: dict[str, list[Article]]) -> list[Article]:
    """소스 정책에 따라 필터링하고 지역단신 플래그를 부착해 단일 리스트로 반환."""
    src_by_key = {s["key"]: s for s in sources}
    kept: list[Article] = []
    for key, articles in collected.items():
        needs_filter = src_by_key[key]["filter"]
        for a in articles:
            if needs_filter and not keyword_pass(a):
                continue
            a.is_local_brief = detect_local_brief(a)
            kept.append(a)
    return kept
