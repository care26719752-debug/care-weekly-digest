"""워드프레스 REST API 발행 (이메일 발송 대체).

설계:
- 전용 카테고리에 글을 올린다. 노출 차단(noindex·사이트맵/피드/검색 제외)은 WP쪽 mu-plugin이 담당.
- 멱등: 같은 주(week) 글은 슬러그가 같아서, 있으면 새로 만들지 않고 업데이트한다.
- status=publish (익명이 링크로 열람 가능). 비공개성은 '링크를 모르면 못 찾음'으로 확보.
- 인증: Application Password (Basic). 관리자 계정 권장(unfiltered_html로 <style> 보존).

필요 환경변수(.env):
  WP_BASE_URL, WP_USER, WP_APP_PASSWORD
  WP_CATEGORY_SLUG  (전용 카테고리 슬러그 — 추측 어렵게)
  WP_CATEGORY_NAME  (없으면 슬러그로 생성)
"""
from __future__ import annotations

import os
from datetime import date

import requests

TIMEOUT = 60


def _auth() -> tuple[str, str]:
    return os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"].replace(" ", "")


def _base() -> str:
    return os.environ["WP_BASE_URL"].rstrip("/") + "/wp-json/wp/v2"


def week_slug(when: date | None = None) -> str:
    """그 주를 식별하는 결정적 슬러그. 멱등 키로 쓴다. 예: wd-2026-06-w4"""
    when = when or date.today()
    week = (when.day - 1) // 7 + 1
    return f"wd-{when.year}-{when.month:02d}-w{week}"


def _find_category(sess: requests.Session, base: str) -> int | None:
    slug = os.environ["WP_CATEGORY_SLUG"]
    r = sess.get(f"{base}/categories", params={"slug": slug}, timeout=TIMEOUT)
    r.raise_for_status()
    found = r.json()
    return found[0]["id"] if found else None


def _create_category(sess: requests.Session, base: str) -> int:
    slug = os.environ["WP_CATEGORY_SLUG"]
    name = os.environ.get("WP_CATEGORY_NAME", slug)
    r = sess.post(f"{base}/categories", json={"name": name, "slug": slug}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["id"]


def _upload_media(
    sess: requests.Session,
    base: str,
    data: bytes,
    filename: str,
    content_type: str,
    alt: str = "",
) -> int:
    """이미지 바이트를 WP 미디어 라이브러리에 업로드하고 media id 반환."""
    headers = {
        "Content-Type": content_type,
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    r = sess.post(f"{base}/media", data=data, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    media_id = r.json()["id"]
    if alt:
        try:
            sess.post(f"{base}/media/{media_id}", json={"alt_text": alt}, timeout=TIMEOUT)
        except requests.RequestException:
            pass  # alt 실패는 치명적 아님
    return media_id


def _find_existing(sess: requests.Session, base: str, slug: str) -> dict | None:
    # 발행/임시 모두 검색 (멱등 업데이트용)
    r = sess.get(
        f"{base}/posts",
        params={"slug": slug, "status": "publish,draft,private", "context": "edit"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    items = r.json()
    return items[0] if items else None


def publish_digest(
    title: str,
    content_html: str,
    excerpt: str = "",
    when: date | None = None,
    dry_run: bool = False,
    image: tuple[bytes, str, str] | None = None,
) -> dict:
    """다이제스트를 워드프레스에 발행(또는 같은 주 글 업데이트). 결과 dict 반환.

    excerpt: 목록 카드 제목/부제로 쓰는 한 줄 요약(보통 digest['headline']).
    image: (bytes, content_type, filename) — 대표 기사 이미지. 있으면 미디어 업로드 후
           featured_media로 지정. 같은 주 글에 이미 대표이미지가 있으면 중복 업로드하지 않음.
    """
    base = _base()
    slug = week_slug(when)
    sess = requests.Session()
    sess.auth = _auth()

    cat_id = _find_category(sess, base)
    existing = _find_existing(sess, base, slug)

    if dry_run:
        # 순수 읽기만: 생성/발행 없이 무엇을 할지만 보고
        return {
            "action": "update" if existing else "create",
            "category_id": cat_id,
            "category_exists": cat_id is not None,
            "slug": slug,
            "existing_id": existing["id"] if existing else None,
        }

    if cat_id is None:
        cat_id = _create_category(sess, base)

    payload = {
        "title": title,
        "content": content_html,
        "excerpt": excerpt,
        "slug": slug,
        "status": "publish",
        "categories": [cat_id],
        "comment_status": "closed",
        "ping_status": "closed",
    }

    # 대표 기사 이미지: 같은 주 글에 아직 대표이미지가 없을 때만 업로드(재실행 중복 방지)
    if image and not (existing and existing.get("featured_media")):
        try:
            data, content_type, _ = image
            ext = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
                   "image/webp": "webp", "image/gif": "gif"}.get(content_type, "jpg")
            filename = f"wd-cover-{slug}.{ext}"  # 주차별 고유 파일명(파일명 충돌→엑박 방지)
            media_id = _upload_media(sess, base, data, filename, content_type, alt=title)
            # 업로드 후 실제 파일이 200/이미지인지 검증. webp 변환 실패 등으로 깨졌으면
            # featured 적용하지 않고 테마 그라데이션 폴백(엑박 방지).
            meta = sess.get(f"{base}/media/{media_id}", timeout=TIMEOUT).json()
            src = meta.get("source_url", "")
            ok = False
            if src:
                vr = sess.get(src, timeout=TIMEOUT)
                ok = vr.status_code == 200 and vr.headers.get("content-type", "").startswith("image/")
            if ok:
                payload["featured_media"] = media_id
            else:
                print(f"대표이미지 파일 검증 실패 → 그라데이션 폴백 (media={media_id}, src={src})")
        except requests.RequestException as e:
            print(f"대표이미지 업로드 실패(본문은 정상 발행): {e}")

    if existing:
        r = sess.post(f"{base}/posts/{existing['id']}", json=payload, timeout=TIMEOUT)
        action = "update"
    else:
        r = sess.post(f"{base}/posts", json=payload, timeout=TIMEOUT)
        action = "create"
    r.raise_for_status()
    post = r.json()
    return {
        "action": action,
        "id": post["id"],
        "link": post.get("link"),
        "status": post.get("status"),
        "category_id": cat_id,
    }
