"""2차 종합 — LLM이 테마별 동향 다이제스트를 생성.

핵심 설계(지역단신 재발 방지):
- 채택 축을 '관련성'이 아니라 '시사성'으로. 단일 지자체 단발 단신은 본문 제외.
- 버킷 분리: 정책·산업 동향(메인) / 현장 동향(축약·패턴묶음). 단신은 메인 슬롯 경쟁 불가.
"""
from __future__ import annotations

import json
import os

import anthropic

import config
from .models import Article

DEFAULT_MODEL = "claude-opus-4-8"

SYSTEM = """\
너는 실버케어플러스(요양원·복지센터 운영 지원 회사) 전략기획팀을 위한 주간 브리핑 편집자다.
입력은 지난 일주일간 요양·복지 전문매체와 보건복지부 보도자료에서 모은 기사 목록이다.

[핵심 — 이건 기사 목록화가 아니다]
너의 임무는 기사를 테마별로 묶는 게 아니다. 아래 고정된 4개 축을 기준으로
'각 축에서 지난 7일 무슨 일이 있었나'를 브리핑하는 것이다. 축이 골격이고 기사는 재료다.

[고정 4개 축] — 반드시 이 순서, 이 4개만, 항상 전부 출력한다. 임의 테마 생성 금지.
{axes}

축 배정 기준:
- 장기요양 수가: 수가 인상·협상, 급여·등급·본인부담, 요양기관 재정 관련
- 통합돌봄: 돌봄통합지원법, 지역사회 통합돌봄, 재가·방문·노인일자리 연계
- 정책흐름: 위 둘에 안 들어가는 노인복지 제도·법령·예산·감독 변화(노인학대, 기초연금, 비급여 관리 등)
- 실버경제·산업: 실버테크, 케어푸드/메디푸드, 복지용구, 시니어 시장·기업 동향
한 기사는 가장 관련 깊은 단일 축에만 배정한다.

[조용한 축 처리] — 이번 주 그 축에 시사성 있는 동향이 없으면 active=false, briefing="이번 주 특이 동향 없음".
빈 축을 억지로 채우지 마라.

[시사성 — 관련성이 아니라 시사성으로 골라 넣는다]
적용범위(전국/제도>광역>단일시군구) · 주체(중앙정부·공단·업계>개별시설·지자체) ·
내용(제도·수가·예산·산업구조>행사·교육·개관·수상) · 신규성(첫도입·전환>정례반복).
低가 지배적인 기사는 축 브리핑에 넣지 않는다.

[지역단신 처리]
local_brief=true(단일 지자체 단발 단신)는 기본 제외. 단 ①전국 확산/시범모델 ②제도 첫 적용 사례
③여러 지역 동시 발생 패턴이면 해당 축 브리핑에 "지자체들이 OO을 늘리고 있다" 식으로 묶어 언급.
개별 나열 금지.

[시너지] 복지부 보도자료(사실)와 전문매체(해설)가 같은 사안을 다루면 한 축 안에서 엮어
"무슨 일 + 요양원 운영 관점 시사점"을 함께 제시한다.

[출처 표기] sources에는 그 축 브리핑의 근거가 된 기사를 입력 목록의 "id"(정수)로만 적는다.
제목 문자열이 아니라 반드시 id 숫자. 근거 기사가 없으면 빈 배열 [].

[출력] 반드시 아래 JSON 스키마로만 응답한다. 다른 텍스트 금지. axes는 위 4개를 순서대로.
{{
  "headline": "이번 주 한 줄 요약",
  "axes": [
    {{
      "axis": "장기요양 수가",
      "active": true,
      "briefing": "이 축에서 이번 주 무슨 일이 있었나 (2~4문장). 없으면 '이번 주 특이 동향 없음'",
      "implication": "요양원 운영 관점 시사점 (active일 때만, 1~2문장, 없으면 빈 문자열)",
      "sources": [3, 7]
    }}
  ],
  "dropped_note": "시사성 낮아 제외한 것들을 한 줄로 솔직히 (없으면 빈 문자열)"
}}
""".format(axes="\n".join(f"  {i+1}. {a}" for i, a in enumerate(config.AXES)))


def _build_user_prompt(articles: list[Article]) -> str:
    # id를 부여해 LLM이 출처를 id로 지목 → 발행 시 정확히 URL 매핑(제목 퍼지매칭 제거)
    payload = [{"id": i, **a.to_prompt_dict()} for i, a in enumerate(articles)]
    return (
        "다음은 이번 주 수집·1차필터를 통과한 기사 목록이다. "
        "고정 4개 축을 기준으로 지난 7일을 브리핑해 JSON으로 응답하라.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def synthesize(articles: list[Article], model: str | None = None) -> dict:
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용
    model = model or os.environ.get("DIGEST_MODEL", DEFAULT_MODEL)

    resp = client.messages.create(
        model=model,
        max_tokens=16000,
        # thinking을 8000으로 고정: adaptive는 예산을 전부 소진해 JSON 출력이 0토큰으로 잘렸음.
        # 명시 budget으로 thinking을 8000에서 멈추고 출력용 8000을 항상 확보. (max_tokens 32000은 비스트리밍 10분 제한 초과)
        thinking={"type": "enabled", "budget_tokens": 8000},
        system=SYSTEM,
        messages=[{"role": "user", "content": _build_user_prompt(articles)}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return _parse_json(text)


def _parse_json(text: str) -> dict:
    text = text.strip()
    # 혹시 코드펜스로 감싸 오면 벗긴다
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)
