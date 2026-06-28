"""요양·실버 주간 다이제스트 — 파이프라인 오케스트레이션.

  python main.py --dry-run     # 수집·필터만, 통계 출력 (LLM/발송 없음)
  python main.py --build       # + 종합 → out/digest.html 저장 (발송 안 함)
  python main.py --send        # + 이메일 발송
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Windows 콘솔에서 한글이 깨지지 않게 stdout을 UTF-8로
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

import config
from src import collect, filter as ffilter

OUT_DIR = Path(__file__).parent / "out"


def _window_days() -> int:
    return int(os.environ.get("WINDOW_DAYS", "7"))


def run_collect_filter():
    collected = collect.collect_all(config.SOURCES, _window_days())
    kept = ffilter.apply(config.SOURCES, collected)
    return collected, kept


def print_stats(collected, kept):
    print("=== 수집/필터 통계 ===")
    for src in config.SOURCES:
        raw = len(collected.get(src["key"], []))
        passed = sum(1 for a in kept if a.source_key == src["key"])
        flag = "무필터" if not src["filter"] else "키워드필터"
        print(f"  {src['name']:<16} 수집 {raw:>3}  채택 {passed:>3}  ({flag})")
    locals_ = sum(1 for a in kept if a.is_local_brief)
    print(f"  ---\n  총 채택 {len(kept)}건 (지역단신 플래그 {locals_}건)")
    print("\n=== 채택 기사 ===")
    for a in kept:
        mark = "📍" if a.is_local_brief else "  "
        kw = ",".join(a.matched_keywords[:3])
        print(f"  {mark} [{a.source_name}] {a.title}  {('<'+kw+'>') if kw else ''}")


def attach_reco_thumbs(recommends):
    """추천뉴스 각 링크의 og:image를 받아 WP 미디어에 올리고 item['thumb']에 채운다.
    이미지 없으면 비움 → 렌더에서 색상 플레이스홀더."""
    import requests

    from src import image as imagemod, publish

    base = publish._base()
    sess = requests.Session()
    sess.auth = publish._auth()
    n = 0
    for i, it in enumerate(recommends):
        url = it.get("link") or it.get("url")
        if not url:
            continue
        try:
            res = imagemod.fetch_og_image(url)
        except requests.RequestException:
            res = None
        if not res:
            continue  # 이미지 없음 → 플레이스홀더
        data, ct, fn = res
        try:
            mid = publish._upload_media(sess, base, data, f"reco-{i}-{fn}", ct, alt=it.get("title", ""))
            src = sess.get(f"{base}/media/{mid}", timeout=30).json().get("source_url", "")
            if src:
                it["thumb"] = src
                n += 1
        except requests.RequestException as e:
            print(f"  추천뉴스 썸네일 업로드 실패({i}): {e}")
    print(f"추천뉴스 썸네일: {n}/{len(recommends)} 적용 (이미지 없으면 플레이스홀더)")


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="수집·필터만")
    ap.add_argument("--build", action="store_true", help="+ 종합 → HTML 저장")
    ap.add_argument("--send", action="store_true", help="+ 이메일 발송")
    ap.add_argument("--publish", action="store_true", help="+ 워드프레스 발행")
    args = ap.parse_args()
    if not (args.dry_run or args.build or args.send or args.publish):
        args.dry_run = True  # 기본은 안전한 dry-run

    collected, kept = run_collect_filter()
    print_stats(collected, kept)

    if not kept:
        print("\n채택 기사가 없어 종합을 건너뜁니다.")
        return

    if args.dry_run and not (args.build or args.send or args.publish):
        return

    # --- 2차 종합 (LLM) ---
    from src import synthesize, render

    print("\n종합 중...")
    digest = synthesize.synthesize(kept)
    # 이메일 본문의 '관련 기사'(축 근거)용 — id(=kept 인덱스)→제목·URL·출처
    source_map = {
        i: {"title": a.title, "url": a.link, "source": a.source_name}
        for i, a in enumerate(kept)
    }
    # 추천 뉴스: 네이버 검색으로 축별 1건씩 큐레이션(디제스트에 쓴 링크는 제외)
    from src import recommend

    recommends = recommend.recommend_news(
        exclude_links=[a.link for a in kept if a.link], limit=4
    )
    print(f"추천 뉴스 {len(recommends)}건 수집")
    # 발행 시 추천뉴스 썸네일(og:image)을 WP 미디어에 올림. 없으면 색상 플레이스홀더.
    if args.publish and recommends:
        attach_reco_thumbs(recommends)

    html = render.render_html(digest, source_map=source_map)         # 이메일용 전체 문서
    post_html = render.render_post_content(digest, recommends=recommends)  # 워드프레스 본문 조각
    subject = render.subject(digest)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "digest.html").write_text(html, encoding="utf-8")
    (OUT_DIR / "digest.post.html").write_text(post_html, encoding="utf-8")
    (OUT_DIR / "digest.json").write_text(
        json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"저장: {OUT_DIR/'digest.html'}")
    print(f"제목: {subject}")

    if args.send:
        from src import send

        send.send_email(subject, html)
        print("발송 완료.")

    if args.publish:
        from src import publish, image as imagemod

        image = None
        res = imagemod.representative_image(digest, kept)
        if res:
            data, ct, fn, art = res
            image = (data, ct, fn)
            print(f"대표이미지: [{art.source_name}] {art.title[:34]}… ({len(data)//1024}KB)")
        else:
            print("대표이미지 없음 — 테마 그라데이션으로 발행")

        result = publish.publish_digest(
            subject, post_html, excerpt=digest.get("headline", ""), image=image
        )
        print(f"워드프레스 {result['action']}: {result.get('link')} (id={result.get('id')})")


if __name__ == "__main__":
    sys.exit(main())
