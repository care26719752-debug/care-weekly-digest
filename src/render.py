"""다이제스트 JSON → HTML 이메일 본문."""
from __future__ import annotations

import re
from datetime import date

from jinja2 import Template

_NORM_RE = re.compile(r"[\s\W]+", re.UNICODE)


def _norm(s: str) -> str:
    return _NORM_RE.sub("", s or "")


def _resolve_sources(sources, link_map) -> list[dict]:
    """LLM이 돌려준 source 제목을 수집 단계의 링크와 매칭. 못 찾으면 url="" (텍스트)."""
    norm_map = {_norm(t): u for t, u in (link_map or {}).items()}
    return [{"title": s, "url": norm_map.get(_norm(s), "")} for s in (sources or [])]

_TEMPLATE = Template(
    """\
<!doctype html>
<html lang="ko"><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f4f4f2;font-family:'Apple SD Gothic Neo',Pretendard,sans-serif;color:#222;">
  <div style="max-width:640px;margin:0 auto;padding:24px;">
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


def render_html(digest: dict, period: str | None = None, link_map: dict | None = None) -> str:
    axes = []
    for ax in digest.get("axes", []):
        ax = dict(ax)
        ax["related"] = _resolve_sources(ax.get("sources"), link_map)[:3]  # 최대 3개
        axes.append(ax)
    ctx = {**digest, "axes": axes}
    return _TEMPLATE.render(digest=ctx, period=period or date.today().isoformat())


def subject(digest: dict | None = None, when: date | None = None) -> str:
    when = when or date.today()
    week = (when.day - 1) // 7 + 1  # 그 달의 n주차
    return f"[{when.year}년 {when.month}월 {week}주 요양·실버 주간 다이제스트]"
