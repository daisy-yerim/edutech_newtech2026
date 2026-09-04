"""Build a conservative ontology pilot from already-confirmed project data."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from kiwipiepy import Kiwi


ROOT = Path(__file__).resolve().parents[2]
DICTIONARY_DB = ROOT / "data/reference/korean_dictionary.sqlite"
RUNTIME_DB = ROOT / "data/runtime/korean_learning.sqlite3"
CRITERIA = ROOT / "data/criteria"
DEFAULT_PASSAGES = ROOT / "experiments/two_source_six_grades_ontology_loop_2026-08-12_rerun/passages_only.json"
DEFAULT_OUTPUT = ROOT / "ontology/pilot"
LEXICAL_TAGS = {"NNG", "NP", "VV", "VA", "MAG", "MAJ", "MM", "XR"}
AUDIT_EXEMPT = {
    "년", "월", "일", "시", "분", "초", "명", "개", "번", "수", "이", "것", "데", "바",
    "오늘", "내일", "날", "나", "있다", "없다", "이제", "모두", "우리", "매일", "조금", "다", "크다",
}


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8-sig"))


class GraphWriter:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript("""
        DROP TABLE IF EXISTS edges;
        DROP TABLE IF EXISTS nodes;
        CREATE TABLE nodes (
            node_id TEXT PRIMARY KEY,
            node_type TEXT NOT NULL,
            label TEXT NOT NULL,
            properties_json TEXT NOT NULL DEFAULT '{}',
            evidence TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'confirmed_from_source'
        );
        CREATE TABLE edges (
            source_id TEXT NOT NULL REFERENCES nodes(node_id),
            predicate TEXT NOT NULL,
            target_id TEXT NOT NULL REFERENCES nodes(node_id),
            evidence TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'confirmed_from_source',
            PRIMARY KEY (source_id, predicate, target_id)
        );
        CREATE INDEX idx_nodes_type ON nodes(node_type);
        CREATE INDEX idx_edges_predicate ON edges(predicate);
        """)

    def node(self, node_id: str, node_type: str, label: str, evidence: str, **properties):
        self.conn.execute(
            "INSERT OR IGNORE INTO nodes VALUES (?,?,?,?,?,?)",
            (node_id, node_type, label, json.dumps(properties, ensure_ascii=False), evidence,
             "confirmed_from_source"),
        )

    def edge(self, source: str, predicate: str, target: str, evidence: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO edges VALUES (?,?,?,?,?)",
            (source, predicate, target, evidence, "confirmed_from_source"),
        )


def add_grade_nodes(graph: GraphWriter) -> None:
    requirements = read_json(CRITERIA / "standards/grade_requirements.json")
    ska = read_json(CRITERIA / "standards/ska_generation.json")
    for grade in range(1, 7):
        grade_id = f"grade:{grade}"
        graph.node(grade_id, "Grade", f"{grade}급", "grade_requirements.json + ska_generation.json",
                   grade_number=grade)
        req = requirements["grades"][str(grade)]
        for key in ("passage_chars", "paragraphs", "sentence_chars_average_max", "writing_chars"):
            value = req[key]
            target = f"requirement:grade:{grade}:{key}"
            extra = {"requirement_key": key, "value": value}
            if isinstance(value, list) and len(value) == 2:
                extra.update({"min_value": value[0], "max_value": value[1]})
            graph.node(target, "Requirement", f"{grade}급 {key}", "grade_requirements.json", **extra)
            graph.edge(grade_id, "HAS_REQUIREMENT", target, "grade_requirements.json")
        for focus in req["reading_focus"]:
            target = f"reading_focus:{focus}"
            graph.node(target, "ReadingFocus", focus, "grade_requirements.json")
            graph.edge(grade_id, "HAS_READING_FOCUS", target, "grade_requirements.json")
        spec = ska["grades"][str(grade)]["reading"]
        for key, predicate, kind in (
            ("topics", "RECOMMENDS_TOPIC", "Topic"),
            ("text_types", "SUPPORTS_TEXT_TYPE", "TextType"),
            ("functions", "SUPPORTS_FUNCTION", "LanguageFunction"),
        ):
            for label in spec[key]:
                target = f"{kind.lower()}:{label}"
                graph.node(target, kind, label, "ska_generation.json")
                graph.edge(grade_id, predicate, target, "ska_generation.json")


def add_dictionary_nodes(graph: GraphWriter) -> dict[str, int]:
    vocab_min_grade: dict[str, int] = {}
    with sqlite3.connect(DICTIONARY_DB) as conn:
        for word, grade, pos, guide in conn.execute(
            "SELECT word,grade,part_of_speech,guide FROM vocabulary ORDER BY id"
        ):
            node_id = f"vocab:{word}:{grade}:{pos}:{guide}"
            graph.node(node_id, "Vocabulary", word, "korean_dictionary.sqlite/vocabulary",
                       grade=grade, part_of_speech=pos, guide=guide)
            graph.edge(node_id, "REGISTERED_AT_GRADE", f"grade:{grade}",
                       "korean_dictionary.sqlite/vocabulary")
            vocab_min_grade[word] = min(grade, vocab_min_grade.get(word, grade))
        for sequence, grade, category, form, related, meaning in conn.execute(
            "SELECT sequence,grade,category,form,related_forms,meaning FROM grammar ORDER BY id"
        ):
            node_id = f"grammar:{grade}:{sequence}"
            graph.node(node_id, "Grammar", form, "korean_dictionary.sqlite/grammar",
                       grade=grade, sequence=sequence, category=category,
                       related_forms=related, meaning=meaning)
            graph.edge(node_id, "REGISTERED_AT_GRADE", f"grade:{grade}",
                       "korean_dictionary.sqlite/grammar")
    return vocab_min_grade


def add_criteria_nodes(graph: GraphWriter) -> None:
    manifest = read_json(CRITERIA / "reading_question_types/manifest.json")
    for type_id, spec in manifest["types"].items():
        node_id = f"question_type:{type_id}"
        graph.node(node_id, "QuestionType", spec["label"], "reading_question_types/manifest.json",
                   description=spec["description"], construction_rules=spec["construction_rules"])
    for section in ("generation", "validation", "approval"):
        filename = {"generation": "teacher_generation.json", "validation": "ai_validation.json",
                    "approval": "teacher_approval.json"}[section]
        data = read_json(CRITERIA / f"rubrics/{section}/{filename}")
        for scope in ("passage", "assessment"):
            for item in data.get(scope, []):
                node_id = f"rubric:{item['id']}"
                graph.node(node_id, "RubricCriterion", item.get("label", item["id"]),
                           f"rubrics/{section}/{filename}", scope=scope, rubric_type=section,
                           definition=item.get("check", item.get("instruction", "")))
    registry = read_json(CRITERIA / "source_registry.json")
    for source in registry["sources"]:
        node_id = f"source:{source['id']}"
        graph.node(node_id, "EvidenceSource", source["title"], "source_registry.json",
                   authority=source.get("authority", ""), role=source.get("role", ""),
                   applies_to=source.get("applies_to", []))
        for area in source.get("applies_to", []):
            area_id = f"evidence_area:{area}"
            graph.node(area_id, "EvidenceArea", area, "source_registry.json")
            graph.edge(node_id, "APPLIES_TO", area_id, "source_registry.json")


def extract_registered_words(text: str, lexicon: dict[str, int], kiwi: Kiwi) -> tuple[Counter, int, int]:
    words = Counter()
    lexical = 0
    unknown = 0
    for token in kiwi.tokenize(text):
        if token.tag not in LEXICAL_TAGS or token.tag == "NNP":
            continue
        lexical += 1
        lemma = token.form + "다" if token.tag in {"VV", "VA"} else token.form
        if lemma in AUDIT_EXEMPT:
            lexical -= 1
        elif lemma in lexicon:
            words[lemma] += 1
        else:
            unknown += 1
    return words, lexical, unknown


def add_experiment_passages(graph: GraphWriter, path: Path, lexicon: dict[str, int]) -> list[dict]:
    kiwi = Kiwi()
    requirements = read_json(CRITERIA / "standards/grade_requirements.json")["grades"]
    results = []
    for index, row in enumerate(read_json(path), 1):
        grade = int(row["grade"])
        text = row["generated_passage"]
        passage_id = f"pilot_passage:{index}:grade:{grade}"
        words, lexical_count, unknown_count = extract_registered_words(text, lexicon, kiwi)
        graph.node(passage_id, "Passage", f"파일럿 {grade}급 지문", str(path.relative_to(ROOT)),
                   grade=grade, chars=len(text), status=row.get("status", ""),
                   source_key=row.get("source_key", ""))
        if row.get("source_key"):
            source_id = f"experiment_source:{row['source_key']}"
            graph.node(source_id, "SourceDocument", row["source_key"], str(path.relative_to(ROOT)))
            graph.edge(passage_id, "GROUNDED_IN", source_id, "passages_only.json/source_key")
        graph.edge(passage_id, "TARGETS_GRADE", f"grade:{grade}", str(path.relative_to(ROOT)))
        if row.get("text_type"):
            text_type_id = f"texttype:{row['text_type']}"
            graph.node(text_type_id, "TextType", row["text_type"], "passages_only.json/text_type")
            graph.edge(passage_id, "REALIZES_TEXT_TYPE", text_type_id,
                       "passages_only.json/text_type")
        for essential in row.get("essential_lexemes", []):
            essential_id = f"lexeme:{essential}"
            graph.node(essential_id, "Lexeme", essential, "experiment-declared source term",
                       minimum_grade=lexicon.get(essential, 99))
            graph.edge(passage_id, "REQUIRES_SOURCE_TERM", essential_id,
                       "experiment source-term policy")
        above = []
        for word, count in words.items():
            word_id = f"lexeme:{word}"
            graph.node(word_id, "Lexeme", word, "Kiwi lemma + vocabulary minimum grade",
                       minimum_grade=lexicon[word])
            graph.edge(passage_id, "USES_REGISTERED_LEXEME", word_id,
                       f"Kiwi deterministic lemma match; occurrences={count}")
            if lexicon[word] > grade:
                above.append({"word": word, "registered_grade": lexicon[word], "count": count})
                graph.edge(passage_id, "HAS_ABOVE_GRADE_LEXEME", word_id,
                           f"lexeme grade {lexicon[word]} > target grade {grade}")
        length_range = requirements[str(grade)]["passage_chars"]
        results.append({
            "grade": grade, "chars": len(text), "registered_unique_lexemes": len(words),
            "target_char_range": length_range,
            "within_target_char_range": length_range[0] <= len(text) <= length_range[1],
            "lexical_tokens": lexical_count, "unmatched_lexical_tokens": unknown_count,
            "registered_token_coverage": round((lexical_count - unknown_count) / lexical_count, 4)
            if lexical_count else 0,
            "above_grade_lexemes": above,
        })
    return results


def add_published_tasks(graph: GraphWriter) -> dict:
    if not RUNTIME_DB.exists():
        return {"tasks": 0, "items": 0}
    tasks = items = 0
    with sqlite3.connect(RUNTIME_DB) as conn:
        for task_id, grade, topic, category, passage in conn.execute(
            "SELECT task_id,grade,topic,category_id,passage FROM assessments WHERE published=1"
        ):
            node_id = f"task:{task_id}"
            graph.node(node_id, "PublishedTask", task_id, "korean_learning.sqlite3/assessments",
                       topic=topic, category_id=category, chars=len(passage))
            graph.edge(node_id, "TARGETS_GRADE", f"grade:{grade}", "assessments.grade")
            tasks += 1
            for item_id, question_type in conn.execute(
                "SELECT item_id,question_type FROM reading_items WHERE task_id=?", (task_id,)
            ):
                item_node = f"item:{task_id}:{item_id}"
                graph.node(item_node, "ReadingItem", item_id, "korean_learning.sqlite3/reading_items")
                graph.edge(node_id, "HAS_READING_ITEM", item_node, "reading_items.task_id")
                qtype = f"question_type:{question_type}"
                if graph.conn.execute("SELECT 1 FROM nodes WHERE node_id=?", (qtype,)).fetchone():
                    graph.edge(item_node, "HAS_QUESTION_TYPE", qtype, "reading_items.question_type")
                items += 1
    return {"tasks": tasks, "items": items}


def write_report(output: Path, summary: dict) -> None:
    rows = "\n".join(
        f"| {r['grade']}급 | {r['chars']} / {r['target_char_range'][0]}~{r['target_char_range'][1]} | "
        f"{'적합' if r['within_target_char_range'] else '초과/미달'} | {r['registered_unique_lexemes']} | "
        f"{r['registered_token_coverage']:.1%} | {len(r['above_grade_lexemes'])} |"
        for r in summary["passage_results"]
    )
    report = f"""# 확정 데이터 온톨로지 파일럿 결과

## 결과 요약

- 노드: {summary['graph']['nodes']:,}개
- 관계: {summary['graph']['edges']:,}개
- 어휘 노드: {summary['node_types'].get('Vocabulary', 0):,}개
- 문법 노드: {summary['node_types'].get('Grammar', 0):,}개
- 연결한 실험 지문: {len(summary['passage_results'])}개
- 연결한 공개 과제/읽기 문항: {summary['published']['tasks']}개/{summary['published']['items']}개

| 급수 | 실제/목표 글자 수 | 길이 | 등록 고유 표제어 | 등록 토큰 커버리지 | 상위 급수 표제어 |
|---:|---:|---:|---:|---:|---:|
{rows}

## 판정

이 파일럿은 기존 DB와 JSON에 명시된 관계만 그래프로 옮겼다. 급수별 어휘·문법 조회,
지문에서 확인된 등록 표제어와 상위 급수 표제어 추적, 지문–문항–문항 유형 연결,
기준–출처의 적용 영역 조회가 가능하다.

등록 토큰 커버리지는 형태소 분석 결과 중 현재 표제어 DB와 정확히 연결된 비율이다.
미연결 토큰은 곧 오류라는 뜻이 아니며 복합어·파생형·고유명사·분석 차이 검토 대상이다.
문법의 실제 사용, 유의어, 선수 관계, 문장 간 의미 관계는 확정 근거가 부족해 넣지 않았다.

## 산출물

- `ontology.sqlite`: 노드와 관계를 직접 조회하는 실험 그래프
- `summary.json`: 수치와 지문별 진단 결과
- `REPORT.md`: 사람이 읽기 쉬운 결과 요약
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")


def run(output: Path, passages: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    graph = GraphWriter(output / "ontology.sqlite")
    add_grade_nodes(graph)
    lexicon = add_dictionary_nodes(graph)
    add_criteria_nodes(graph)
    passage_results = add_experiment_passages(graph, passages, lexicon)
    published = add_published_tasks(graph)
    graph.conn.commit()
    node_types = dict(graph.conn.execute(
        "SELECT node_type,COUNT(*) FROM nodes GROUP BY node_type ORDER BY node_type"
    ))
    predicates = dict(graph.conn.execute(
        "SELECT predicate,COUNT(*) FROM edges GROUP BY predicate ORDER BY predicate"
    ))
    summary = {
        "schema_version": 1,
        "scope": "confirmed project data only; no semantic relation inference",
        "graph": {
            "nodes": graph.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0],
            "edges": graph.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        },
        "node_types": node_types,
        "predicates": predicates,
        "published": published,
        "passage_results": passage_results,
    }
    graph.conn.close()
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(output, summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--passages", type=Path, default=DEFAULT_PASSAGES)
    args = parser.parse_args()
    result = run(args.output.resolve(), args.passages.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
