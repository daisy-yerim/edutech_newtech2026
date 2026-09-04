"""Run two sources x six grades x two evidence-selected text types."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.experiments.run_passage_grade_loop import run_grade


TYPE_MATRIX = {
    1: ["개인 문자", "메모"],
    2: ["짧은 일기", "안내문"],
    3: ["소개글", "짧은 기사"],
    4: ["기사", "사회적 설명문"],
    5: ["제안서", "보고서"],
    6: ["전문 자료", "기사문"],
}

SOURCES = [
    {
        "key": "pet_restaurant",
        "meta": ROOT / "data/sources/government/pet_restaurant/source_facts.json",
        "pdf": ROOT / "data/sources/government/pet_restaurant/press_release.pdf",
    },
    {
        "key": "energy_saving",
        "meta": ROOT / "data/sources/government/energy_saving/source_facts.json",
        "pdf": ROOT / "data/sources/government/energy_saving/press_release.pdf",
    },
]


def slug(index: int) -> str:
    return f"type_{index}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "experiments/two_source_24_passages_current",
    )
    parser.add_argument("--grades", type=int, nargs="+", default=list(range(1, 7)))
    parser.add_argument("--sources", nargs="+", default=[x["key"] for x in SOURCES])
    args = parser.parse_args()
    base = args.output_dir.resolve()
    base.mkdir(parents=True, exist_ok=True)
    selected_sources = [s for s in SOURCES if s["key"] in args.sources]
    if not selected_sources or any(g not in TYPE_MATRIX for g in args.grades):
        raise ValueError("sources 또는 grades가 올바르지 않습니다.")

    manifest = {
        "schema_version": 1,
        "expected_count": len(selected_sources) * len(args.grades) * 2,
        "type_selection_note": (
            "SKA 급수별 text_types 목록에서 실험용 대표 유형 두 개를 선정했으며 "
            "공식 고정 대응표가 아니다."
        ),
        "type_matrix": TYPE_MATRIX,
        "records": [],
    }
    for source_spec in selected_sources:
        source = json.loads(source_spec["meta"].read_text(encoding="utf-8"))
        for grade in args.grades:
            for type_index, text_type in enumerate(TYPE_MATRIX[grade], 1):
                unit = base / source_spec["key"] / f"grade_{grade}" / slug(type_index)
                unit.mkdir(parents=True, exist_ok=True)
                result_file = unit / "result.json"
                if result_file.exists():
                    result = json.loads(result_file.read_text(encoding="utf-8"))
                    print(f"resume {source_spec['key']} grade {grade} {text_type}", flush=True)
                else:
                    print(f"run {source_spec['key']} grade {grade} {text_type}", flush=True)
                    result = run_grade(
                        grade=grade,
                        source=source,
                        output_dir=unit,
                        source_pdf=source_spec["pdf"],
                        experiment_name="two_source_24_passages_current",
                        text_type=text_type,
                    )
                    result_file.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                manifest["records"].append({
                    "source_key": source_spec["key"],
                    "grade": grade,
                    "type_index": type_index,
                    "text_type": text_type,
                    "status": result["status"],
                    "rounds": len(result["rounds"]),
                    "result_file": str(result_file.relative_to(base)).replace("\\", "/"),
                })
                (base / "manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
                )
    print(base / "manifest.json", flush=True)


if __name__ == "__main__":
    main()
