"""Build one self-contained HTML report for the latest saved grades 1-6 experiments."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "experiments" / "all_grades_latest_experiment_report_2026-08-27.html"
SOURCES = {"pet_restaurant": "반려동물 동반 음식점", "energy_saving": "에너지 절약"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_result(source: str, grade: int) -> tuple[dict, str]:
    if grade <= 2:
        experiment = "naturalness_diagnostic_v5_2026-08-18"
    elif grade <= 4:
        experiment = "naturalness_diagnostic_v6_2026-08-22"
    else:
        experiment = "naturalness_diagnostic_v7_2026-08-22"
    path = ROOT / "experiments" / experiment / source / f"grade_{grade}" / "result.json"
    result = load(path)
    if grade in {3, 4}:
        fixed_path = (
            ROOT / "experiments" / "naturalness_diagnostic_v6_questions_fixed_2026-08-22"
            / source / f"grade_{grade}" / "result.json"
        )
        fixed = load(fixed_path)
        result["reading_items"] = fixed.get("reading_items", [])
        result["question_checks"] = fixed.get("question_checks", [])
        result["question_status"] = fixed.get("question_status", "NEEDS_HUMAN_REVIEW")
        result["status"] = (
            "PASS" if result.get("passage_status") == "PASS"
            and result["question_status"] == "PASS" else "NEEDS_HUMAN_REVIEW"
        )
        experiment += " + question normalization follow-up"
    return result, experiment


DIRECT_REVIEW = {
    ("pet_restaurant", 1): ("조건부", "구조는 개선됐지만 초급 어휘와 반복 여부를 전문가가 다시 확인해야 합니다."),
    ("pet_restaurant", 2): ("조건부", "문장은 부드러워졌지만 자동 PASS만으로 교육자료 확정을 의미하지 않습니다."),
    ("pet_restaurant", 3): ("조건부", "‘식당이 늘어난다’는 전망이 원문 직접 사실인지 확인이 필요합니다."),
    ("pet_restaurant", 4): ("채택 가능", "적용 범위, 운영 조건, 시설 제한, 점검 순서가 자연스럽습니다."),
    ("pet_restaurant", 5): ("추가 교정", "v7은 ‘출입 제한’을 ‘출입 금지’로 강화하고 점검 대상을 넓게 표현했습니다."),
    ("pet_restaurant", 6): ("추가 교정", "‘모든 음식이 아닌’ 오기와 배경 문단의 후반 배치가 남았습니다."),
    ("energy_saving", 1): ("추가 교정", "장면 흐름은 좋아졌지만 목표 급수보다 높은 핵심 어휘가 남았습니다."),
    ("energy_saving", 2): ("추가 교정", "반복 결말과 일부 급수 초과 어휘를 더 줄여야 합니다."),
    ("energy_saving", 3): ("채택 가능", "제도명 왜곡 없이 기업 목표, 실천, 정부 지원으로 이어집니다."),
    ("energy_saving", 4): ("채택 가능", "참여 주체와 대표기업의 감축 목표가 구분되어 있습니다."),
    ("energy_saving", 5): ("채택 가능", "50여 개 참여 주체와 계획 제출 50개사를 별개의 사실로 표현했습니다."),
    ("energy_saving", 6): ("추가 교정", "원문에 직접 없는 ‘기후변화 대응’ 목적이 추가됐습니다."),
}


def esc(value) -> str:
    return html.escape(str(value or ""))


def status_badge(status: str) -> str:
    css = "pass" if status == "PASS" else "review"
    return f'<span class="badge {css}">{esc(status)}</span>'


def questions_html(items: list[dict], checks: list[dict]) -> str:
    parts = []
    for index, item in enumerate(items, 1):
        check = checks[index - 1] if index - 1 < len(checks) else {}
        choices = "".join(
            f'<li class="{"answer" if choice == item.get("answer") else ""}">{esc(choice)}</li>'
            for choice in item.get("choices", [])
        )
        failed = ", ".join(check.get("failed_ids", [])) or "없음"
        parts.append(f"""
        <article class="question">
          <div class="question-head"><strong>{index}. {esc(item.get('question'))}</strong>{status_badge('PASS' if check.get('passed') else 'NEEDS_HUMAN_REVIEW')}</div>
          <div class="type">유형: {esc(item.get('question_type'))}</div>
          <ol>{choices}</ol>
          <p><b>정답:</b> {esc(item.get('answer'))}</p>
          <p><b>해설:</b> {esc(item.get('explanation'))}</p>
          <p class="minor"><b>형식 실패 기준:</b> {esc(failed)}</p>
        </article>""")
    return "".join(parts) or '<p class="minor">저장된 문항이 없습니다.</p>'


def rounds_html(rounds: list[dict]) -> str:
    blocks = []
    for item in rounds:
        ai = item.get("ai_validation", {})
        ontology = item.get("ontology_validation", {})
        blocks.append(f"""
        <div class="round">
          <h4>라운드 {esc(item.get('round'))} {status_badge('PASS' if item.get('passed') else 'NEEDS_HUMAN_REVIEW')}</h4>
          <p>{esc(item.get('passage'))}</p>
          <p class="minor">AI 실패: {esc(', '.join(ai.get('failed_ids', [])) or '없음')} · 온톨로지 실패: {esc(', '.join(ontology.get('failed_ids', [])) or '없음')}</p>
        </div>""")
    return "".join(blocks) or '<p class="minor">라운드 이력이 없습니다.</p>'


def card(source: str, grade: int, result: dict, experiment: str) -> str:
    review_label, review_note = DIRECT_REVIEW[(source, grade)]
    direct_css = "pass" if review_label == "채택 가능" else "review"
    ontology = result.get("final_ontology_validation", result.get("ontology_validation", {}))
    return f"""
    <section class="result-card" data-source="{source}" data-grade="{grade}">
      <div class="card-head">
        <div><div class="eyebrow">{esc(SOURCES[source])} · {grade}급</div><h2>{esc(result.get('text_type', '읽기 지문'))}</h2></div>
        <div class="badges">{status_badge(result.get('status', 'NEEDS_HUMAN_REVIEW'))}<span class="badge {direct_css}">직접 판정: {esc(review_label)}</span></div>
      </div>
      <div class="meta">출처 실험: {esc(experiment)} · 생성 라운드: {esc(result.get('rounds_used'))}회 · 지문: {esc(result.get('passage_status'))} · 문항: {esc(result.get('question_status'))} · 온톨로지: {esc('PASS' if ontology.get('passed') else '진단 기록')}</div>
      <div class="review-note"><b>직접 검토:</b> {esc(review_note)}</div>
      <h3>최종 지문</h3><div class="passage">{esc(result.get('generated_passage'))}</div>
      <h3>읽기 문항</h3>{questions_html(result.get('reading_items', []), result.get('question_checks', []))}
      <details><summary>생성·수정 라운드 전체 보기</summary>{rounds_html(result.get('rounds', []))}</details>
      <details><summary>최종 AI·온톨로지 판정 보기</summary><pre>{esc(json.dumps({'ai_validation': result.get('final_ai_validation', {}), 'ontology_validation': ontology}, ensure_ascii=False, indent=2))}</pre></details>
    </section>"""


def main() -> None:
    records = []
    cards = []
    for source in SOURCES:
        for grade in range(1, 7):
            result, experiment = selected_result(source, grade)
            records.append(result)
            cards.append(card(source, grade, result, experiment))
    passage_pass = sum(x.get("passage_status") == "PASS" for x in records)
    question_pass = sum(x.get("question_status") == "PASS" for x in records)
    overall_pass = sum(x.get("status") == "PASS" for x in records)
    content = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>1~6급 전체 최신 실험 결과</title>
<style>
:root{{--ink:#172033;--muted:#66758a;--line:#dce4ed;--bg:#f3f6fa;--blue:#275ac7;--green:#087552;--amber:#9a5a00}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Pretendard,"Noto Sans KR","Malgun Gothic",sans-serif;line-height:1.65}}main{{max-width:1180px;margin:32px auto;padding:0 18px}}header,.panel,.result-card{{background:#fff;border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 26px #18304b0d}}header{{padding:34px;color:#fff;background:linear-gradient(135deg,#18386f,#376fd4)}}h1{{margin:0;font-size:36px}}h2{{margin:2px 0 0}}h3{{margin:24px 0 10px}}.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:22px}}.metric{{padding:14px;background:#ffffff17;border:1px solid #ffffff38;border-radius:12px}}.metric b{{display:block;font-size:23px}}.panel{{padding:22px 26px;margin:18px 0}}.filters{{display:flex;gap:10px;flex-wrap:wrap}}button{{border:1px solid #b8c7dc;background:#fff;border-radius:999px;padding:8px 14px;cursor:pointer}}button.active{{background:var(--blue);color:#fff;border-color:var(--blue)}}.result-card{{padding:26px 30px;margin:18px 0}}.card-head,.question-head{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}}.badges{{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}}.badge{{display:inline-block;padding:3px 9px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}}.badge.pass{{background:#e6f7ef;color:var(--green)}}.badge.review{{background:#fff0d7;color:var(--amber)}}.eyebrow,.meta,.minor,.type{{color:var(--muted);font-size:13px}}.review-note{{margin:16px 0;padding:12px 14px;border-left:4px solid #efad3c;background:#fffaf0}}.passage{{white-space:pre-wrap;padding:18px;background:#f7f9fc;border-radius:12px}}.question{{border:1px solid var(--line);border-radius:12px;padding:16px;margin:10px 0}}li.answer{{font-weight:700;color:var(--green)}}details{{margin-top:12px;border-top:1px solid var(--line);padding-top:12px}}summary{{cursor:pointer;font-weight:700}}.round{{padding:12px 0;border-bottom:1px dashed var(--line)}}pre{{white-space:pre-wrap;overflow:auto;background:#121a28;color:#dce7f7;padding:14px;border-radius:10px;font-size:12px}}.hidden{{display:none}}@media(max-width:760px){{h1{{font-size:28px}}.summary{{grid-template-columns:1fr 1fr}}.card-head,.question-head{{display:block}}.badges{{justify-content:flex-start;margin-top:8px}}.result-card{{padding:21px}}}}
</style></head><body><main><header><h1>1~6급 전체 최신 실험 결과</h1><p>반려동물 동반 음식점과 에너지 절약 원자료 · 최종 지문 12개 · 읽기 문항 24개 · 생성 라운드와 진단 근거 포함</p><div class="summary"><div class="metric"><b>12개</b>최종 지문</div><div class="metric"><b>24개</b>읽기 문항</div><div class="metric"><b>{passage_pass}/12</b>지문 자동 PASS</div><div class="metric"><b>{overall_pass}/12</b>종합 자동 PASS</div></div></header>
<section class="panel"><h2>통합 기준</h2><p>1·2급은 v5, 3·4급은 v6와 문항 정규화 후속 결과, 5·6급은 v7을 사용했습니다. 문항 자동 PASS는 {question_pass}/12세트입니다. 자동 PASS는 교육자료 확정을 뜻하지 않으므로 각 급수에 직접 검토 판정을 별도로 표시했습니다.</p><div class="filters"><button class="active" data-filter="all">전체</button><button data-filter="pet_restaurant">반려동물</button><button data-filter="energy_saving">에너지</button>{''.join(f'<button data-grade="{g}">{g}급</button>' for g in range(1,7))}</div></section>{''.join(cards)}
<section class="panel"><h2>한계와 다음 확인</h2><ul><li>1·2급은 최신 코드 재적용 결과가 별도 직접 검토에 있었지만, 지문·문항·라운드가 함께 저장된 가장 최신 전체 실험 v5를 사용했습니다.</li><li>5·6급 v7은 자동 PASS여도 원문에 없는 목적 추가, 제한 강도 변화, 오기 사례가 있어 직접 판정에서 제외했습니다.</li><li>온톨로지는 생성문 수정에 개입하지 않고 사후 진단만 기록합니다.</li></ul></section></main>
<script>const cards=[...document.querySelectorAll('.result-card')],buttons=[...document.querySelectorAll('button')];let source='all',grade=null;function apply(){{cards.forEach(c=>c.classList.toggle('hidden',!(source==='all'||c.dataset.source===source)||!(grade===null||c.dataset.grade===grade)))}}buttons.forEach(b=>b.onclick=()=>{{if(b.dataset.filter){{source=b.dataset.filter;buttons.filter(x=>x.dataset.filter).forEach(x=>x.classList.toggle('active',x===b))}}else{{grade=grade===b.dataset.grade?null:b.dataset.grade;buttons.filter(x=>x.dataset.grade).forEach(x=>x.classList.toggle('active',x.dataset.grade===grade))}}apply()}});</script></body></html>"""
    OUTPUT.write_text(content, encoding="utf-8")
    print(OUTPUT)
    print(json.dumps({"records": len(records), "questions": sum(len(x.get('reading_items', [])) for x in records), "passage_pass": passage_pass, "question_pass": question_pass, "overall_pass": overall_pass}, ensure_ascii=False))


if __name__ == "__main__":
    main()
