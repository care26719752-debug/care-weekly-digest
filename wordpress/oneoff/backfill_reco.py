#!/usr/bin/env python
"""기발행 글 백필(1회성): 관련기사 섹션 제거 + 하단 '추천 뉴스'(네이버 검색) 추가.
추천뉴스 썸네일은 og:image를 WP 미디어에 업로드(없으면 색상 플레이스홀더).
사용:  .venv/bin/python wordpress/backfill_reco.py 4853 [--apply]
"""
import os
import re
import sys

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
load_dotenv(os.path.join(HERE, "..", ".env"))

from src import image as imagemod, publish, recommend
from src.render import _decorate_rel

POST_ID = next((a for a in sys.argv[1:] if a.isdigit()), None)
APPLY = "--apply" in sys.argv
if not POST_ID:
    sys.exit("사용: backfill_reco.py <post_id> [--apply]")

base = publish._base()
sess = requests.Session()
sess.auth = publish._auth()

p = sess.get(f"{base}/posts/{POST_ID}", params={"context": "edit"}, timeout=30).json()
raw = p["content"]["raw"]
print(f"글 '{p['title']['raw'][:40]}'\n")

# 본문에 이미 걸린 링크는 추천에서 제외(중복 회피)
existing = re.findall(r'href="([^"]+)"', raw)
recos = recommend.recommend_news(exclude_links=existing, limit=4)
print(f"추천 뉴스 {len(recos)}건:")
for r in recos:
    print(f"  • [{r['source']}] {r['title'][:44]}")

# 썸네일 업로드(og:image → WP 미디어)
n = 0
for i, it in enumerate(recos):
    try:
        res = imagemod.fetch_og_image(it["link"])
    except requests.RequestException:
        res = None
    if not res:
        continue
    data, ct, fn = res
    try:
        mid = publish._upload_media(sess, base, data, f"reco-bf-{i}-{fn}", ct, alt=it["title"])
        src = sess.get(f"{base}/media/{mid}", timeout=30).json().get("source_url", "")
        if src:
            it["thumb"] = src
            n += 1
    except requests.RequestException as e:
        print(f"  썸네일 업로드 실패({i}): {e}")
print(f"썸네일: {n}/{len(recos)} 업로드 (없으면 플레이스홀더)\n")

# 추천뉴스 HTML 생성(render 템플릿과 동일 구조)
rows = []
for r in _decorate_rel(recos):
    if r["thumb"]:
        th = f'<img class="cwd-rel-th" src="{r["thumb"]}" alt="" loading="lazy">'
    else:
        th = (f'<span class="cwd-rel-th cwd-rel-ph" '
              f'style="background:linear-gradient(135deg,{r["c0"]},{r["c1"]})">{r["ph"]}</span>')
    rows.append(
        f'<a class="cwd-rel" href="{r["url"]}" target="_blank" rel="noopener">{th}'
        f'<span class="cwd-rel-t">{r["title"]}<span class="cwd-rel-src">{r["source"]}</span></span></a>'
    )
reco_html = ('<div class="cwd-reco"><h2 class="cwd-reco-h">추천 뉴스</h2>\n      '
             + "".join(rows) + "\n    </div>")

# 1) 관련기사(cwd-src) 블록 제거
new = re.sub(r'<(p|div) class="cwd-src">.*?</\1>', "", raw, flags=re.S)
# 2) .cwd 컨테이너 닫기 직전에 추천뉴스 삽입
idx = new.rfind("</div>")
if idx == -1:
    sys.exit("'.cwd' 닫는 </div>를 못 찾음 — 중단")
new = new[:idx] + "  " + reco_html + "\n" + new[idx:]

print("관련기사 제거:", "cwd-src" not in new, "| 추천뉴스 삽입:", "cwd-reco" in new)

if APPLY and new != raw:
    r = sess.post(f"{base}/posts/{POST_ID}", json={"content": new}, timeout=60)
    print(f"반영 HTTP {r.status_code}")
elif not APPLY:
    print("조회만(미반영). 실제 반영하려면 --apply")
