"""Generate and validate one passage at a time for grades 1 through 6.

Each grade completes its generate -> vocabulary control -> semantic validation
-> repair loop before the next grade starts. Existing experiment outputs are
never overwritten.
"""

from __future__ import annotations

import json
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.teacher.nodes import validate_passage
from app.workflow.nodes.passage_node import passage_node

DEFAULT_SOURCE_META = ROOT / "data" / "sources" / "government" / "pet_restaurant" / "source_facts.json"
DEFAULT_SOURCE_PDF = ROOT / "data" / "sources" / "government" / "pet_restaurant" / "press_release.pdf"
DEFAULT_OUT_ROOT = ROOT / "experiments" / "passage_grade_loop_current"
MAX_ROUNDS = 3
BEGINNER_SOURCE_KEYWORDS = {
    "KOREA-PET-2026": {1: "식당", 2: "음식점"},
    "MOE-ENERGY-SAVING-2026-04-07": {1: "불", 2: "전기"},
}
BEGINNER_KEYWORD_CONTEXTS = {
    "KOREA-PET-2026": {
        1: "사람이 식당에 가서 음식을 먹는 일상 장면",
        2: "사람이 음식점을 이용하는 일상 안내나 경험",
    },
    "MOE-ENERGY-SAVING-2026-04-07": {
        1: "쓰지 않는 방이나 회사의 불을 끄는 장면. 화재가 난다는 뜻으로 쓰면 안 됨",
        2: "회사나 집에서 전기를 덜 쓰고 아끼는 행동. 정전이나 고장 이야기로 바꾸면 안 됨",
    },
}


def source_text(source: dict) -> str:
    return "\n".join(f"{fact['id']}: {fact['text']}" for fact in source["facts"])


def repair_note(validation: dict) -> str:
    notes = []
    for item in validation.get("items", []):
        if item.get("passed") is False:
            notes.append(
                f"- {item.get('criterion_id', '')}: "
                f"{item.get('revision_instruction') or item.get('evidence') or '검증 실패 항목을 수정하세요.'}"
            )
    return "\n".join(notes)


def failed_details(validation: dict) -> list[dict]:
    """Return only failed checks so the result is readable without scanning rounds."""
    return [
        {
            "criterion_id": item.get("criterion_id", ""),
            "evidence": item.get("evidence", ""),
            "revision_instruction": item.get("revision_instruction", ""),
        }
        for item in validation.get("items", [])
        if item.get("passed") is False
    ]


def write_readable_report(output_dir: Path, results: list[dict], title: str) -> None:
    lines = [f"# {title} 지문 생성 실험", ""]
    for result in results:
        display = result["result"]
        lines.extend([
            f"## {result['grade']}급 — {display['status']}",
            "",
            display["generated_passage"],
            "",
            f"- 생성·검증 횟수: {display['rounds_used']}회",
            f"- 실패 항목: {', '.join(display['failed_ids']) or '없음'}",
            f"- 등급 초과 어휘: {', '.join(display['vocabulary_violations']) or '없음'}",
            f"- 차단된 미등록 일반명사: {', '.join(display['blocked_unknown_nouns']) or '없음'}",
            "",
        ])
    (output_dir / "PASSAGES.md").write_text("\n".join(lines), encoding="utf-8")
    compact = [
        {"grade": result["grade"], **result["result"]} for result in results
    ]
    (output_dir / "passages_only.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_checkpoint(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"기존 중간 결과를 덮어쓰지 않습니다: {path}")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_grade(
    grade: int,
    source: dict,
    output_dir: Path,
    source_pdf: Path,
    experiment_name: str,
    text_type: str = "일반 읽기 지문",
) -> dict:
    beginner_free = grade in {1, 2}
    required_keyword = (
        BEGINNER_SOURCE_KEYWORDS.get(source["id"], {}).get(grade, "")
        if beginner_free else ""
    )
    required_keyword_context = (
        BEGINNER_KEYWORD_CONTEXTS.get(source["id"], {}).get(grade, "")
        if beginner_free else ""
    )
    base_state = {
        "grade": grade,
        "topic": "TOPIK I 일상생활" if beginner_free else source["title"],
        "category_id": "social",
        "category_label": "사회",
        "text_type": text_type,
        "required_keyword": required_keyword,
        "required_keyword_context": required_keyword_context,
        "source_mode": "beginner_free_adaptation" if beginner_free else "source_grounded",
        "source_text": (
            f"원자료에서 고른 필수 핵심어: {required_keyword}. "
            f"핵심어의 원문 의미: {required_keyword_context}. "
            "이 핵심어 하나로 TOPIK I의 쉬운 일상 장면을 자유롭게 개작합니다. "
            "원자료의 전문 제도·수치·기관·정책은 따를 필요가 없습니다."
            if beginner_free else source_text(source)
        ),
        "reject_note": "",
        "passage_round": 1,
    }
    rounds = []
    current_state = dict(base_state)

    for round_no in range(1, MAX_ROUNDS + 1):
        print(f"grade {grade}: generation round {round_no}", flush=True)
        generated = passage_node({**current_state, "round_no": round_no})
        candidate = {**current_state, **generated}
        _write_checkpoint(
            output_dir / f"grade_{grade}_round_{round_no}_generation.json",
            {
                "grade": grade,
                "round": round_no,
                "stage": "generation",
                "passage": generated.get("passage", ""),
                "vocabulary_audit": generated.get("vocabulary_audit", {}),
                "vocabulary_revision_history": generated.get(
                    "vocabulary_revision_history", []
                ),
                "naturalness_revision": generated.get("naturalness_revision", {}),
            },
        )

        print(f"grade {grade}: validation round {round_no}", flush=True)
        checked = validate_passage(candidate)
        validation = checked["passage_validation"]
        vocabulary = generated.get("vocabulary_audit", {})
        round_record = {
            "round": round_no,
            "passage": generated.get("passage", ""),
            "vocabulary_audit": vocabulary,
            "vocabulary_revision_history": generated.get("vocabulary_revision_history", []),
            "naturalness_revision": generated.get("naturalness_revision", {}),
            "language_validation": validation,
            "passed": bool(validation.get("passed")),
        }
        rounds.append(round_record)
        _write_checkpoint(
            output_dir / f"grade_{grade}_round_{round_no}_validation.json",
            round_record,
        )

        if validation.get("passed"):
            break

        current_state = {
            **candidate,
            "reject_note": repair_note(validation),
            "passage_round": round_no + 1,
        }

    final = rounds[-1]
    return {
        "schema_version": 2,
        "experiment": experiment_name,
        "grade": grade,
        "text_type": text_type,
        "required_keyword": required_keyword,
        "required_keyword_context": required_keyword_context,
        "result": {
            "generated_passage": final["passage"],
            "status": "PASS" if final["passed"] else "NEEDS_HUMAN_REVIEW",
            "rounds_used": len(rounds),
            "failed_ids": final["language_validation"].get("failed_ids", []),
            "failed_details": failed_details(final["language_validation"]),
            "vocabulary_violations": [
                item["word"] for item in final["vocabulary_audit"].get("violations", [])
            ],
            "blocked_unknown_nouns": [
                item["word"]
                for item in final["vocabulary_audit"].get("blocked_unknown_nouns", [])
            ],
        },
        "model": "gemma4:12b",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "mode": "beginner_free_adaptation" if beginner_free else "source_grounded",
            "id": source["id"],
            "title": source["title"],
            "source_file": str(source_pdf.relative_to(ROOT)).replace("\\", "/"),
            "source_url": source.get("source_url") or source.get("url", ""),
            "license": source.get("license", {}),
            "facts": source["facts"],
        },
        "loop_policy": {
            "sequence": "generate_then_validate_then_repair_before_next_grade",
            "max_rounds": MAX_ROUNDS,
            "criteria": [
                (
                    "TOPIK I everyday free adaptation; source body fidelity not required"
                    if beginner_free else
                    "source fidelity and no unsupported factual claims"
                ),
                "grade vocabulary",
                "TOPIK I adaptation profile for grades 1-2",
                "controlled repetition",
                "sentence well-formedness and semantic flow",
            ],
        },
        "rounds": rounds,
        "final_passage": final["passage"],
        "final_vocabulary_audit": final["vocabulary_audit"],
        "final_validation": final["language_validation"],
        "status": "PASS" if final["passed"] else "NEEDS_HUMAN_REVIEW",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUT_ROOT,
        help="새 실험 결과를 저장할 폴더(기존 결과는 덮어쓰지 않음)",
    )
    parser.add_argument("--source-meta", type=Path, default=DEFAULT_SOURCE_META)
    parser.add_argument("--source-pdf", type=Path, default=DEFAULT_SOURCE_PDF)
    parser.add_argument("--experiment-name", default="passage_grade_loop")
    parser.add_argument(
        "--grades", type=int, nargs="+", default=list(range(1, 7)),
        help="실험할 급수 목록(예: --grades 1 2)",
    )
    args = parser.parse_args()
    output_root = args.output_dir.resolve()
    source_meta = args.source_meta.resolve()
    source_pdf = args.source_pdf.resolve()
    source = json.loads(source_meta.read_text(encoding="utf-8"))
    if not source_pdf.exists():
        raise FileNotFoundError(source_pdf)
    output_root.mkdir(parents=True, exist_ok=True)

    summary = []
    results = []
    grades = list(dict.fromkeys(args.grades))
    if not grades or any(grade not in range(1, 7) for grade in grades):
        raise ValueError("--grades에는 1~6만 지정할 수 있습니다.")
    for grade in grades:
        output_path = output_root / f"grade_{grade}.json"
        if output_path.exists():
            raise FileExistsError(f"기존 결과를 덮어쓰지 않습니다: {output_path}")
        result = run_grade(
            grade, source, output_root, source_pdf, args.experiment_name
        )
        results.append(result)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary.append({
            "grade": grade,
            "status": result["status"],
            "rounds": len(result["rounds"]),
            "passage_chars": len(result["final_passage"]),
            "vocabulary_violations": result["final_vocabulary_audit"].get("violation_count"),
            "unknown_vocabulary": result["final_vocabulary_audit"].get("unknown_token_count"),
            "failed_ids": result["final_validation"].get("failed_ids", []),
        })
        print(f"grade {grade}: saved {result['status']}", flush=True)

    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_readable_report(output_root, results, source["title"])
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
