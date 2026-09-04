"""Build a side-by-side passage comparison for ontology-loop and TOPIK-style runs."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "pet_restaurant": "반려동물 동반 음식점",
    "energy_saving": "에너지 절약",
}
DECORATIVE_PATTERNS = [
    "주목받고 있", "적극적으로", "다양한", "이러한", "이 같은",
    "노력하고 있", "노력할 계획", "사회 전반", "자리 잡", "기여할 것으로",
    "실질적인 변화를 이끌", "확산될 수 있도록 노력", "기대된다",
]


def load_result(base: Path, source: str, grade: int) -> dict:
    path = base / source / f"grade_{grade}" / "result.json"
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def sentence_count(text: str) -> int:
    return len([part for part in re.split(r"[.!?]+", text) if part.strip()])


def decoration_hits(text: str) -> list[str]:
    return [pattern for pattern in DECORATIVE_PATTERNS if pattern in text]


def badge(passed: bool, true_label: str = "통과", false_label: str = "검토 필요") -> str:
    css = "pass" if passed else "review"
    label = true_label if passed else false_label
    return f'<span class="badge {css}">{esc(label)}</span>'


def version_panel(result: dict, label: str, css: str) -> str:
    passage = result.get("generated_passage", "")
    ontology = result.get("final_ontology_validation", {})
    ai = result.get("final_ai_validation", {})
    hits = decoration_hits(passage)
    hit_text = ", ".join(hits) if hits else "표시 표현 없음"
    repair = result.get("vocabulary_repair", {})
    audit = repair.get("after_audit") or (
        result.get("rounds", [{}])[-1].get("vocabulary_audit", {})
        if result.get("rounds") else {}
    )
    before_audit = repair.get("before_audit", audit)
    remaining = [item.get("word", "") for item in audit.get("violations", [])]
    remaining += [item.get("word", "") for item in audit.get("blocked_unknown_tokens", [])]
    vocab_text = ", ".join(filter(None, remaining)) or "없음"
    before_count = before_audit.get("violation_count", 0) + before_audit.get("blocked_unknown_token_count", 0)
    after_count = audit.get("violation_count", 0) + audit.get("blocked_unknown_token_count", 0)
    naturalness_label = (
        "채택" if repair.get("naturalness_accepted") else
        "미채택" if "naturalness_accepted" in repair else "해당 없음"
    )
    return f"""
      <article class="version {css}">
        <div class="version-head"><h3>{esc(label)}</h3>{badge(bool(ai.get('passed')), 'AI 통과', 'AI 검토')}</div>
        <div class="metrics">
          <span>{len(passage)}자</span><span>{sentence_count(passage)}문장</span>
          <span>생성 {esc(result.get('rounds_used', '-'))}회</span>
          {badge(bool(ontology.get('passed')), '온톨로지 통과', '온톨로지 진단')}
        </div>
        <div class="passage">{esc(passage)}</div>
        <div class="diagnostic"><b>상투적 꾸밈 표현 탐지:</b> {esc(hit_text)}</div>
        <div class="diagnostic"><b>급수 어휘 문제:</b> {before_count}개 → {after_count}개 · <b>남은 어휘:</b> {esc(vocab_text)}</div>
        <div class="diagnostic"><b>필수 용어 예외:</b> {esc(', '.join(result.get('source_terms', [])) or '없음')}</div>
        <div class="diagnostic"><b>자연스러움 후속 교정:</b> {esc(naturalness_label)}</div>
        <details><summary>판정 근거 보기</summary><pre>{esc(json.dumps({'ai': ai, 'ontology': ontology}, ensure_ascii=False, indent=2))}</pre></details>
      </article>"""


def card(source: str, grade: int, old: dict, new: dict) -> str:
    return f"""
    <section class="card" data-source="{source}" data-grade="{grade}">
      <div class="card-head"><div><div class="eyebrow">{esc(SOURCES[source])}</div><h2>{grade}급 · {esc(new.get('text_type', old.get('text_type', '읽기 지문')))}</h2></div></div>
      <div class="comparison">
        {version_panel(old, '기존 온톨로지 루프 적용본', 'old')}
        {version_panel(new, 'TOPIK 문장 경제성 + 급수 어휘 교정본', 'new')}
      </div>
    </section>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    candidate = args.candidate.resolve()
    cards = []
    records = []
    for source in SOURCES:
        for grade in range(1, 7):
            old = load_result(baseline, source, grade)
            new = load_result(candidate, source, grade)
            cards.append(card(source, grade, old, new))
            records.append((old, new))

    old_hits = sum(len(decoration_hits(old.get("generated_passage", ""))) for old, _ in records)
    new_hits = sum(len(decoration_hits(new.get("generated_passage", ""))) for _, new in records)
    vocab_before = 0
    vocab_after = 0
    for _, new in records:
        repair = new.get("vocabulary_repair", {})
        before = repair.get("before_audit", {})
        after = repair.get("after_audit", {})
        vocab_before += before.get("violation_count", 0) + before.get("blocked_unknown_token_count", 0)
        vocab_after += after.get("violation_count", 0) + after.get("blocked_unknown_token_count", 0)
    content = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>온톨로지·TOPIK 자연스러움 비교</title>
<style>
:root{{--ink:#172033;--muted:#66758a;--line:#dbe3ec;--bg:#f2f5f9;--blue:#285cc5;--green:#087552;--amber:#985800}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Pretendard,"Noto Sans KR","Malgun Gothic",sans-serif;line-height:1.68}}main{{max-width:1440px;margin:30px auto;padding:0 18px}}header,.guide,.card{{background:#fff;border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 25px #1b30490b}}header{{padding:32px;color:#fff;background:linear-gradient(135deg,#18396f,#326cd5)}}h1{{margin:0 0 8px;font-size:34px}}h2,h3{{margin:0}}.summary{{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}}.metric{{padding:10px 14px;border-radius:10px;background:#ffffff18;border:1px solid #ffffff35}}.guide{{margin:16px 0;padding:20px 24px}}.guide ul{{margin-bottom:0}}.filters{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}button{{border:1px solid #b8c7dc;background:#fff;border-radius:999px;padding:8px 14px;cursor:pointer}}button.active{{background:var(--blue);border-color:var(--blue);color:#fff}}.card{{padding:24px;margin:16px 0}}.card-head{{margin-bottom:14px}}.eyebrow,.diagnostic{{font-size:13px;color:var(--muted)}}.comparison{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.version{{border:1px solid var(--line);border-radius:14px;padding:18px;min-width:0}}.version.old{{background:#fbfcfe}}.version.new{{background:#f7fbff;border-color:#b9d0f2}}.version-head,.metrics{{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}}.metrics{{justify-content:flex-start;color:var(--muted);font-size:12px;margin:10px 0}}.metrics>span{{padding:2px 7px;background:#eef2f7;border-radius:6px}}.badge{{display:inline-block;padding:3px 8px;border-radius:999px;font-size:12px;font-weight:700}}.badge.pass{{background:#e4f6ee;color:var(--green)}}.badge.review{{background:#fff0d6;color:var(--amber)}}.passage{{white-space:pre-wrap;background:#fff;border:1px solid #e5ebf1;border-radius:10px;padding:16px;min-height:190px}}.diagnostic{{margin-top:10px}}details{{margin-top:10px}}summary{{cursor:pointer;font-weight:700}}pre{{white-space:pre-wrap;overflow:auto;background:#142033;color:#dce7f7;padding:12px;border-radius:9px;font-size:11px}}.hidden{{display:none}}@media(max-width:900px){{.comparison{{grid-template-columns:1fr}}h1{{font-size:28px}}}}
</style></head><body><main><header><h1>온톨로지 버전 vs TOPIK 자연스러움 버전</h1><p>같은 원자료와 같은 급수의 지문을 좌우로 비교합니다. 온톨로지는 두 버전 모두 사후 진단이며, 오른쪽 버전은 문장 경제성과 정보 연결을 강화했습니다.</p><div class="summary"><div class="metric">비교 지문 <b>12쌍</b></div><div class="metric">기존 꾸밈 표현 탐지 <b>{old_hits}건</b></div><div class="metric">새 버전 꾸밈 표현 탐지 <b>{new_hits}건</b></div></div></header>
<section class="guide"><h2>실제 TOPIK 자료를 반영한 비교 기준</h2><p><b>급수 어휘 문제 합계: {vocab_before}개 → {vocab_after}개</b></p><ul><li>문장마다 주된 정보 관계 하나를 두고, 앞 문장의 핵심 명사를 다음 문장이 구체화합니다.</li><li>분량을 채우는 평가·홍보·일반 전망은 제거하고 문항의 정답 근거가 되는 정보만 남깁니다.</li><li>접속부사는 실제 이유·대조·결과가 있을 때만 쓰며, 추상적인 지시어로 문장을 억지로 잇지 않습니다.</li><li>원자료의 기관·수치·대상·의무·금지 관계는 축약하더라도 방향을 바꾸지 않습니다.</li></ul><div class="filters"><button class="active" data-source="all">전체 주제</button><button data-source="pet_restaurant">반려동물 음식점</button><button data-source="energy_saving">에너지 절약</button>{''.join(f'<button data-grade="{g}">{g}급</button>' for g in range(1, 7))}</div></section>
{''.join(cards)}
</main><script>const cards=[...document.querySelectorAll('.card')],sourceButtons=[...document.querySelectorAll('[data-source]')].filter(x=>x.tagName==='BUTTON'),gradeButtons=[...document.querySelectorAll('[data-grade]')].filter(x=>x.tagName==='BUTTON');let source='all',grade=null;function apply(){{cards.forEach(c=>c.classList.toggle('hidden',!((source==='all'||c.dataset.source===source)&&(grade===null||c.dataset.grade===grade))))}}sourceButtons.forEach(b=>b.onclick=()=>{{source=b.dataset.source;sourceButtons.forEach(x=>x.classList.toggle('active',x===b));apply()}});gradeButtons.forEach(b=>b.onclick=()=>{{grade=grade===b.dataset.grade?null:b.dataset.grade;gradeButtons.forEach(x=>x.classList.toggle('active',x.dataset.grade===grade));apply()}});</script></body></html>"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
