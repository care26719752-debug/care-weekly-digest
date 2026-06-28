"""다이제스트 JSON → HTML 이메일 본문."""
from __future__ import annotations

import re
from datetime import date

from jinja2 import Template

_NORM_RE = re.compile(r"[\s\W]+", re.UNICODE)


def _norm(s: str) -> str:
    return _NORM_RE.sub("", s or "")


# 썸네일 없는 기사용 색상 플레이스홀더 팔레트 (id로 결정적 선택)
_REL_PALETTE = [
    ("#6b8cff", "#3b53d8"), ("#ff9e6b", "#ef5f53"), ("#3fc9a6", "#2a9d8f"),
    ("#a78bfa", "#6c5ce7"), ("#ff8fb0", "#e84a7f"), ("#5fb6e5", "#2d7fc7"),
]


def _resolve_sources(sources, source_map) -> list[dict]:
    """LLM이 지목한 기사 id를 관련기사 항목으로 해석. source_map: {id(int): {'title','url','thumb','source'}}.
    링크(URL)가 있는 기사만 노출. thumb 없으면 색상 플레이스홀더(팔레트+출처명)로 표시."""
    out = []
    for s in sources or []:
        if isinstance(s, str) and s.strip().isdigit():
            s = int(s.strip())
        if isinstance(s, int):
            a = (source_map or {}).get(s)
            if a and a.get("url"):
                c0, c1 = _REL_PALETTE[s % len(_REL_PALETTE)]
                out.append({
                    "title": a.get("title", ""),
                    "url": a["url"],
                    "thumb": a.get("thumb", ""),
                    "ph": (a.get("source") or "기사").split()[0][:5],
                    "c0": c0, "c1": c1,
                })
    return out

_TEMPLATE = Template(
    """\
<!doctype html>
<html lang="ko"><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f4f4f2;font-family:'Apple SD Gothic Neo',Pretendard,sans-serif;color:#222;">
  <div style="max-width:680px;margin:0 auto;padding:24px;">
    <p style="font-size:13px;color:#888;margin:0 0 4px;">실버케어플러스 · 요양·실버 주간 다이제스트</p>
    <h1 style="font-size:21px;font-weight:800;margin:0 0 4px;">{{ digest.headline }}</h1>
    <p style="font-size:13px;color:#888;margin:0 0 20px;">{{ period }}</p>

    {% for ax in digest.axes %}
      <div style="margin:18px 0;padding:14px 16px;background:#fff;border-radius:8px;border-left:4px solid {{ '#1f6fb2' if ax.active else '#cccccc' }};">
        <h2 style="font-size:17px;margin:0 0 8px;color:{{ '#1f6fb2' if ax.active else '#aaa' }};">{{ ax.axis }}</h2>
        <p style="font-size:16px;line-height:1.7;margin:0 0 10px;color:{{ '#222' if ax.active else '#999' }};">{{ ax.briefing }}</p>
        {% if ax.active and ax.implication %}
        <p style="font-size:14px;line-height:1.6;margin:0;padding:10px 12px;background:#eef4fa;border-radius:6px;">
          <strong>시사점</strong> · {{ ax.implication }}</p>
        {% endif %}
        {% if ax.related %}
        <p style="font-size:14px;color:#777;margin:12px 0 0;line-height:1.8;">
          <strong style="color:#555;">관련 기사</strong><br>
          {% for r in ax.related %}
            {% if r.url %}<a href="{{ r.url }}" style="color:#1f6fb2;text-decoration:none;">{{ r.title }}</a>{% else %}{{ r.title }}{% endif %}{% if not loop.last %}<br>{% endif %}
          {% endfor %}
        </p>
        {% endif %}
      </div>
    {% endfor %}
  </div>
</body></html>
"""
)


def render_html(digest: dict, period: str | None = None, source_map: dict | None = None) -> str:
    axes = []
    for ax in digest.get("axes", []):
        ax = dict(ax)
        ax["related"] = _resolve_sources(ax.get("sources"), source_map)[:3]  # 최대 3개
        axes.append(ax)
    ctx = {**digest, "axes": axes}
    return _TEMPLATE.render(digest=ctx, period=period or date.today().isoformat())


def subject(digest: dict | None = None, when: date | None = None) -> str:
    when = when or date.today()
    week = (when.day - 1) // 7 + 1  # 그 달의 n주차
    return f"[{when.year}년 {when.month}월 {week}주 요양·실버 주간 다이제스트]"


# --- 워드프레스 본문용 (브런치식 읽기 레이아웃) ---
# 이메일과 달리 전체 <html> 문서가 아니라 글 '본문 조각'만 만든다.
# 테마와 독립적으로 보이도록 .cwd 네임스페이스로 스코프된 <style>을 본문에 포함한다.
# (관리자 계정은 unfiltered_html 권한이 있어 REST 발행 시 <style>이 보존됨)
_WEB_TEMPLATE = Template(
    """\
<style>
.cwd{max-width:900px;margin:0 auto;font-size:17px;line-height:1.9;color:#1a1a1a;
     font-family:'Apple SD Gothic Neo',Pretendard,-apple-system,'Noto Sans KR',sans-serif;}
.cwd .cwd-kicker{font-size:13px;letter-spacing:.02em;color:#666;margin:0 0 6px;}
.cwd .cwd-period{font-size:14px;color:#666;margin:0 0 36px;}
.cwd .cwd-ax{margin:0 0 40px;}
.cwd .cwd-ax h2{font-size:16px;font-weight:500;margin:0 0 14px;padding:2px 14px;
     background:#1a1a1a;color:#fff;display:inline-block;}
.cwd .cwd-ax.muted h2{background:#d6d6d6;color:#fff;}
.cwd .cwd-brief{margin:0 0 24px;color:#222;font-size:17px;font-weight:400;line-height:1.9;}
.cwd .cwd-ax.muted .cwd-brief{color:#8a8a8a;}
.cwd .cwd-impl{margin:0;padding:14px 18px;background:#f3f7fb;border-radius:10px;
     font-size:15.5px;line-height:1.7;color:#26415a;}
.cwd .cwd-impl b{color:#1f6fb2;}
.cwd .cwd-src{margin:16px 0 0;font-size:14px;line-height:1.9;color:#555;}
.cwd .cwd-src b{display:block;margin-bottom:8px;color:#444;font-size:13px;}
.cwd .cwd-rel{display:flex;align-items:center;gap:11px;margin:7px 0;text-decoration:none;}
.cwd .cwd-rel-th{flex:0 0 auto;width:58px;height:43px;border-radius:6px;object-fit:cover;
     display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;
     font-weight:500;letter-spacing:-.01em;overflow:hidden;}
.cwd .cwd-rel-t{font-size:14px;line-height:1.45;color:#333;}
.cwd .cwd-rel:hover .cwd-rel-t{text-decoration:underline;}
.cwd .cwd-reco{margin:50px 0 0;padding-top:26px;border-top:2px solid #1a1a1a;}
.cwd .cwd-reco-h{font-size:18px;font-weight:500;letter-spacing:-.01em;margin:0 0 18px;color:#1a1a1a;}
.cwd .cwd-reco-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px 16px;}
.cwd .cwd-reco .cwd-rel{flex-direction:column;align-items:stretch;gap:0;margin:0;}
.cwd .cwd-reco .cwd-rel-th{width:100%;height:auto;aspect-ratio:4/3;border-radius:8px;margin-bottom:9px;font-size:13px;}
.cwd .cwd-reco .cwd-rel-t{font-size:13.5px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}
.cwd .cwd-reco .cwd-rel-src{display:block;font-size:12px;color:#9a9a9a;margin-top:5px;}
@media(max-width:680px){.cwd .cwd-reco-grid{grid-template-columns:repeat(2,1fr);}}
</style>
<div class="cwd">
  {% for ax in digest.axes %}
  <section class="cwd-ax{{ '' if ax.active else ' muted' }}">
    <h2>{{ ax.axis }}</h2>
    <p class="cwd-brief">{{ ax.briefing }}</p>
    {% if ax.active and ax.implication %}
    <p class="cwd-impl">{{ ax.implication }}</p>
    {% endif %}
  </section>
  {% endfor %}
  {% if digest.recommends %}
  <div class="cwd-reco">
    <h2 class="cwd-reco-h">추천 뉴스</h2>
    <div class="cwd-reco-grid">{% for r in digest.recommends %}<a class="cwd-rel" href="{{ r.url }}" target="_blank" rel="noopener">{% if r.thumb %}<img class="cwd-rel-th" src="{{ r.thumb }}" alt="" loading="lazy">{% else %}<span class="cwd-rel-th cwd-rel-ph" style="background:linear-gradient(135deg,{{ r.c0 }},{{ r.c1 }})">{{ r.ph }}</span>{% endif %}<span class="cwd-rel-t">{{ r.title }}<span class="cwd-rel-src">{{ r.source }}</span></span></a>{% endfor %}</div>
  </div>
  {% endif %}
</div>
"""
)


def _decorate_rel(items: list[dict]) -> list[dict]:
    """추천/관련 항목에 팔레트 색·플레이스홀더 라벨을 부여. items: [{title,url,thumb?,source?}]."""
    out = []
    for i, it in enumerate(items or []):
        c0, c1 = _REL_PALETTE[i % len(_REL_PALETTE)]
        out.append({
            "title": it.get("title", ""),
            "url": it.get("url") or it.get("link", ""),
            "thumb": it.get("thumb", ""),
            "source": it.get("source", ""),
            "ph": (it.get("source") or "뉴스").split()[0][:5],
            "c0": c0, "c1": c1,
        })
    return out


def render_post_content(digest: dict, period: str | None = None,
                        recommends: list[dict] | None = None) -> str:
    """워드프레스 글 본문(HTML 조각)을 만든다. 4개 축 요약 + 하단 추천 뉴스."""
    axes = [dict(ax) for ax in digest.get("axes", [])]
    ctx = {**digest, "axes": axes, "recommends": _decorate_rel(recommends)}
    return _WEB_TEMPLATE.render(digest=ctx, period=period or date.today().isoformat())
