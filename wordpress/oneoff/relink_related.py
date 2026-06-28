#!/usr/bin/env python
"""기발행 다이제스트 글의 관련기사(텍스트)에 링크 복구 (1회성).

이번 주 기사를 재수집해 title→url 맵을 만들고, 글 본문 cwd-src 안의
관련기사 제목을 퍼지매칭해 <a>로 감싼다.
사용:
  조회만:  .venv/bin/python wordpress/relink_related.py 4853
  실제반영: .venv/bin/python wordpress/relink_related.py 4853 --apply
"""
import os
import re
import sys
from difflib import SequenceMatcher

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
load_dotenv(os.path.join(HERE, "..", ".env"))

import config
from src import collect, filter as ffilter

POST_ID = next((a for a in sys.argv[1:] if a.isdigit()), None)
APPLY = "--apply" in sys.argv
if not POST_ID:
    sys.exit("사용: relink_related.py <post_id> [--apply]")

base = os.environ["WP_BASE_URL"].rstrip("/") + "/wp-json/wp/v2"
auth = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"].replace(" ", ""))

_norm_re = re.compile(r"[\s\W]+", re.UNICODE)
def norm(s):
    return _norm_re.sub("", (s or "")).lower()

# 1) 이번 주 기사 재수집 → title→url
days = int(os.environ.get("WINDOW_DAYS", "7"))
collected = collect.collect_all(config.SOURCES, days)
kept = ffilter.apply(config.SOURCES, collected)
cands = [(a.title, a.link) for a in kept if a.link]
print(f"재수집 기사 {len(cands)}건")

def best_match(title):
    nt = norm(title)
    best, score = None, 0.0
    for ct, url in cands:
        nc = norm(ct)
        if not nc:
            continue
        if nt and (nt in nc or nc in nt):
            r = 0.95
        else:
            r = SequenceMatcher(None, nt, nc).ratio()
        if r > score:
            best, score = (ct, url), r
    return best, score

# 2) 글 본문 로드
p = requests.get(f"{base}/posts/{POST_ID}", params={"context": "edit"}, auth=auth, timeout=30).json()
raw = p["content"]["raw"]
print(f"글 '{p['title']['raw'][:40]}'\n")

THRESHOLD = 0.6
n_link = 0

def repl_src(m):
    global n_link
    inner = m.group(1)
    # <b>관련 기사</b> 라벨 분리
    lab = re.match(r"\s*(<b>.*?</b>)\s*", inner, re.S)
    label = lab.group(1) if lab else ""
    rest = inner[lab.end():] if lab else inner
    # 이미 <a>가 있으면 건드리지 않음
    if "<a " in rest:
        return m.group(0)
    titles = [t.strip() for t in re.split(r"\s+·\s+", rest.strip()) if t.strip()]
    out = []
    for t in titles:
        (cand, score) = best_match(t)
        if cand and score >= THRESHOLD:
            n_link += 1
            print(f"  ✓ {score:.2f} | {t[:42]}\n        → {cand[0][:42]}\n        {cand[1]}")
            out.append(f'<a href="{cand[1]}" target="_blank" rel="noopener">{t}</a>')
        else:
            sc = f"{score:.2f}" if cand else "—"
            print(f"  ✗ {sc} | {t[:42]}  (매칭 실패, 텍스트 유지)")
            out.append(t)
    return f'<p class="cwd-src">{label}\n      ' + " · ".join(out) + "\n    </p>"

new = re.sub(r'<p class="cwd-src">(.*?)</p>', repl_src, raw, flags=re.S)
print(f"\n링크 연결 {n_link}건")

if APPLY and new != raw:
    r = requests.post(f"{base}/posts/{POST_ID}", json={"content": new}, auth=auth, timeout=60)
    print(f"반영 HTTP {r.status_code}")
elif not APPLY:
    print("조회만(미반영). 실제 반영하려면 --apply")
