# 요양·실버 주간 다이제스트

실버케어플러스 전략기획팀용 주간 동향 다이제스트. 요양·복지 전문매체 RSS를 모아
1차 키워드 필터로 거르고, LLM이 시사성 기준으로 테마별 동향을 종합해 주 1회 이메일로 발송한다.

## 파이프라인

```
수집(3소스 RSS) → 1차 필터(키워드+지역단신 탐지) → 2차 종합(LLM, 시사성 선별) → 렌더(HTML) → 발송(SMTP)
```

- **소스 3개**: 요양뉴스(메인, 무필터) · 보건복지부 보도자료(1차 소스, 키워드필터) · 복지타임스(보조, 키워드필터)
- **지역단신 격리**: 단일 지자체 단발 단신이 메인을 점령하던 예전 문제 방지.
  1차에서 `[지역명]+행사동사` 플래그만 부착, 2차 LLM이 시사성으로 메인/현장 버킷 분리.

## 설정

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # 키/SMTP 채우기
```

## 실행

```bash
python main.py --dry-run      # 수집·필터만, 통계 확인 (LLM/발송 없음)
python main.py --build        # + 종합 → out/digest.html 저장
python main.py --send         # + 이메일 발송
```

## 모델

종합은 기본 `claude-opus-4-8`(`.env`의 `DIGEST_MODEL`로 교체). 주 1회라 비용은 무시 가능,
종합 품질이 핵심이라 Opus 기본. 비용을 줄이려면 `claude-sonnet-4-6`.

## 알려진 TODO

- 요양뉴스 섹션 코드(실버경제/돌봄현장) 확정 → 시니어정책+실버경제만 main 피드,
  돌봄현장은 단신풀로 분리. (현재 v1은 전체피드 + 2차 LLM 시사성 선별로 대체)
- "조용한 주" 처리 규칙(최소분량/빈주 대응) — 1~2주 실수집 데이터 보고 결정 예정.
- 스케줄링(주 1회 자동 실행) — Windows 작업 스케줄러 또는 cron.
