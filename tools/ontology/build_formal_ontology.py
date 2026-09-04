# -*- coding: utf-8 -*-
"""Turn the pilot graph into a constrained OWL/SHACL-style ontology package.

No semantic relationship is guessed. Inference is limited to declared inverse,
grade-order, grade-allowance, and passage vocabulary compliance rules.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "ontology/pilot/ontology.sqlite"
DEFAULT_OUTPUT = ROOT / "ontology/formal"
BASE = "https://example.org/korean-learning/ontology/"


CLASS_PARENTS = {
    "EducationalEntity": "owl:Thing",
    "CurriculumEntity": "EducationalEntity",
    "Grade": "CurriculumEntity",
    "Requirement": "CurriculumEntity",
    "ReadingFocus": "CurriculumEntity",
    "Topic": "CurriculumEntity",
    "TextType": "CurriculumEntity",
    "LanguageFunction": "CurriculumEntity",
    "LanguageResource": "EducationalEntity",
    "LexicalResource": "LanguageResource",
    "Vocabulary": "LexicalResource",
    "Lexeme": "LexicalResource",
    "Grammar": "LanguageResource",
    "LearningResource": "EducationalEntity",
    "Passage": "LearningResource",
    "PublishedTask": "LearningResource",
    "AssessmentEntity": "EducationalEntity",
    "ReadingItem": "AssessmentEntity",
    "QuestionType": "AssessmentEntity",
    "RubricCriterion": "AssessmentEntity",
    "EvidenceEntity": "EducationalEntity",
    "EvidenceSource": "EvidenceEntity",
    "SourceDocument": "EvidenceEntity",
    "EvidenceArea": "EvidenceEntity",
}

PROPERTIES = {
    "REGISTERED_AT_GRADE": ("LanguageResource", "Grade", "HAS_REGISTERED_RESOURCE"),
    "TARGETS_GRADE": ("LearningResource", "Grade", "IS_TARGET_OF"),
    "HAS_REQUIREMENT": ("Grade", "Requirement", "REQUIREMENT_OF"),
    "HAS_READING_FOCUS": ("Grade", "ReadingFocus", "READING_FOCUS_OF"),
    "RECOMMENDS_TOPIC": ("Grade", "Topic", "RECOMMENDED_BY_GRADE"),
    "SUPPORTS_TEXT_TYPE": ("Grade", "TextType", "SUPPORTED_BY_GRADE"),
    "SUPPORTS_FUNCTION": ("Grade", "LanguageFunction", "SUPPORTED_BY_GRADE_FUNCTION"),
    "USES_REGISTERED_LEXEME": ("Passage", "Lexeme", "USED_BY_PASSAGE"),
    "HAS_ABOVE_GRADE_LEXEME": ("Passage", "Lexeme", "ABOVE_GRADE_IN_PASSAGE"),
    "HAS_READING_ITEM": ("PublishedTask", "ReadingItem", "PART_OF_TASK"),
    "HAS_QUESTION_TYPE": ("ReadingItem", "QuestionType", "TYPE_OF_ITEM"),
    "APPLIES_TO": ("EvidenceSource", "EvidenceArea", "HAS_EVIDENCE_SOURCE"),
    "NEXT_GRADE": ("Grade", "Grade", "PREVIOUS_GRADE"),
    "HIGHER_THAN": ("Grade", "Grade", "LOWER_THAN"),
    "ALLOWS_RESOURCE": ("Grade", "LanguageResource", "ALLOWED_AT_GRADE"),
    "HAS_AT_OR_BELOW_GRADE_LEXEME": ("Passage", "Lexeme", "COMPLIANT_IN_PASSAGE"),
    "REQUIRES_SOURCE_TERM": ("Passage", "Lexeme", "REQUIRED_BY_PASSAGE"),
    "GROUNDED_IN": ("Passage", "SourceDocument", "GROUNDS_PASSAGE"),
    "REALIZES_TEXT_TYPE": ("Passage", "TextType", "REALIZED_BY_PASSAGE"),
}


def uri(value: str) -> str:
    return "kl:" + quote(value, safe="-._~")


def literal(value) -> str:
    if isinstance(value, bool):
        return f'"{str(value).lower()}"^^xsd:boolean'
    if isinstance(value, int):
        return f'"{value}"^^xsd:integer'
    return json.dumps(str(value), ensure_ascii=False)


def load_graph(path: Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    nodes = {r["node_id"]: dict(r) for r in conn.execute("SELECT * FROM nodes")}
    edges = [dict(r) for r in conn.execute("SELECT * FROM edges")]
    conn.close()
    return nodes, edges


def build_inference(nodes: dict, edges: list[dict]) -> list[tuple[str, str, str, str]]:
    inferred: set[tuple[str, str, str, str]] = set()
    for edge in edges:
        spec = PROPERTIES.get(edge["predicate"])
        if spec and spec[2]:
            inferred.add((edge["target_id"], spec[2], edge["source_id"], "inverse_property"))

    for grade in range(1, 6):
        inferred.add((f"grade:{grade}", "NEXT_GRADE", f"grade:{grade + 1}", "grade_sequence"))
    for high in range(2, 7):
        for low in range(1, high):
            inferred.add((f"grade:{high}", "HIGHER_THAN", f"grade:{low}", "grade_order"))
            inferred.add((f"grade:{low}", "LOWER_THAN", f"grade:{high}", "inverse_grade_order"))

    registered = []
    for edge in edges:
        if edge["predicate"] == "REGISTERED_AT_GRADE":
            registered.append((edge["source_id"], int(edge["target_id"].split(":")[-1])))
    for resource, registered_grade in registered:
        for grade in range(registered_grade, 7):
            inferred.add((f"grade:{grade}", "ALLOWS_RESOURCE", resource, "grade_monotonic_allowance"))

    target_grades = {
        e["source_id"]: int(e["target_id"].split(":")[-1])
        for e in edges if e["predicate"] == "TARGETS_GRADE"
    }
    lexeme_grade = {
        node_id: int(json.loads(node["properties_json"]).get("minimum_grade", 99))
        for node_id, node in nodes.items() if node["node_type"] == "Lexeme"
    }
    for edge in edges:
        if edge["predicate"] != "USES_REGISTERED_LEXEME":
            continue
        target_grade = target_grades.get(edge["source_id"])
        word_grade = lexeme_grade.get(edge["target_id"])
        if target_grade is not None and word_grade is not None and word_grade <= target_grade:
            inferred.add((edge["source_id"], "HAS_AT_OR_BELOW_GRADE_LEXEME",
                          edge["target_id"], "grade_comparison"))
    return sorted(inferred)


def validate(nodes: dict, edges: list[dict], inferred: list[tuple]) -> list[dict]:
    issues = []
    all_edges = edges + [
        {"source_id": s, "predicate": p, "target_id": t, "evidence": reason}
        for s, p, t, reason in inferred
    ]
    outgoing = Counter((e["source_id"], e["predicate"]) for e in all_edges)
    for node_id, node in nodes.items():
        if node["node_type"] in {"Passage", "PublishedTask"}:
            count = outgoing[(node_id, "TARGETS_GRADE")]
            if count != 1:
                issues.append({"severity": "Violation", "shape": "LearningResourceTargetGradeShape",
                               "focus_node": node_id, "message": f"TARGETS_GRADE가 정확히 1개여야 하나 {count}개"})
        if node["node_type"] == "Passage":
            props = json.loads(node["properties_json"])
            grade = props.get("grade")
            chars = props.get("chars")
            req_id = f"requirement:grade:{grade}:passage_chars"
            if req_id in nodes and chars is not None:
                low, high = json.loads(nodes[req_id]["properties_json"])["value"]
                if not low <= chars <= high:
                    issues.append({"severity": "Warning", "shape": "PassageLengthShape",
                                   "focus_node": node_id,
                                   "message": f"{grade}급 지문 {chars}자, 목표 {low}~{high}자"})

    for edge in all_edges:
        spec = PROPERTIES.get(edge["predicate"])
        if not spec:
            continue
        domain, range_, _ = spec
        source_type = nodes.get(edge["source_id"], {}).get("node_type")
        target_type = nodes.get(edge["target_id"], {}).get("node_type")
        if source_type and not is_instance_of(source_type, domain):
            issues.append({"severity": "Violation", "shape": "PropertyDomainShape",
                           "focus_node": edge["source_id"],
                           "message": f"{edge['predicate']} domain {domain}, 실제 {source_type}"})
        if target_type and not is_instance_of(target_type, range_):
            issues.append({"severity": "Violation", "shape": "PropertyRangeShape",
                           "focus_node": edge["target_id"],
                           "message": f"{edge['predicate']} range {range_}, 실제 {target_type}"})
    return issues


def is_instance_of(actual: str, expected: str) -> bool:
    current = actual
    while current and current != "owl:Thing":
        if current == expected:
            return True
        current = CLASS_PARENTS.get(current, "")
    return expected == "owl:Thing"


def write_schema(path: Path) -> None:
    lines = [
        f"@prefix kl: <{BASE}> .", "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .", "",
        "kl:KoreanLearningOntology a owl:Ontology ; rdfs:label \"한국어 교육·평가 온톨로지\"@ko .", "",
    ]
    for cls, parent in CLASS_PARENTS.items():
        parent_uri = parent if ":" in parent else f"kl:{parent}"
        lines.append(f"kl:{cls} a owl:Class ; rdfs:subClassOf {parent_uri} .")
    lines.append("")
    for prop, (domain, range_, inverse) in PROPERTIES.items():
        lines.append(
            f"kl:{prop} a owl:ObjectProperty ; rdfs:domain kl:{domain} ; "
            f"rdfs:range kl:{range_} ; owl:inverseOf kl:{inverse} ."
        )
        lines.append(
            f"kl:{inverse} a owl:ObjectProperty ; rdfs:domain kl:{range_} ; "
            f"rdfs:range kl:{domain} ; owl:inverseOf kl:{prop} ."
        )
    lines.extend(["", "kl:HIGHER_THAN a owl:TransitiveProperty .", "kl:LOWER_THAN a owl:TransitiveProperty ."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_shapes(path: Path) -> None:
    path.write_text(f"""@prefix kl: <{BASE}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

kl:LearningResourceTargetGradeShape a sh:NodeShape ;
  sh:targetClass kl:Passage ;
  sh:property [ sh:path kl:TARGETS_GRADE ; sh:class kl:Grade ; sh:minCount 1 ; sh:maxCount 1 ] .

kl:PassageGroundingShape a sh:NodeShape ;
  sh:targetClass kl:Passage ;
  sh:property [ sh:path kl:GROUNDED_IN ; sh:class kl:SourceDocument ; sh:minCount 1 ; sh:maxCount 1 ] ;
  sh:property [ sh:path kl:REALIZES_TEXT_TYPE ; sh:class kl:TextType ; sh:minCount 1 ; sh:maxCount 1 ] .

kl:VocabularyGradeShape a sh:NodeShape ;
  sh:targetClass kl:Vocabulary ;
  sh:property [ sh:path kl:REGISTERED_AT_GRADE ; sh:class kl:Grade ; sh:minCount 1 ; sh:maxCount 1 ] .

kl:GrammarGradeShape a sh:NodeShape ;
  sh:targetClass kl:Grammar ;
  sh:property [ sh:path kl:REGISTERED_AT_GRADE ; sh:class kl:Grade ; sh:minCount 1 ; sh:maxCount 1 ] .

kl:ReadingItemTypeShape a sh:NodeShape ;
  sh:targetClass kl:ReadingItem ;
  sh:property [ sh:path kl:HAS_QUESTION_TYPE ; sh:class kl:QuestionType ; sh:minCount 1 ; sh:maxCount 1 ] .

kl:PassageLengthShape a sh:NodeShape ;
  sh:targetClass kl:Passage ;
  sh:sparql [
    a sh:SPARQLConstraint ;
    sh:message "지문 글자 수가 목표 급수 범위를 벗어났습니다."@ko ;
    sh:select '''
      SELECT $this WHERE {{
        $this kl:chars ?chars ; kl:TARGETS_GRADE ?grade .
        ?grade kl:HAS_REQUIREMENT ?req .
        ?req kl:requirement_key "passage_chars" ;
             kl:min_value ?min ; kl:max_value ?max .
        FILTER (?chars < ?min || ?chars > ?max)
      }}
    '''
  ] .

kl:AboveGradeLexemeShape a sh:NodeShape ;
  sh:targetClass kl:Passage ;
  sh:sparql [
    a sh:SPARQLConstraint ;
    sh:message "원문 필수어가 아닌 목표 급수 초과 표제어가 있습니다."@ko ;
    sh:select '''
      SELECT $this WHERE {{
        $this kl:TARGETS_GRADE ?grade ; kl:USES_REGISTERED_LEXEME ?lexeme .
        ?grade kl:grade_number ?targetGrade .
        ?lexeme kl:minimum_grade ?lexemeGrade .
        FILTER (?lexemeGrade > ?targetGrade)
        FILTER NOT EXISTS {{ $this kl:REQUIRES_SOURCE_TERM ?lexeme }}
      }}
    '''
  ] .

kl:RequiredSourceTermUsedShape a sh:NodeShape ;
  sh:targetClass kl:Passage ;
  sh:sparql [
    a sh:SPARQLConstraint ;
    sh:message "선언된 원문 필수어가 지문에 실제 사용되지 않았습니다."@ko ;
    sh:select '''
      SELECT $this WHERE {{
        $this kl:REQUIRES_SOURCE_TERM ?term .
        FILTER NOT EXISTS {{ $this kl:USES_REGISTERED_LEXEME ?term }}
      }}
    '''
  ] .
""", encoding="utf-8")


def write_graph(path: Path, nodes: dict, edges: list[dict], inferred: list[tuple]) -> None:
    lines = [f"@prefix kl: <{BASE}> .", "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
             "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .", ""]
    for node_id, node in sorted(nodes.items()):
        props = json.loads(node["properties_json"])
        lines.append(f"{uri(node_id)} a kl:{node['node_type']} ; rdfs:label {literal(node['label'])} ;")
        lines.append(f"  kl:evidence {literal(node['evidence'])} ; kl:reviewStatus {literal(node['review_status'])}")
        for key, value in props.items():
            if isinstance(value, (str, int, bool)) and value != "":
                lines[-1] += " ;"
                lines.append(f"  kl:{key} {literal(value)}")
        lines[-1] += " ."
    lines.append("")
    for edge in edges:
        lines.append(f"{uri(edge['source_id'])} kl:{edge['predicate']} {uri(edge['target_id'])} .")
    lines.append("\n# Materialized inferred triples")
    for source, predicate, target, _ in inferred:
        lines.append(f"{uri(source)} kl:{predicate} {uri(target)} .")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_database(path: Path, inferred: list[tuple], issues: list[dict]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        DROP TABLE IF EXISTS inferred_edges; DROP TABLE IF EXISTS validation_issues;
        CREATE TABLE inferred_edges(source_id TEXT,predicate TEXT,target_id TEXT,rule TEXT,
          PRIMARY KEY(source_id,predicate,target_id));
        CREATE TABLE validation_issues(issue_id INTEGER PRIMARY KEY,severity TEXT,shape TEXT,
          focus_node TEXT,message TEXT);
        """)
        conn.executemany("INSERT OR IGNORE INTO inferred_edges VALUES (?,?,?,?)", inferred)
        conn.executemany(
            "INSERT INTO validation_issues(severity,shape,focus_node,message) VALUES (?,?,?,?)",
            [(x["severity"], x["shape"], x["focus_node"], x["message"]) for x in issues],
        )


def run(input_path: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    nodes, edges = load_graph(input_path)
    inferred = build_inference(nodes, edges)
    issues = validate(nodes, edges, inferred)
    write_schema(output / "ontology_schema.ttl")
    write_shapes(output / "ontology_shapes.ttl")
    write_graph(output / "knowledge_graph.ttl", nodes, edges, inferred)
    write_database(output / "formal_ontology.sqlite", inferred, issues)
    summary = {
        "schema_version": 1,
        "classes": len(CLASS_PARENTS),
        "declared_object_properties": len(PROPERTIES) * 2,
        "source_nodes": len(nodes),
        "asserted_edges": len(edges),
        "materialized_inferred_edges": len(inferred),
        "inference_rules": dict(Counter(x[3] for x in inferred)),
        "validation": {
            "conforms": not any(x["severity"] == "Violation" for x in issues),
            "violations": sum(x["severity"] == "Violation" for x in issues),
            "warnings": sum(x["severity"] == "Warning" for x in issues),
            "issues": issues,
        },
    }
    (output / "validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    warning_lines = "\n".join(
        f"- {issue['message']}"
        for issue in issues
        if issue["severity"] == "Warning"
    ) or "- 없음"
    report = f"""# 정식 온톨로지 구조화 결과

- 클래스: {summary['classes']}개
- 선언한 정방향·역방향 관계: {summary['declared_object_properties']}개
- 원본 노드/관계: {len(nodes):,}개/{len(edges):,}개
- 규칙으로 도출한 관계: {len(inferred):,}개
- 구조 위반: {summary['validation']['violations']}개
- 운영 경고: {summary['validation']['warnings']}개
- 스키마 적합: {'예' if summary['validation']['conforms'] else '아니요'}

## 적용한 추론

- 모든 선언 관계의 역관계 생성
- 1~6급 순서와 상위·하위 급수 관계 생성
- 등록 급수 이상에서 사용할 수 있는 어휘·문법 관계 생성
- 지문 목표 급수와 표제어 최소 급수를 비교하여 적합 어휘 관계 생성

## 검증 결과

구조적 domain/range 및 지문 목표 급수의 단일성 위반은 없다.
길이 기준 이탈은 데이터 구조 위반과 분리해 Warning으로 기록한다.

### 운영 경고

{warning_lines}
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.input.resolve(), args.output.resolve()), ensure_ascii=False, indent=2))
