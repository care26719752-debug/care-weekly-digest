#!/usr/bin/env python
"""weekly-digest-snippet.php → 워드프레스 Code Snippets(id 9)에 푸시(배포).

UI 수정 워크플로:
  1) wordpress/weekly-digest-snippet.php 편집
  2) 이 스크립트 실행 → 라이브 즉시 반영
사용: .venv/bin/python wordpress/deploy_snippet.py
"""
import os
import sys

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))

SNIPPET_ID = 9
root = os.environ["WP_BASE_URL"].rstrip("/") + "/wp-json/code-snippets/v1"
auth = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"].replace(" ", ""))

raw = open(os.path.join(HERE, "weekly-digest-snippet.php"), encoding="utf-8").read()
code = raw.split("*/", 1)[1].strip()  # 맨 위 블록주석 이후 본문만

payload = {
    "id": SNIPPET_ID,
    "name": "Weekly Digest Unlisted",
    "desc": "주간 다이제스트: 비공개 링크화 + 브런치풍 독립 렌더(테마 우회)",
    "code": code,
    "scope": "global",
    "active": True,
    "priority": 10,
}
r = requests.post(f"{root}/snippets/{SNIPPET_ID}", json=payload, auth=auth, timeout=30)
d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
print(f"배포 HTTP {r.status_code} | active: {d.get('active')} | code_error: {d.get('code_error')}")
print("목록: https://silvercareplus.co.kr/category/wd-brief-k7m3q9x2/")
sys.exit(0 if r.status_code == 200 and not d.get("code_error") else 1)
