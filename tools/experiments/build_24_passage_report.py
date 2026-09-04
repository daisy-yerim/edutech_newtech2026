"""Build a readable, self-contained HTML report for the 24-passage matrix."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "experiments/two_source_24_passages_current",
    )
    args = parser.parse_args()
    base = args.base.resolve()
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    records = []
    for item in manifest["records"]:
        result = json.loads((base / item["result_file"]).read_text(encoding="utf-8"))
        records.append((item, result))

    pass_count = sum(r["status"] == "PASS" for _, r in records)
    total_rounds = sum(len(r["rounds"]) for _, r in records)
    failed_summaries = []
    for item, result in records:
        if result["status"] == "PASS":
            continue
        audit = result["final_vocabulary_audit"]
        words = [x["word"] for x in audit.get("violations", [])]
        words += [x["word"] for x in audit.get("blocked_unknown_tokens", [])]
        failed_summaries.append(
            f"{item['source_key']} {item['grade']}급 {item['text_type']}: "
            f"{', '.join(result['final_validation'].get('failed_ids', [])) or '검토 필요'}"
            + (f" / 어휘 {', '.join(words)}" if words else "")
        )
    source_names = {
        "pet_restaurant": "반려동물 동반 음식점 보도자료",
        "energy_saving": "민간 기업 에너지절약 보도자료",
    }
    rows = []
    details = []
    for item, result in records:
        audit = result["final_vocabulary_audit"]
        failed = result["final_validation"].get("failed_ids", [])
        cls = "pass" if result["status"] == "PASS" else "review"
        rows.append(
            "<tr>"
            f"<td>{esc(source_names[item['source_key']])}</td><td>{item['grade']}급</td>"
            f"<td>{esc(item['text_type'])}</td><td><span class='badge {cls}'>{esc(result['status'])}</span></td>"
            f"<td>{len(result['rounds'])}</td><td>{audit.get('violation_count', 0)}</td>"
            f"<td>{audit.get('blocked_unknown_token_count', 0)}</td><td>{esc(', '.join(failed) or '없음')}</td>"
            "</tr>"
        )
        rounds = []
        for rd in result["rounds"]:
            failures = [x for x in rd["language_validation"].get("items", []) if x.get("passed") is False]
            rounds.append(
                f"<details><summary>{rd['round']}회차 — {'PASS' if rd['passed'] else 'FAIL'}</summary>"
                f"<pre>{esc(rd['passage'])}</pre>"
                f"<p>실패: {esc(' / '.join(x.get('criterion_id','') for x in failures) or '없음')}</p></details>"
            )
        details.append(
            f"<article><header><h3>{item['grade']}급 · {esc(item['text_type'])}</h3>"
            f"<span class='badge {cls}'>{esc(result['status'])}</span></header>"
            f"<p class='muted'>{esc(source_names[item['source_key']])} · {len(result['rounds'])}회차"
            + (f" · 필수 핵심어: {esc(result.get('required_keyword'))}" if result.get("required_keyword") else "")
            + "</p>"
            f"<pre class='final'>{esc(result['final_passage'])}</pre>"
            f"<p><b>초과어:</b> {esc(', '.join(x['word'] for x in audit.get('violations', [])) or '없음')}<br>"
            f"<b>차단 미등록어:</b> {esc(', '.join(x['word'] for x in audit.get('blocked_unknown_tokens', [])) or '없음')}<br>"
            f"<b>최종 실패:</b> {esc(', '.join(failed) or '없음')}</p>{''.join(rounds)}</article>"
        )

    doc = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>24개 지문 급수·유형 실험</title><style>
:root{{--bg:#f3f6fb;--card:#fff;--ink:#172033;--muted:#667085;--line:#dbe2ec;--blue:#2457d6;--green:#087a55;--red:#b42318}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:'Malgun Gothic',sans-serif;line-height:1.6}}main{{max-width:1280px;margin:auto;padding:32px 18px 80px}}
.hero,.panel,article{{background:var(--card);border:1px solid var(--line);border-radius:15px;box-shadow:0 8px 24px #1720330b}}.hero,.panel,article{{padding:22px;margin:16px 0}}h1{{margin:0}}.muted{{color:var(--muted)}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}}.stat{{border:1px solid var(--line);border-radius:10px;padding:12px}}.stat b{{display:block;font-size:24px;color:var(--blue)}}
table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}.badge{{padding:3px 8px;border-radius:999px;font-size:12px;font-weight:700}}.pass{{background:#e8f7f0;color:var(--green)}}.review{{background:#fff0ed;color:var(--red)}}
article header{{display:flex;justify-content:space-between;align-items:center}}pre{{white-space:pre-wrap;font-family:inherit;background:#f7f9fc;border-left:4px solid #a6b6d8;padding:14px;border-radius:8px}}pre.final{{border-left-color:var(--blue)}}details{{border:1px solid var(--line);border-radius:8px;padding:10px;margin-top:8px}}summary{{cursor:pointer;font-weight:700}}
@media(max-width:800px){{.stats{{grid-template-columns:1fr 1fr}}.panel{{overflow:auto}}table{{font-size:12px}}}}
</style></head><body><main>
<section class='hero'><p class='muted'>2026-08-03 · 로컬 gemma4:12b · 생성→검증→수정 루프</p><h1>두 원문 × 6개 급수 × 대표 유형 2개</h1>
<p>SKA의 급수별 텍스트 유형 목록에서 실험용 대표 유형 두 개를 선정해 총 24개 지문을 생성했습니다. 유형 배정은 공식 고정 대응표가 아닙니다.</p>
<div class='stats'><div class='stat'><b>2</b>원문</div><div class='stat'><b>{len(records)}/24</b>저장 지문</div><div class='stat'><b>{pass_count}/{len(records)}</b>최종 PASS</div><div class='stat'><b>{total_rounds}</b>총 회차</div></div></section>
<section class='panel'><h2>이번 기준</h2><ul><li>1·2급은 TOPIK I 일상 개작을 우선하고 급수 초과어·미등록 내용어를 실제 탈락 처리</li><li>1급 3~5문장, 2급 4~7문장 필수</li><li>3~6급은 원문 사실을 유지하고 지정 유형의 목적과 조직을 P-VAL-03에서 검증</li><li>길이는 참고값이며 단독 탈락 사유로 사용하지 않음</li><li>모든 최초 생성·수정·검증 회차를 JSON으로 보존</li></ul></section>
<section class='panel'><h2>급수별 대표 유형</h2><table><thead><tr><th>급수</th><th>유형 1</th><th>유형 2</th></tr></thead><tbody>
<tr><td>1급</td><td>개인 문자</td><td>메모</td></tr><tr><td>2급</td><td>짧은 일기</td><td>안내문</td></tr>
<tr><td>3급</td><td>소개글</td><td>짧은 기사</td></tr><tr><td>4급</td><td>기사</td><td>사회적 설명문</td></tr>
<tr><td>5급</td><td>제안서</td><td>보고서</td></tr><tr><td>6급</td><td>전문 자료</td><td>기사문</td></tr>
</tbody></table><p class='muted'>SKA 급수별 text_types 목록에서 이번 실험용으로 두 개씩 선정했으며 공식 고정 대응표는 아닙니다.</p></section>
<section class='panel'><h2>실험 결론</h2><ul>
<li>24개 조합이 중복 없이 모두 생성·저장되었습니다.</li><li>자동 검증 결과는 {pass_count}/24 PASS, {len(records)-pass_count}/24 NEEDS_HUMAN_REVIEW입니다.</li>
<li>1·2급은 원문에서 급수에 맞는 핵심어 하나를 반드시 포함하고, 핵심어의 원문 의미도 유지하도록 수정했습니다.</li>
<li>반려동물 자료: 1급 ‘식당’, 2급 ‘음식점’. 에너지 자료: 1급 ‘불(쓰지 않는 불 끄기)’, 2급 ‘전기(전기 절약)’.</li>
{''.join(f'<li>{esc(x)}</li>' for x in failed_summaries) or '<li>자동 검증 실패 없음</li>'}
<li>자동 PASS는 자연스러움의 전문가 확정을 뜻하지 않습니다. 괄호식 설명, 어색한 결합, 지나친 단순화는 별도 전문가 검토가 필요합니다.</li>
</ul></section>
<section class='panel'><h2>전체 결과표</h2><table><thead><tr><th>원문</th><th>급수</th><th>유형</th><th>상태</th><th>회차</th><th>초과어</th><th>미등록어</th><th>실패 기준</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
<section><h2>24개 최종 지문과 회차 기록</h2>{''.join(details)}</section>
</main></body></html>"""
    output = base / "24_passage_experiment_report.html"
    output.write_text(doc, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
