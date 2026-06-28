#!/usr/bin/env python
"""기발행 글의 관련기사를 썸네일 행 구조로 백필(1회성).
기존 <a> 링크마다: og:image 있으면 WP 미디어 업로드→실사진, 없으면 색상 플레이스홀더.
사용:  .venv/bin/python wordpress/backfill_thumbs.py 4853 [--apply]
"""
import os
import re
import sys

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
load_dotenv(os.path.join(HERE, "..", ".env"))

from src import image as imagemod, publish
from src.render import _REL_PALETTE

POST_ID = next((a for a in sys.argv[1:] if a.isdigit()), None)
APPLY = "--apply" in sys.argv
if not POST_ID:
    sys.exit("사용: backfill_thumbs.py <post_id> [--apply]")

base = publish._base()
sess = requests.Session()
sess.auth = publish._auth()

HOST_SRC = {"yoyangnews.co.kr": "요양뉴스", "bokjitimes.com": "복지타임스", "korea.kr": "보건복지부"}
def source_label(url):
    for h, s in HOST_SRC.items():
        if h in url:
            return s
    return re.sub(r"^www\.", "", re.sub(r"https?://([^/]+).*", r"\1", url))[:5]

p = sess.get(f"{base}/posts/{POST_ID}", params={"context": "edit"}, timeout=30).json()
raw = p["content"]["raw"]
print(f"글 '{p['title']['raw'][:40]}'\n")

counter = {"i": 0}

def real_thumb(url, title):
    try:
        res = imagemod.fetch_og_image(url)
    except requests.RequestException:
        return ""
    if not res:
        return ""
    data, ct, fn = res
    try:
        mid = publish._upload_media(sess, base, data, f"rel-bf-{counter['i']}-{fn}", ct, alt=title)
        return sess.get(f"{base}/media/{mid}", timeout=30).json().get("source_url", "")
    except requests.RequestException:
        return ""

def build_row(href, title):
    i = counter["i"]; counter["i"] += 1
    c0, c1 = _REL_PALETTE[i % len(_REL_PALETTE)]
    th = real_thumb(href, title)
    if th:
        thumb_html = f'<img class="cwd-rel-th" src="{th}" alt="" loading="lazy">'
        kind = "실사진"
    else:
        ph = source_label(href)
        thumb_html = f'<span class="cwd-rel-th cwd-rel-ph" style="background:linear-gradient(135deg,{c0},{c1})">{ph}</span>'
        kind = f"플레이스홀더({ph})"
    print(f"  • {kind:18} | {title[:38]}")
    return (f'<a class="cwd-rel" href="{href}" target="_blank" rel="noopener">'
            f'{thumb_html}<span class="cwd-rel-t">{title}</span></a>')

def conv(m):
    inner = m.group(1)
    anchors = re.findall(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', inner, re.S)
    if not anchors:
        return ""  # 링크 0건 → 단락 제거
    rows = "".join(build_row(href, re.sub(r"\s+", " ", t).strip()) for href, t in anchors)
    return f'<div class="cwd-src"><b>관련 기사</b>\n      {rows}\n    </div>'

new, n = re.subn(r'<p class="cwd-src">(.*?)</p>', conv, raw, flags=re.S)
print(f"\ncwd-src 단락 {n}개 변환")

if APPLY and new != raw:
    r = sess.post(f"{base}/posts/{POST_ID}", json={"content": new}, timeout=60)
    print(f"반영 HTTP {r.status_code}")
elif not APPLY:
    print("조회만(미반영). 실제 반영하려면 --apply")
