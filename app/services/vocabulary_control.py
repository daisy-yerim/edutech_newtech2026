"""생성 지문의 등급 초과 어휘 탐지와 교체."""

from __future__ import annotations

import re
import sqlite3
from functools import lru_cache

from kiwipiepy import Kiwi

from app.core.config import DICTIONARY_DB
from app.core.llm import call_gemma, call_gemma_json

HANGUL_TOKEN = re.compile(r"[가-힣]+")
PARTICLES = (
    "으로부터", "에게서", "에서는", "으로는", "까지는", "이라고", "이라는",
    "에게", "에서", "으로", "처럼", "보다", "하고", "이며", "이나", "라도",
    "에는", "에도", "만을", "부터", "까지", "께서", "의", "이", "가", "은", "는",
    "을", "를", "에", "도", "만", "과", "와", "로", "께", "랑",
)
# 날짜·수량 단위와 문법 구성에 쓰이는 의존명사/기능 표현은 어휘 등급이 아니라
# 문법 등급에서 판정한다. 예: '-(으)ㄹ 수 있다'는 문법 DB에서 1급 항목이다.
ALWAYS_EXEMPT = {
    "년", "월", "일", "시", "분", "초", "명", "개", "번",
    "수", "이", "것", "데", "바",
}
LEXICAL_TAGS = {"NNG", "NP", "VV", "VA", "MAG", "MAJ", "MM", "XR"}
STRICT_REGISTERED_VOCABULARY_GRADES = {1, 2}
BEGINNER_BASIC_AUDIT_EXEMPTIONS = {
    "오늘", "내일", "날", "나", "있다", "없다", "이제", "모두", "우리",
    "매일", "조금", "다", "크다",
}
REVISION_MARKER = re.compile(
    r"^[ \t]*(?:\*\*)?[\[(]?\s*(?:교정|수정)(?:된)?\s+(?:결과|지문)\s*[\])]?[ \t]*:?[ \t]*(?:\*\*)?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


@lru_cache(maxsize=1)
def kiwi() -> Kiwi:
    return Kiwi()


@lru_cache(maxsize=1)
def vocabulary_grade_map() -> dict[str, int]:
    with sqlite3.connect(DICTIONARY_DB) as conn:
        rows = conn.execute(
            "SELECT word, MIN(grade) FROM vocabulary GROUP BY word"
        ).fetchall()
    return {str(word): int(grade) for word, grade in rows if word}


@lru_cache(maxsize=6)
def allowed_vocabulary_sample(target_grade: int, limit: int = 220) -> list[str]:
    """프롬프트에 넣을 목표 등급 이하 표제어. 낮은 등급·짧은 어휘부터 제공한다."""
    items = [
        (grade, len(word), word)
        for word, grade in vocabulary_grade_map().items()
        if grade <= target_grade and len(word) >= 2
    ]
    items.sort()
    return [word for _, _, word in items[:limit]]


def _candidate_forms(token: str) -> list[str]:
    forms = [token]
    for particle in PARTICLES:
        if token.endswith(particle) and len(token) > len(particle) + 1:
            forms.append(token[:-len(particle)])
    # 활용형 안에서 사전 표제어가 접두부로 확인되는 경우를 잡는다(예: 활용하여 → 활용).
    lexicon = vocabulary_grade_map()
    prefixes = [
        word for word in lexicon
        if len(word) >= 2 and len(word) < len(token) and token.startswith(word)
    ]
    forms.extend(sorted(prefixes, key=len, reverse=True)[:2])
    return list(dict.fromkeys(forms))


def clean_revised_passage(text: str) -> str:
    """Remove model commentary and duplicated pre-revision text."""
    matches = list(REVISION_MARKER.finditer(text))
    if matches:
        text = text[matches[-1].end():]
    text = text.strip()
    text = re.sub(r"^\s*\[[^\]\n]{1,40}\]\s*\n+", "", text)
    # Some local-model revisions prepend an unmarked short title.
    text = re.sub(r"^\s*[^.!?\n]{1,24}\s*\n\s*\n?", "", text, count=1)
    final_markers = list(re.finditer(
        r"^[ \t]*(?:\*\*)?\[?\s*최종\s+교정본\s*\]?(?:\*\*)?[ \t]*$",
        text,
        flags=re.MULTILINE,
    ))
    if final_markers:
        text = text[final_markers[-1].end():].strip()
    text = re.sub(r"\s*\(\s*[※*]\s*수정\s*:.*?\)\s*", "\n", text, flags=re.DOTALL)
    # Local models sometimes append an audit explanation after the passage.
    # It is metadata, not learner-facing text.
    text = re.split(r"\n\s*\n\s*\(\s*[※*]?\s*참고\s*:", text, maxsplit=1)[0]
    text = re.sub(
        r"\s*\(\s*(?:원문|교정|수정)[^()]*(?:유지|반영|재구성|수정)[^()]*\)\s*$",
        "",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"^```(?:text|markdown)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def polish_beginner_topik_flow(
    passage: str,
    target_grade: int,
    source_text: str,
    min_chars: int,
    max_chars: int,
    exempt_words: set[str] | None = None,
) -> tuple[str, dict, dict]:
    """Apply a bounded, single-scene TOPIK-I final edit to every beginner passage."""
    if target_grade not in {1, 2}:
        return passage, audit_vocabulary(passage, target_grade, exempt_words), {
            "attempted": False, "accepted": False, "reason": "TOPIK I 대상 아님"
        }
    minimum, maximum, target = ((3, 5, 4) if target_grade == 1 else (4, 7, 6))
    prompt = f"""당신은 TOPIK I 교육용 지문 편집자입니다.

[목표]
{target_grade}급 학습자가 읽을 한 장면의 지문을 정확히 {target}문장으로 다시 쓰세요.
전체 길이는 {min_chars}~{max_chars}자를 목표로 하되, 문장을 억지로 늘리거나 새 장면을 넣지 마세요.

[참고 의미]
{source_text}

[현재 지문]
{passage}

[문장 역할]
- 첫 문장: 사람·장소·상황을 구체적으로 제시
- 가운데 문장: 같은 장면의 행동을 시간 순서로 전개하고 필요한 이유를 한 번만 설명
- 마지막 문장: 앞 행동의 직접적인 결과나 간단한 마무리
- 처음 정한 장소와 목적을 마지막까지 유지하고, 다른 장소나 다음 일정으로 넘어가지 않기
- 각 문장은 바로 앞 문장의 사람·장소·행동 중 하나를 이어 받아야 함
- 결과는 `불을 꺼서 전기를 덜 쓴다`처럼 바로 확인할 수 있는 내용으로 쓰기
- `하지만`은 실제 대조일 때만, `그래서·-면·-어서`는 앞 행동이 뒤 결과의 직접 원인일 때만 쓰기
- 마지막 문장은 앞 내용을 한 번만 마무리하고, 앞의 권유나 평가를 다른 말로 반복하지 않기
- 읽은 뒤 `누가, 어디에서, 무엇을, 왜 했는지`가 하나씩 분명하게 남도록 쓰기
- `직원들은 불을 꺼 주세요`처럼 3인칭 주어와 청자 명령을 섞지 않기. 안내문이면 `직원들은 불을 꺼야 합니다`, 직접 부탁이면 `불을 꺼 주세요`로 쓰기
- 한 지문에서는 설명문 `-습니다`, 권유 `-세요`, 대화체 중 중심 말투 하나를 정하고 불필요하게 바꾸지 않기

[금지]
- 제목, 괄호 설명, 교정 메모
- 같은 권유·결론의 반복
- 핵심 행동과 관계없는 식사·약속·응원·새 계획
- 식당 뒤 카페, 회사 뒤 학교처럼 핵심 장소 밖으로 이동하는 후속 장면
- ‘좋은 세상’, ‘자연이 좋아진다’ 같은 막연한 결과
- `전기는 아껴 쓰는 것입니다`처럼 핵심 낱말을 되풀이해 정의하는 문장
- `음식이 빨리 나오면 배가 부르다`처럼 시간상 이어져도 원인과 결과가 아닌 내용을 인과로 연결하는 문장
- `함께 노력합시다`, `즐거운 시간을 보내세요`처럼 구체적 결과 없이 끝나는 상투적인 마무리
- 어려운 말을 쉬운 단어로 하나씩 바꿔 만든 어색한 문장
- 새로운 기관·수치·정책·사실

각 배열 항목에 완결된 문장 하나만 넣고 다음 JSON만 출력하세요.
{{"sentences":["문장1","문장2","문장3","문장4"]}}
"""
    raw = call_gemma_json(prompt, temperature=0.1)
    sentences = [str(x).strip() for x in raw.get("sentences", []) if str(x).strip()]
    revised = clean_revised_passage(" ".join(sentences))
    before_audit = audit_vocabulary(passage, target_grade, exempt_words)
    after_audit = audit_vocabulary(revised, target_grade, exempt_words)
    reasons = []
    if len(sentences) != target:
        reasons.append(f"요청 문장 수 불일치({len(sentences)}개/{target}개)")
    # Coherent beginner flow takes priority over padding with a new schedule.
    beginner_min = max(40, int(min_chars * 0.7))
    if not beginner_min <= len(revised) <= max_chars:
        reasons.append(f"길이 범위 이탈({len(revised)}자/{beginner_min}~{max_chars}자)")
    # Do not fall back to a repetitive original solely because the structural
    # edit introduced a lexical item. The outer validation loop audits and
    # repairs vocabulary again; this stage owns discourse coherence.
    accepted = bool(revised) and not reasons
    return (
        revised if accepted else passage,
        after_audit if accepted else before_audit,
        {
            "attempted": True,
            "accepted": accepted,
            "reason": "통과" if accepted else "; ".join(reasons),
            "candidate_passage": revised,
        },
    )


def audit_vocabulary(
    text: str, target_grade: int, exempt_words: set[str] | None = None
) -> dict:
    lexicon = vocabulary_grade_map()
    exempt_words = (exempt_words or set()) | ALWAYS_EXEMPT
    if target_grade in STRICT_REGISTERED_VOCABULARY_GRADES:
        exempt_words |= BEGINNER_BASIC_AUDIT_EXEMPTIONS
    violations: dict[str, dict] = {}
    known_tokens = 0
    unknown_tokens = []
    unknown_items: dict[str, dict] = {}
    exempt_ranges = []
    for exempt in exempt_words:
        if len(exempt) < 2:
            continue
        start = 0
        while True:
            found = text.find(exempt, start)
            if found < 0:
                break
            exempt_ranges.append((found, found + len(exempt)))
            start = found + len(exempt)
    tokens = list(kiwi().tokenize(text))
    for index, token in enumerate(tokens):
        if any(start <= token.start < end for start, end in exempt_ranges):
            continue
        if token.form == "드세" and text[token.start:token.start + token.len + 2].startswith("드세요"):
            continue
        if token.tag == "NNP":  # 기관명·인명·지명 등 고유명사는 별도 예외 목록으로 기록한다.
            continue
        if token.tag not in LEXICAL_TAGS:
            continue
        surface = token.form
        if surface in exempt_words:
            continue
        lemma = surface + "다" if token.tag in {"VV", "VA"} else surface
        # Kiwi가 형용사를 어근(XR)+접미사(XSA)로 나누는 경우 사전 표제어로 복원한다.
        # 예: 깨끗/XR + 하/XSA + 다/EF -> 깨끗하다
        if token.tag == "XR" and index + 1 < len(tokens):
            following = tokens[index + 1]
            derived = surface + following.form + "다"
            if following.tag == "XSA" and derived in lexicon:
                lemma = derived
        if lemma in exempt_words:
            continue
        if lemma not in lexicon:
            unknown_tokens.append(lemma)
            unknown_items.setdefault(
                lemma,
                {
                    "word": lemma,
                    "part_of_speech": token.tag,
                    "policy": (
                        "blocked_unregistered_lexical_token"
                        if target_grade in STRICT_REGISTERED_VOCABULARY_GRADES
                        else "record_only"
                    ),
                },
            )
            continue
        known_tokens += 1
        form, grade = lemma, lexicon[lemma]
        if grade > target_grade:
            violations.setdefault(
                form, {"word": form, "grade": grade, "part_of_speech": token.tag, "tokens": []}
            )
            if surface not in violations[form]["tokens"]:
                violations[form]["tokens"].append(surface)
    ordered = sorted(violations.values(), key=lambda item: (-item["grade"], item["word"]))
    ordered_unknown = list(unknown_items.values())
    blocked_unknown = [
        item for item in ordered_unknown
        if item["policy"] == "blocked_unregistered_lexical_token"
    ]
    return {
        "engine": "kiwipiepy",
        "target_grade": target_grade,
        "violations": ordered,
        "violation_count": len(ordered),
        "known_token_count": known_tokens,
        "unknown_tokens": list(dict.fromkeys(unknown_tokens)),
        "unknown_token_count": len(set(unknown_tokens)),
        "unknown_items": ordered_unknown,
        "blocked_unknown_tokens": blocked_unknown,
        "blocked_unknown_token_count": len(blocked_unknown),
        # 이전 결과 스키마와의 호환을 위해 별칭을 유지한다.
        "blocked_unknown_nouns": blocked_unknown,
        "blocked_unknown_noun_count": len(blocked_unknown),
        "unknown_policy": (
            "grades_1_2_allow_only_registered_lexical_tokens_at_or_below_target_grade; "
            "grades_3_6_record_unknown_tokens_only"
        ),
    }


def simplify_passage_vocabulary(
    passage: str,
    target_grade: int,
    source_text: str,
    min_chars: int,
    max_chars: int,
    max_rounds: int = 3,
    exempt_words: set[str] | None = None,
) -> tuple[str, dict, list[dict]]:
    """등급 초과 표제어가 없어질 때까지 지문을 제한적으로 다시 쓴다."""
    current = passage
    history = []
    forbidden: set[str] = set()
    allowed_examples = ", ".join(allowed_vocabulary_sample(target_grade))
    essential_terms = ", ".join(sorted(exempt_words or set())) or "없음"
    for round_no in range(1, max_rounds + 1):
        audit = audit_vocabulary(current, target_grade, exempt_words)
        blocked_unknown = audit.get("blocked_unknown_tokens", [])
        if not audit["violations"] and not blocked_unknown:
            return current, audit, history
        forbidden.update(item["word"] for item in audit["violations"])
        forbidden.update(item["word"] for item in blocked_unknown)
        words = ", ".join(sorted(forbidden))
        prompt = f"""당신은 한국어 등급별 어휘 교정자입니다.

[목표]
아래 지문의 {target_grade}급 초과 어휘를 {target_grade}급 이하의 쉬운 표현으로 바꾸세요.
1~2급에서는 조사·어미를 제외한 내용어가 반드시 어휘 DB의 목표 급수 이하 목록에 있어야 합니다.

[절대 사용 금지 어휘 — 활용형·합성어에서도 다시 쓰지 말 것]
{words}

[사용할 수 있는 {target_grade}급 이하 쉬운 어휘 예시]
{allowed_examples}

[교체하지 않을 고유명사·핵심 용어]
{essential_terms}
핵심 용어는 처음 나올 때 목표 등급의 쉬운 말로 바로 설명하세요.

[원자료]
{source_text}

[교체 전 지문]
{current}

[규칙]
- 반드시 교체 대상 어휘와 미등록 내용어를 모두 없애세요.
- 단어만 기계적으로 바꾸지 말고, 해당 단어가 들어간 문장 전체를 자연스럽게 다시 쓰세요.
- 금지 어휘 대신 새로운 어려운 한자어나 전문어를 넣지 마세요.
- '수 있다'가 금지되면 '-는다/-한다'처럼 문장 구조 자체를 바꾸세요.
- '내용→이야기', '모든→다', '이용→쓰다', '지원→돕다'처럼 짧고 구체적으로 바꾸세요.
- 인물·기관명·고유명사와 원자료의 핵심 사실·수치·인과는 바꾸지 마세요.
- 정확한 제도·안전 개념을 뜻이 흐린 일상 표현으로 바꾸지 마세요. 예를 들어 '예방접종'을 '병을 막는 주사'로 바꾸지 마세요.
- 목표 등급에 꼭 필요한 원자료 핵심 용어는 그대로 쓰고, 바로 뒤에서 목표 등급의 쉬운 말로 짧게 설명하세요.
- 새로운 사실을 추가하지 마세요.
- 공백 포함 {min_chars}~{max_chars}자를 유지하세요.
- 문단 구조와 담화 형식을 가능한 한 유지하세요.
- 1~2급의 목표 급수 이하 등록 수식어는 모두 허용하며, 수식어라는 이유만으로 삭제하지 마세요.
- 3~6급에서는 정보 없이 분위기만 꾸미는 평가·감정 수식어와 같은 꾸밈말의 반복을 줄이세요.
- 어려운 단어를 피하려고 뜻이 모호한 수식어구를 새로 만들지 마세요.
- 수정한 지문만 출력하세요.
"""
        revised = clean_revised_passage(call_gemma(prompt, temperature=0.2))
        next_audit = audit_vocabulary(revised, target_grade, exempt_words)
        before_issue_count = (
            audit.get("violation_count", len(audit.get("violations", [])))
            + audit.get("blocked_unknown_token_count", len(blocked_unknown))
        )
        after_issue_count = (
            next_audit.get("violation_count", len(next_audit.get("violations", [])))
            + next_audit.get(
                "blocked_unknown_token_count",
                len(next_audit.get("blocked_unknown_tokens", [])),
            )
        )
        accepted = bool(revised) and after_issue_count < before_issue_count
        history.append({
            "round": round_no,
            "before_chars": len(current),
            "after_chars": len(revised),
            "before_violations": audit["violations"],
            "after_violations": next_audit["violations"],
            "before_blocked_unknown_tokens": audit.get("blocked_unknown_tokens", []),
            "after_blocked_unknown_tokens": next_audit.get("blocked_unknown_tokens", []),
            "accepted": accepted,
            "acceptance_reason": (
                f"어휘 문제 {before_issue_count}->{after_issue_count} 감소"
                if accepted else
                f"어휘 문제 미감소({before_issue_count}->{after_issue_count})"
            ),
        })
        if accepted:
            current = revised
    return current, audit_vocabulary(current, target_grade, exempt_words), history


def polish_passage_naturalness(
    passage: str,
    target_grade: int,
    source_text: str,
    min_chars: int,
    max_chars: int,
    exempt_words: set[str] | None = None,
) -> tuple[str, dict, dict]:
    """Polish whole sentences, accepting only a vocabulary-safe revision."""
    before_audit = audit_vocabulary(passage, target_grade, exempt_words)
    allowed_examples = ", ".join(allowed_vocabulary_sample(target_grade))
    prompt = f"""당신은 한국어 학습용 지문의 자연스러움 교정자입니다.

[목표 등급]
{target_grade}급. 1급이 가장 쉬운 초급이고 6급이 가장 어려운 고급입니다.

[원래 생성 입력]
{source_text}

[교정할 지문]
{passage}

[사용 가능한 어휘 예시]
{allowed_examples}

[교정 규칙]
- 단어 하나만 바꾸는 방식이 아니라 문장 전체와 앞뒤 연결을 자연스럽게 다듬으세요.
- 주어·서술어 호응, 수식 관계, 지시 대상, 시간·인과 관계를 확인하세요.
- `하지만`을 지우면 단순 병렬인지, `그래서·-면·-어서`의 앞 내용이 실제로 뒤 결과를 만드는지 검사하세요. 통과하지 못하는 연결 표현은 고치세요.
- 두 일이 시간상 이어진다는 이유만으로 원인·결과로 연결하지 말고, 행동의 직접 결과만 인과 표현으로 연결하세요.
- 각 문장이 바로 앞 문장의 사람·대상·장소·시간·원인 중 무엇을 이어 받는지 확인하세요. 이어 받는 요소가 없는 문장은 삭제하거나 연결되는 내용으로 다시 쓰세요.
- 동일 인물·대상의 명칭을 일관되게 유지하고, 생략된 주어가 바뀌는 곳에는 주어를 다시 밝히세요.
- 3인칭 주어 뒤에 청자 명령형을 붙이지 마세요. `직원들은 불을 꺼 주세요`는 `직원들은 불을 꺼야 합니다` 또는 `불을 꺼 주세요`처럼 서술 시점을 하나로 맞추세요.
- 설명문·안내문·대화문 가운데 중심 담화 형식을 유지하고, 종결형만 다양하게 보이려고 높임 수준이나 말투를 바꾸지 마세요.
- 1~2급은 서로 무관한 쉬운 문장의 나열을 금지하고, 하나의 장면을 `상황→행동→결과` 또는 `상황→행동→이유/결과` 순서로 정리하세요.
- 1~2급에서 핵심 행동과 관계없는 약속·식사·기분·응원 같은 부수 장면을 추가하지 마세요. 모든 문장은 같은 사람·장소·목적을 이어 가야 합니다.
- 1급은 3~5문장, 2급은 4~7문장을 반드시 지키세요. 같은 권유·평가·결론을 말만 바꾸어 반복하면 한 문장으로 합치거나 삭제하세요.
- 3~4급은 `중심 정보→관련 사실 설명→결과·계획`, 5~6급은 `배경·핵심 내용→근거·방법→의미·전망` 순서로 정보 묶음을 재배열하세요.
- 3급은 전문 용어를 없애기 위해 `규칙이 시작된다`, `움직임을 막는다` 같은 어색한 말로 바꾸지 마세요. 필요한 용어는 유지하고 별도의 자연스러운 문장으로 정확히 설명하세요.
- 4급은 제도명이나 수치를 괄호 속에서 임의로 정의하지 마세요. 승용차 5부제를 카풀이나 특정 횟수의 운전 제한으로 바꾸는 것처럼 원문에 없는 풀이를 만들지 마세요.
- 5급은 같은 주체의 목표와 실행 방법을 한 문단에 묶고, 지원·점검은 다음 문단에서 그 결과로 이어 주세요.
- 6급은 적용 대상·예외·제한을 관련 내용 바로 뒤에 배치하고, 마지막 문장에서 새로운 의무나 핵심 조건을 처음 제시하지 마세요.
- 사실을 체크리스트처럼 나열하지 말고, 같은 대상에 관한 사실끼리 묶어 앞 문장을 다음 문장이 설명하도록 만드세요.
- 연결어를 기계적으로 추가하지 말고 실제 의미가 이유·대조·결과일 때만 사용하세요.
- 실제 TOPIK 읽기 지문처럼 문장마다 주된 정보 관계를 하나만 두세요. 배경·목적·방법·평가가 한 문장에 겹치면 둘로 나누거나 평가를 삭제하세요.
- `최근`, `특히`, `이러한`, `적극적으로`, `다양한`, `주목받고 있다`, `노력하고 있다`, `사회 전반`, `자리 잡다`, `기여할 것으로 보인다`가 사실의 범위나 대비를 구별하지 않으면 삭제하세요.
- 꾸밈말을 지워도 기관·대상·행동·조건·원인·결과가 같다면 그 꾸밈말은 넣지 마세요. 글자 수를 맞추기 위한 홍보성 평가나 일반적인 전망을 보태지 마세요.
- 앞 문장을 `이러한 움직임`, `이 같은 노력`처럼 추상적으로 되받기보다 앞 문장의 핵심 명사를 다시 써서 다음 사실을 직접 연결하세요.
- 한 문장 안의 나열은 문항 단서에 필요한 항목만 남기고, 유사한 방법을 과도하게 열거하지 마세요.
- 마지막 문장은 앞 내용을 마무리해야 하며 새로운 인물·기관·행동·주장을 갑자기 시작하면 안 됩니다.
- 마지막 두 문장이 모두 `노력·약속·함께·즐겁다·좋다` 같은 일반 평가라면 하나를 삭제하고 구체적인 행동이나 결과로 마무리하세요.
- 번역투, 뜻이 모호한 우회 표현, 불필요한 괄호 설명, 같은 종결형의 연속을 고치세요.
- `시설 설치 돈`, `자연이 좋아집니다`, `돈을 아끼지 않아도 됩니다`처럼 단어 뜻은 쉬워도 한국어 결합이나 논리가 어색한 표현은 자연스러운 전체 문장으로 다시 쓰세요.
- 1~2급의 목표 급수 이하 등록 수식어는 모두 허용하고, 자연스럽게 쓰인 수식어를 억지로 삭제하지 마세요.
- 3~6급에서는 없어도 핵심 의미가 같은 평가·감정 수식어와 반복되는 꾸밈말만 줄이세요.
- 원래 주제와 핵심 의미를 바꾸거나 새로운 수치·날짜·법령·기관·정책을 추가하지 마세요.
- 원문의 기관·날짜·수치·대상·의무·금지·지원 관계를 대조하여 관계 방향이나 조건을 바꾸지 마세요. 의미를 확신할 수 없는 전문 용어는 임의로 풀지 말고 유지하세요.
- 비슷한 수치가 반복되어도 수치마다 연결된 주체와 행동을 따로 유지하세요. 서로 다른 집단의 참여 수와 계획 제출 기업 수를 한 사실로 합치지 마세요.
- 원문에 없는 기후·탄소·사회적 효과를 상식으로 추가하지 마세요.
- {target_grade}급 초과 어휘를 새로 넣지 마세요.
- 1~2급은 제102회 TOPIK I처럼 짧고 직접적인 문장, 명시 정보, 쉬운 생활 표현을 우선하세요.
- 목표 급수보다 높은 핵심 주제어가 꼭 필요하면 한두 개만 쓰고 가까운 문장에서 쉽게 풀어 주세요.
- 공백 포함 {min_chars}~{max_chars}자를 목표로 하되 자연스러운 완결성과 목표 급수의 정보 부담을 우선하세요.
- 설명이나 제목 없이 다듬은 지문만 출력하세요.
"""
    revised = clean_revised_passage(call_gemma(prompt, temperature=0.15))
    after_audit = audit_vocabulary(revised, target_grade, exempt_words)
    reasons = []
    # A fluent rewrite is still invalid if it silently replaces the topic.
    # Compare lexical anchors rather than raw characters so inflection changes
    # do not count as topic drift.
    def content_anchors(text: str) -> set[str]:
        return {
            token.form
            for token in kiwi().tokenize(text)
            if token.tag in LEXICAL_TAGS and len(token.form) >= 2
        }

    before_anchors = content_anchors(passage)
    after_anchors = content_anchors(revised)
    anchor_overlap = (
        len(before_anchors & after_anchors) / len(before_anchors)
        if before_anchors else 1.0
    )
    if anchor_overlap < 0.35:
        reasons.append(f"핵심 내용어 유지율 부족({anchor_overlap:.0%})")
    if target_grade in {1, 2}:
        import re
        sentence_count = len([
            part for part in re.split(r"[.!?]+", revised) if part.strip()
        ])
        minimum, maximum = ((3, 5) if target_grade == 1 else (4, 7))
        if not minimum <= sentence_count <= maximum:
            reasons.append(
                f"TOPIK I 문장 수가 허용 범위를 벗어남({sentence_count}개, {minimum}~{maximum}개)"
            )
    if after_audit["violation_count"] > before_audit["violation_count"]:
        reasons.append("등급 초과 어휘 수가 교정 전보다 증가함")
    if after_audit.get("blocked_unknown_token_count", 0) > before_audit.get(
        "blocked_unknown_token_count", 0
    ):
        reasons.append("미등록 내용어 수가 교정 전보다 증가함")
    accepted = not reasons and bool(revised)
    return (
        revised if accepted else passage,
        after_audit if accepted else before_audit,
        {
            "attempted": True,
            "accepted": accepted,
            "reason": "통과" if accepted else "; ".join(reasons),
            "before_passage": passage,
            "candidate_passage": revised,
            "content_anchor_overlap": round(anchor_overlap, 3),
            "before_audit": before_audit,
            "candidate_audit": after_audit,
        },
    )
