"""RSS 수집. 3개 소스에서 지난 WINDOW_DAYS 기사를 모아 정규화."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import feedparser

from .models import Article


def _parse_published(entry) -> tuple[datetime | None, str]:
    raw = entry.get("published", "") or entry.get("updated", "")
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc), raw
    return None, raw


def _clean(text: str) -> str:
    # description에 HTML이 섞여 들어오는 경우를 위한 가벼운 정리
    import re

    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def collect_source(source: dict, window_days: int) -> list[Article]:
    feed = feedparser.parse(source["rss"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    articles: list[Article] = []
    for entry in feed.entries:
        published, raw = _parse_published(entry)
        if published and published < cutoff:
            continue
        articles.append(
            Article(
                source_key=source["key"],
                source_name=source["name"],
                title=_clean(entry.get("title", "")),
                link=entry.get("link", ""),
                summary=_clean(entry.get("summary", "") or entry.get("description", "")),
                published=published,
                raw_published=raw,
            )
        )
    return articles


def collect_all(sources: list[dict], window_days: int) -> dict[str, list[Article]]:
    """소스별로 수집. 반환: {source_key: [Article, ...]}."""
    result: dict[str, list[Article]] = {}
    seen_links: set[str] = set()
    for src in sources:
        articles = collect_source(src, window_days)
        deduped = []
        for a in articles:
            if a.link and a.link in seen_links:
                continue
            if a.link:
                seen_links.add(a.link)
            deduped.append(a)
        result[src["key"]] = deduped
    return result
