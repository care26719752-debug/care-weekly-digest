"""대표 기사 이미지 수집 — 그 주 다이제스트의 대표 기사에서 og:image를 받아온다.

설계:
- 대표 기사: 첫 active 축의 sources 순서대로 후보 → 못 받으면 다음 후보 → 끝으로 kept 전체.
- og:image(+twitter:image 폴백)만 정규식으로 추출(새 의존성 없음).
- 실패/이미지없음/너무 작거나 큼은 조용히 None → 발행은 테마 그라데이션 폴백으로 진행.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

import requests

from .models import Article

UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 SilvercareDigestBot/1.0"
    )
}
PAGE_TIMEOUT = 20
MIN_BYTES = 2_000        # 파비콘/스페이서 컷
MAX_BYTES = 8_000_000    # 과대 이미지 컷
EXT_BY_CT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
             "image/webp": "webp", "image/gif": "gif"}

_OG_PATTERNS = [
    r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::url)?["\']',
    r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
]


def _norm(s: str) -> str:
    return re.sub(r"[\s\W]+", "", s or "").lower()


def _best_match(source_title: str, kept: list[Article]) -> Article | None:
    """LLM이 적은 sources 제목 문자열을 실제 kept 기사와 느슨하게(부분문자열) 매칭."""
    s = _norm(source_title)
    if not s:
        return None
    best, best_len = None, 0
    for a in kept:
        t = _norm(a.title)
        if t and (t in s or s in t) and len(t) > best_len:
            best, best_len = a, len(t)
    return best


def candidate_articles(digest: dict, kept: list[Article]) -> list[Article]:
    """대표 후보를 우선순위 순으로. 첫 active 축의 sources → 나머지 kept."""
    seen: set[str] = set()
    out: list[Article] = []
    for ax in digest.get("axes", []):
        if not ax.get("active"):
            continue
        for s in ax.get("sources", []) or []:
            a = _best_match(s, kept)
            if a and a.link and a.link not in seen:
                seen.add(a.link)
                out.append(a)
    for a in kept:
        if a.link and a.link not in seen:
            seen.add(a.link)
            out.append(a)
    # 실사진 확률이 높은 전문매체를 먼저, 정부 보도자료(로고 og)는 뒤로 (stable sort로 축 우선순위 유지)
    out.sort(key=lambda a: 1 if a.source_key == "mohw" else 0)
    return out


# og:image가 실사진이 아니라 기관 로고/기본 배너인 경우(예: korea.kr=korea_logo_2024.jpg) 컷.
BOILERPLATE_URL = (
    "korea_logo", "/images/event/", "logo_2024", "noimage", "no_image",
    "og_default", "default-og", "default_og", "blank.", "/logo", "_logo.",
)
# 본문 인라인 이미지 폴백 시 사진이 아닌 것(로고·아이콘·배너·광고 등) 제외.
BAD_IMG_HINT = (
    "logo", "icon", "banner", "btn", "button", "blank", "spacer", "emoticon",
    "/ad/", "ads", "profile", "avatar", "sns", "share", "facebook", "twitter",
)
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)


def _extract_og(html: str) -> str | None:
    for pat in _OG_PATTERNS:
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return None


def _is_boilerplate(url: str) -> bool:
    u = url.lower()
    return any(b in u for b in BOILERPLATE_URL)


def _extract_body_image(html: str, page_url: str) -> str | None:
    """본문에서 사진일 법한 첫 <img>를 고른다(로고/아이콘/광고 제외)."""
    for m in _IMG_SRC_RE.finditer(html):
        src = m.group(1).strip()
        low = src.lower()
        if any(h in low for h in BAD_IMG_HINT):
            continue
        if not re.search(r"\.(jpe?g|png|webp)(\?|$)", low):
            continue
        return urljoin(page_url, src)
    return None


def _pick_image_url(html: str, page_url: str) -> str | None:
    """og:image(보일러플레이트 아님) → 본문 첫 사진 순으로 대표 이미지 URL 선택."""
    og = _extract_og(html)
    if og and not _is_boilerplate(og):
        return urljoin(page_url, og)
    return _extract_body_image(html, page_url)


def fetch_og_image(page_url: str) -> tuple[bytes, str, str] | None:
    """기사 페이지에서 대표 이미지를 받아 (bytes, content_type, filename) 반환. 실패 시 None.

    정부 보도자료의 기관 로고(og:image=korea_logo 등)는 건너뛰고 본문 사진으로 폴백한다.
    """
    r = requests.get(page_url, headers=UA, timeout=PAGE_TIMEOUT)
    r.raise_for_status()
    img_url = _pick_image_url(r.text, page_url)
    if not img_url:
        return None
    ir = requests.get(img_url, headers=UA, timeout=PAGE_TIMEOUT)
    ir.raise_for_status()
    ct = ir.headers.get("content-type", "").split(";")[0].strip().lower()
    if not ct.startswith("image/"):
        return None
    data = ir.content
    if len(data) < MIN_BYTES or len(data) > MAX_BYTES:
        return None
    ext = EXT_BY_CT.get(ct, "jpg")
    return data, ct, f"wd-cover.{ext}"


def representative_image(
    digest: dict, kept: list[Article], max_try: int = 5
) -> tuple[bytes, str, str, Article] | None:
    """대표 기사 후보를 순서대로 시도해 첫 성공 이미지를 (bytes, ct, filename, article)로 반환."""
    for a in candidate_articles(digest, kept)[:max_try]:
        try:
            res = fetch_og_image(a.link)
        except Exception:
            continue
        if res:
            return (*res, a)
    return None
