#!/usr/bin/env python
"""기발행 글의 관련기사를 새 규칙으로 정리(1회성):
링크(<a>) 있는 기사만 남기고, 구분자 ' · ' → <br> 줄바꿈. 링크 0건이면 단락 제거.
사용:  .venv/bin/python wordpress/tidy_related.py 4853 [--apply]
"""
import os
import re
import sys

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))

POST_ID = next((a for a in sys.argv[1:] if a.isdigit()), None)
APPLY = "--apply" in sys.argv
if not POST_ID:
    sys.exit("사용: tidy_related.py <post_id> [--apply]")

base = os.environ["WP_BASE_URL"].rstrip("/") + "/wp-json/wp/v2"
auth = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"].replace(" ", ""))

p = requests.get(f"{base}/posts/{POST_ID}", params={"context": "edit"}, auth=auth, timeout=30).json()
raw = p["content"]["raw"]
print(f"글 '{p['title']['raw'][:40]}'\n")

def tidy(m):
    inner = m.group(1)
    lab = re.search(r"<b>.*?</b>", inner, re.S)
    label = lab.group(0) if lab else "<b>관련 기사</b>"
    anchors = re.findall(r"<a\s[^>]*>.*?</a>", inner, re.S)
    kept = len(anchors)
    titles = [re.sub(r"<[^>]+>", "", a).strip() for a in anchors]
    dropped = [t.strip() for t in re.split(r"\s+·\s+", re.sub(r"<a\s[^>]*>.*?</a>", "", re.sub(r"<b>.*?</b>", "", inner, 1), flags=re.S)) if t.strip()]
    print(f"  유지(링크) {kept}건: " + " / ".join(t[:30] for t in titles))
    if dropped:
        print(f"  제거(링크없음) {len(dropped)}건: " + " / ".join(d[:30] for d in dropped))
    if not anchors:
        print("  → 링크 0건, 단락 삭제")
        return ""
    body = "<br>".join(anchors)
    return f'<p class="cwd-src">{label}\n      {body}\n    </p>'

new, n = re.subn(r'<p class="cwd-src">(.*?)</p>', tidy, raw, flags=re.S)
print(f"\ncwd-src 단락 {n}개 처리")

if APPLY and new != raw:
    r = requests.post(f"{base}/posts/{POST_ID}", json={"content": new}, auth=auth, timeout=60)
    print(f"반영 HTTP {r.status_code}")
elif not APPLY:
    print("조회만(미반영). 실제 반영하려면 --apply")
