"""추천 뉴스 — 네이버 뉴스 검색 API로 그 주 주목 기사를 큐레이션.

사람이 네이버 뉴스에서 도메인 키워드로 검색하듯, 축별 질의로 관련도순 최신 기사를 받아
온토픽·최신·중복제거 필터를 거쳐 축당 1건씩 고른다(기본 4건).

필요 환경변수: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime, timedelta, timezone

import requests

import config

API = "https://openapi.naver.com/v1/search/news.json"
TIMEOUT = 15
RECENT_DAYS = 14  # 이보다 오래된 기사는 추천에서 제외
_TAG = re.compile(r"<[^>]+>")
_NORM = re.compile(r"[\s\W]+", re.UNICODE)

# 온토픽 판정용 도메인 키워드(1차 필터의 CORE+GENERAL 재사용)
_TOPIC_KW = config.INCLUDE_CORE + config.INCLUDE_GENERAL


def _clean(s: str) -> str:
    return _TAG.sub("", html.unescape(s or "")).strip()


def _norm(s: str) -> str:
    return _NORM.sub("", s or "")


def _on_topic(text: str) -> bool:
    return any(k in text for k in _TOPIC_KW)


def _recent(pub: str) -> bool:
    # pubDate 예: 'Sun, 28 Jun 2026 12:36:00 +0900'
    try:
        dt = datetime.strptime(pub.strip(), "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        return True  # 파싱 실패 시 보수적으로 통과
    return dt >= datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)


def _headers() -> dict:
    cid = os.environ.get("NAVER_CLIENT_ID")
    cs = os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and cs):
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정")
    return {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": cs}


def _search(query: str, display: int = 10) -> list[dict]:
    """관련도순(sim) 검색. 항목: {title, link, desc, pub, source}."""
    r = requests.get(
        API,
        params={"query": query, "display": display, "sort": "sim"},
        headers=_headers(),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        link = it.get("originallink") or it.get("link") or ""
        out.append({
            "title": _clean(it.get("title", "")),
            "link": link,
            "desc": _clean(it.get("description", "")),
            "pub": it.get("pubDate", ""),
            "source": re.sub(r"^www\.", "", re.sub(r"https?://([^/]+).*", r"\1", link)),
        })
    return out


def recommend_news(exclude_links=None, limit: int = 4) -> list[dict]:
    """축별 질의로 추천 뉴스를 고른다. exclude_links: 디제스트에 이미 쓴 링크(중복 회피).

    반환: [{title, link, source}] 최대 limit개. 네트워크/키 문제 시 [] (발행은 계속).
    """
    seen = {_norm_link(u) for u in (exclude_links or [])}
    picks: list[dict] = []
    try:
        for axis, query in config.RECOMMEND_QUERIES.items():
            try:
                items = _search(query)
            except requests.RequestException:
                continue
            for it in items:
                if not it["link"] or _norm_link(it["link"]) in seen:
                    continue
                if not _recent(it["pub"]):
                    continue
                if not _on_topic(it["title"] + " " + it["desc"]):
                    continue
                picks.append({"title": it["title"], "link": it["link"], "source": it["source"]})
                seen.add(_norm_link(it["link"]))
                break  # 축당 1건
    except RuntimeError:
        return []  # 키 미설정 → 조용히 생략
    # 부족하면 일반 질의로 보충
    if len(picks) < limit:
        try:
            for it in _search("요양 노인 돌봄", display=20):
                if len(picks) >= limit:
                    break
                if not it["link"] or _norm_link(it["link"]) in seen:
                    continue
                if not (_recent(it["pub"]) and _on_topic(it["title"] + " " + it["desc"])):
                    continue
                picks.append({"title": it["title"], "link": it["link"], "source": it["source"]})
                seen.add(_norm_link(it["link"]))
        except (requests.RequestException, RuntimeError):
            pass
    return picks[:limit]


def _norm_link(u: str) -> str:
    return _norm(re.sub(r"https?://(www\.)?", "", (u or "").split("?")[0]).rstrip("/"))
