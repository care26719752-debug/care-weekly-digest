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


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="수집·필터만")
    ap.add_argument("--build", action="store_true", help="+ 종합 → HTML 저장")
    ap.add_argument("--send", action="store_true", help="+ 이메일 발송")
    args = ap.parse_args()
    if not (args.dry_run or args.build or args.send):
        args.dry_run = True  # 기본은 안전한 dry-run

    collected, kept = run_collect_filter()
    print_stats(collected, kept)

    if not kept:
        print("\n채택 기사가 없어 종합을 건너뜁니다.")
        return

    if args.dry_run and not (args.build or args.send):
        return

    # --- 2차 종합 (LLM) ---
    from src import synthesize, render

    print("\n종합 중...")
    digest = synthesize.synthesize(kept)
    link_map = {a.title: a.link for a in kept if a.link}
    html = render.render_html(digest, link_map=link_map)
    subject = render.subject(digest)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "digest.html").write_text(html, encoding="utf-8")
    (OUT_DIR / "digest.json").write_text(
        json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"저장: {OUT_DIR/'digest.html'}")
    print(f"제목: {subject}")

    if args.send:
        from src import send

        send.send_email(subject, html)
        print("발송 완료.")


if __name__ == "__main__":
    sys.exit(main())
