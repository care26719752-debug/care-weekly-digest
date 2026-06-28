#!/usr/bin/env python
"""기발행 다이제스트 글에서 cwd-impl '시사점 ·' 라벨 제거 (1회성 패치).

본문에 박힌  <b>시사점</b> · {내용}  →  {내용}  으로 치환.
사용:
  조회만:  .venv/bin/python wordpress/strip_impl_label.py
  실제반영: .venv/bin/python wordpress/strip_impl_label.py --apply
"""
import os
import re
import sys

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))

APPLY = "--apply" in sys.argv
base = os.environ["WP_BASE_URL"].rstrip("/") + "/wp-json/wp/v2"
auth = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"].replace(" ", ""))
slug = os.environ["WP_CATEGORY_SLUG"]

# 시사점 라벨 패턴: <b>시사점</b> 와 뒤따르는 가운뎃점/공백
PAT = re.compile(r"<b>\s*시사점\s*</b>\s*[·•]?\s*")

sess = requests.Session()
sess.auth = auth

cat = sess.get(f"{base}/categories", params={"slug": slug}, timeout=30).json()
cat_id = cat[0]["id"] if cat else None
print(f"category id={cat_id}")

posts = sess.get(
    f"{base}/posts",
    params={"categories": cat_id, "per_page": 100, "status": "publish", "context": "edit"},
    timeout=60,
).json()
print(f"글 {len(posts)}개 조회")

changed = 0
for p in posts:
    raw = p["content"]["raw"]
    hits = len(PAT.findall(raw))
    if not hits:
        continue
    changed += 1
    new = PAT.sub("", raw)
    print(f"- id={p['id']} '{p['title']['raw'][:40]}' : 시사점 라벨 {hits}곳")
    if APPLY:
        r = sess.post(f"{base}/posts/{p['id']}", json={"content": new}, timeout=60)
        print(f"    → 반영 HTTP {r.status_code}")

print(f"\n{'반영 완료' if APPLY else '조회만(미반영)'} · 대상 글 {changed}개")
if not APPLY and changed:
    print("실제 반영하려면 --apply 붙여 다시 실행")
