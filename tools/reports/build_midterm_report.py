"""Build the self-contained midterm report draft from Markdown."""

from __future__ import annotations

import re
from pathlib import Path

import mistune

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/reports/midterm_2026-08"
SOURCE = BASE / "midterm_report_draft.md"
OUTPUT = BASE / "midterm_report_draft.html"


def figure(src: str, caption: str, cls: str = "") -> str:
    return (
        f'<figure class="screen {cls}"><img src="{src}" alt="{caption}">'
        f'<figcaption>{caption}</figcaption></figure>'
    )


SYSTEM_FLOW = """
<figure class="diagram"><svg viewBox="0 0 1180 260" role="img" aria-label="시스템 생성 검증 흐름">
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#3159d4"/></marker></defs>
<g class="node"><rect x="20" y="82" width="145" height="78"/><text x="92" y="112">교수자 자료</text><text x="92" y="137">PDF·TXT·MD</text></g>
<g class="node"><rect x="205" y="82" width="145" height="78"/><text x="277" y="112">근거 추출</text><text x="277" y="137">기준 조회</text></g>
<g class="node strong"><rect x="390" y="35" width="160" height="78"/><text x="470" y="65">로컬 LLM</text><text x="470" y="90">지문·문항 생성</text></g>
<g class="node strong"><rect x="390" y="150" width="160" height="78"/><text x="470" y="180">결정적 검사</text><text x="470" y="205">어휘·구조·근거</text></g>
<g class="node"><rect x="600" y="82" width="155" height="78"/><text x="677" y="112">AI 검증</text><text x="677" y="137">실패 항목 수정</text></g>
<g class="node"><rect x="795" y="82" width="155" height="78"/><text x="872" y="112">교수자 승인</text><text x="872" y="137">문항 공개</text></g>
<g class="node"><rect x="990" y="82" width="165" height="78"/><text x="1072" y="112">학습자 응답</text><text x="1072" y="137">채점·피드백</text></g>
<g class="edge"><path d="M165 121H202"/><path d="M350 121H385"/><path d="M550 75C585 75 565 121 595 121"/><path d="M550 189C585 189 565 121 595 121"/><path d="M755 121H790"/><path d="M950 121H985"/></g>
</svg><figcaption>그림 1. 근거 조회·생성·검증·교수자 승인·학습자 평가가 연결된 전체 흐름</figcaption></figure>
"""

ROLE_MAP = """
<figure class="diagram role"><div class="role-grid">
<div class="role-card university"><b>주관대학(안)</b><span>교육 기준 해석</span><span>문항 제작 원리</span><span>전문가·학습자 실증</span></div>
<div class="role-core"><b>공동 의사결정</b><span>요구사항</span><span>오류 분석</span><span>기준 변경 승인</span></div>
<div class="role-card company"><b>공동연구기업(안)</b><span>로컬 LLM·RAG</span><span>워크플로·웹·DB</span><span>실험 자동화</span></div>
</div><figcaption>그림 2. 공동연구 수행 체계 초안(기관 실명과 책임 범위는 협약서 대조 필요)</figcaption></figure>
"""

TIMELINE = """
<figure class="timeline"><div class="track">
<div class="month"><b>2026.07</b><span>프로토타입 구조</span><span>v1→v2 재설계</span><span>검증 루프 실험</span></div>
<div class="month active"><b>2026.08</b><span>기준·데이터 정리</span><span>초·중·고급 분리</span><span>24개 지문 실험</span></div>
<div class="month future"><b>M+1~M+2</b><span>전문가 타당화</span><span>오류 분석·개선</span></div>
<div class="month future"><b>M+3~M+4</b><span>교사·학습자 실증</span><span>사용성·난이도 검증</span></div>
<div class="month future"><b>M+5~M+6</b><span>통합 분석</span><span>최종 성과물</span></div>
</div><figcaption>그림 3. 확인된 수행 기간과 향후 단계 일정 초안</figcaption></figure>
"""

METRICS = """
<figure class="metrics"><div class="chart-grid">
<div class="chart"><h4>검증 오류 감소</h4><div class="bar"><i style="width:100%"></i><b>초기 11건</b></div><div class="bar good"><i style="width:36.4%"></i><b>최종 4건</b></div><p>7건 감소 · 63.6% 개선</p></div>
<div class="chart"><h4>초과 어휘 감소</h4><div class="bar"><i style="width:100%"></i><b>초기 265건</b></div><div class="bar good"><i style="width:61.9%"></i><b>최종 164건</b></div><p>101건 감소 · 38.1% 개선</p></div>
<div class="chart"><h4>최신 24개 실험</h4><div class="donut"><span>23<small>/24</small></span></div><p>자동 PASS 23 · 검토 필요 1</p></div>
</div><figcaption>그림 4. 중간 단계 핵심 실험 지표</figcaption></figure>
"""

ROADMAP = """
<figure class="roadmap"><div class="road-grid">
<div><b>1</b><strong>기준 동결</strong><span>전문가 평가표·버전 1.0</span></div>
<div><b>2</b><strong>전문가 평가</strong><span>급수·자연스러움·타당도</span></div>
<div><b>3</b><strong>로직 개선</strong><span>독립 자연스러움 검증</span></div>
<div><b>4</b><strong>현장 실증</strong><span>교사·학습자 사용 로그</span></div>
<div><b>5</b><strong>최종 통합</strong><span>보고서·프로토타입·매뉴얼</span></div>
</div><figcaption>그림 8. 중간보고 이후 연구 추진 단계</figcaption></figure>
"""


def main() -> None:
    markdown = mistune.create_markdown(plugins=["table"])
    body = markdown(SOURCE.read_text(encoding="utf-8"))
    body = body.replace("<h3>1.5 공동연구 수행 체계 및 역할 분담(초안)</h3>", ROLE_MAP + "<h3>1.5 공동연구 수행 체계 및 역할 분담(초안)</h3>")
    body = body.replace("<h3>1.6 시스템 수행 체계</h3>", "<h3>1.6 시스템 수행 체계</h3>" + SYSTEM_FLOW)
    body = body.replace("<h2>2. 월별 연구 진행 내용</h2>", "<h2>2. 월별 연구 진행 내용</h2>" + TIMELINE)
    body = body.replace("<h4>7월 주요 발견</h4>", METRICS + "<h4>7월 주요 발견</h4>")
    body = body.replace("<h3>3.1 교사 기능</h3>", "<h3>3.1 교사 기능</h3>" + figure("images/teacher_prototype.png", "그림 5. 교수자용 정적 UI 프로토타입 화면"))
    body = body.replace("<h3>3.2 학습자 기능</h3>", "<h3>3.2 학습자 기능</h3>" + figure("images/learner_prototype.png", "그림 6. 학습자용 정적 UI 프로토타입 화면"))
    body = body.replace("<h4>최신 24개 지문 실험</h4>", "<h4>최신 24개 지문 실험</h4>" + figure("images/experiment_report.png", "그림 7. 최신 24개 지문 실험 통합 화면"))
    body = body.replace("<h3>4.5 향후 일정 초안</h3>", ROADMAP + "<h3>4.5 향후 일정 초안</h3>")

    placeholders = [
        "과제명", "주관대학명", "공동연구기업명", "연구책임자", "총 연구기간",
        "당초 월별 계획", "정량 목표치", "한국어교육 전문가 수", "교사 수", "학습자 수",
    ]
    for item in placeholders:
        body = body.replace(f"[{item}]", f'<mark class="todo">[{item} 입력 필요]</mark>')

    headings = re.findall(r"<h([2-3])>(.*?)</h\1>", body)
    toc = []
    for index, (level, title) in enumerate(headings, 1):
        clean = re.sub("<.*?>", "", title)
        anchor = f"sec-{index}"
        body = body.replace(f"<h{level}>{title}</h{level}>", f'<h{level} id="{anchor}">{title}</h{level}>', 1)
        toc.append(f'<a class="l{level}" href="#{anchor}">{clean}</a>')

    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>한국어 평가 문항 생성 시스템 중간보고서 초안</title><style>
:root{{--navy:#15223b;--blue:#3159d4;--sky:#eaf0ff;--ink:#20283a;--muted:#667085;--line:#d8dfeb;--paper:#fff;--bg:#eef2f7;--green:#0b8061;--amber:#f5b942}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Malgun Gothic","Noto Sans KR",sans-serif;line-height:1.72}}.page{{max-width:1180px;margin:28px auto 70px;background:var(--paper);box-shadow:0 14px 50px #26334d1a;border-radius:18px;overflow:hidden}}
.cover{{min-height:680px;padding:84px 78px;background:linear-gradient(145deg,#14213d 0%,#263f84 70%,#4e72db 100%);color:white;position:relative}}.cover:after{{content:"";position:absolute;width:430px;height:430px;border:1px solid #ffffff2c;border-radius:50%;right:-120px;top:-80px;box-shadow:0 0 0 65px #ffffff0b,0 0 0 130px #ffffff08}}.cover .eyebrow{{letter-spacing:.16em;font-weight:700;color:#cbd8ff}}.cover h1{{font-size:46px;line-height:1.28;margin:42px 0 22px;max-width:780px;color:white}}.cover .sub{{font-size:20px;color:#e3e9ff;max-width:760px}}.cover .meta{{position:absolute;bottom:64px;left:78px;right:78px;display:flex;justify-content:space-between;border-top:1px solid #ffffff50;padding-top:18px;color:#d9e2ff}}
.summary{{padding:34px 58px;background:#f8faff;border-bottom:1px solid var(--line)}}.stat-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}}.stat{{background:white;border:1px solid #dbe3f6;border-radius:13px;padding:16px}}.stat b{{display:block;color:var(--blue);font-size:25px}}.stat span{{font-size:13px;color:var(--muted)}}
.layout{{display:grid;grid-template-columns:245px minmax(0,1fr)}}nav{{padding:32px 20px;background:#f8faff;border-right:1px solid var(--line);position:relative}}nav .sticky{{position:sticky;top:18px}}nav h3{{margin-top:0}}nav a{{display:block;text-decoration:none;color:#34425d;border-left:2px solid #ced7ea;padding:6px 9px;font-size:13px}}nav a.l3{{padding-left:22px;color:#69758b;font-size:12px}}nav a:hover{{color:var(--blue);border-color:var(--blue)}}main{{padding:40px 50px 80px;min-width:0}}
h1,h2,h3,h4{{color:var(--navy);line-height:1.35}}main h1{{font-size:32px;margin-top:0}}h2{{font-size:27px;margin-top:58px;padding-bottom:11px;border-bottom:3px solid var(--navy)}}h3{{font-size:20px;margin-top:34px}}h4{{font-size:17px;margin-top:28px}}p,li{{font-size:14.5px}}blockquote{{margin:18px 0;padding:14px 18px;background:#fff8dc;border-left:4px solid var(--amber);color:#5b5130}}code{{font-family:Consolas,monospace;background:#eef1f7;padding:2px 5px;border-radius:4px;font-size:.9em}}pre{{white-space:pre-wrap;background:#172238;color:#ecf1ff;padding:18px;border-radius:10px;overflow:auto}}mark.todo{{background:#fff0a8;color:#664d00;padding:2px 5px;border-radius:4px;font-weight:700}}
table{{width:100%;border-collapse:collapse;margin:16px 0 24px;font-size:13px}}th{{background:#edf2ff;color:#203360}}th,td{{border:1px solid var(--line);padding:10px;vertical-align:top;text-align:left}}tr:nth-child(even) td{{background:#fafbfd}}
figure{{margin:24px 0 34px}}figcaption{{text-align:center;color:var(--muted);font-size:12px;margin-top:9px}}.screen img{{display:block;width:100%;max-height:720px;object-fit:cover;object-position:top;border:1px solid var(--line);border-radius:12px;box-shadow:0 10px 30px #25314a1a}}.diagram{{background:#f8faff;border:1px solid var(--line);border-radius:14px;padding:18px}}.diagram svg{{display:block;width:100%}}.node rect{{fill:white;stroke:#aebfe7;stroke-width:2;rx:13}}.node.strong rect{{fill:#e9efff;stroke:#3159d4}}.node text{{font-size:15px;text-anchor:middle;fill:#243453;font-weight:700}}.edge path{{fill:none;stroke:#3159d4;stroke-width:3;marker-end:url(#arrow)}}
.role-grid{{display:grid;grid-template-columns:1fr .72fr 1fr;gap:18px;align-items:center}}.role-card,.role-core{{display:flex;flex-direction:column;gap:8px;text-align:center;border-radius:14px;padding:22px}}.role-card{{background:white;border:2px solid #bdcaea}}.role-core{{background:#3159d4;color:white}}.role-core b{{color:white}}.role-grid span{{font-size:13px}}
.track{{display:grid;grid-template-columns:repeat(5,1fr);gap:0;position:relative}}.track:before{{content:"";position:absolute;left:7%;right:7%;top:22px;height:4px;background:#cbd5eb}}.month{{position:relative;text-align:center;padding:0 8px}}.month:before{{content:"";display:block;width:17px;height:17px;border:5px solid white;background:#8295c6;border-radius:50%;margin:14px auto 14px;position:relative;z-index:1;box-shadow:0 0 0 2px #8295c6}}.month.active:before{{background:#3159d4;box-shadow:0 0 0 2px #3159d4}}.month.future:before{{background:#fff;box-shadow:0 0 0 2px #9cacd2}}.month b,.month span{{display:block}}.month span{{font-size:11px;color:var(--muted)}}
.chart-grid{{display:grid;grid-template-columns:1fr 1fr .8fr;gap:18px}}.chart{{border:1px solid var(--line);background:white;border-radius:12px;padding:16px;text-align:center}}.chart h4{{margin:0 0 14px}}.bar{{height:34px;background:#edf0f6;border-radius:7px;margin:10px 0;position:relative;overflow:hidden;text-align:left}}.bar i{{display:block;height:100%;background:#df6a63}}.bar.good i{{background:#27a17d}}.bar b{{position:absolute;left:10px;top:5px;font-size:12px}}.chart p{{font-size:12px;color:var(--muted)}}.donut{{width:110px;height:110px;border-radius:50%;margin:5px auto;background:conic-gradient(#3159d4 0 95.8%,#e1e6f2 95.8%);display:grid;place-items:center}}.donut:before{{content:"";position:absolute;width:76px;height:76px;background:white;border-radius:50%}}.donut span{{position:relative;font-size:26px;font-weight:800;color:#243f94}}.donut small{{font-size:12px}}
.road-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}}.road-grid div{{background:white;border:1px solid var(--line);border-radius:10px;padding:14px;min-height:135px}}.road-grid b{{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:#3159d4;color:white}}.road-grid strong,.road-grid span{{display:block;margin-top:8px}}.road-grid span{{font-size:11px;color:var(--muted)}}
.footer-note{{padding:24px 50px;background:#172238;color:#dce5ff;font-size:12px}}
@media(max-width:900px){{.page{{margin:0;border-radius:0}}.layout{{grid-template-columns:1fr}}nav{{display:none}}main{{padding:28px 20px}}.cover{{padding:60px 30px}}.cover .meta{{left:30px;right:30px}}.stat-grid,.chart-grid{{grid-template-columns:1fr 1fr}}.role-grid,.road-grid{{grid-template-columns:1fr}}}}
@media print{{body{{background:white}}.page{{margin:0;box-shadow:none;max-width:none}}nav{{display:none}}.layout{{display:block}}main{{padding:25mm 18mm}}.cover{{min-height:260mm;page-break-after:always}}.summary{{page-break-after:always}}h2{{page-break-before:always}}h2:first-of-type{{page-break-before:auto}}figure,table{{break-inside:avoid}}a{{color:inherit}}}}
</style></head><body><div class="page">
<section class="cover"><div class="eyebrow">INTERIM RESEARCH REPORT · DRAFT</div><h1>한국어 읽기·쓰기 평가 문항 생성 및 검증 시스템</h1><p class="sub">근거 기반 로컬 LLM 생성·검증 워크플로 및 교사·학습자 프로토타입 개발</p><div class="meta"><span>작성 기준일 2026.08.04</span><span>내부 검토용 초안</span></div></section>
<section class="summary"><div class="stat-grid"><div class="stat"><b>2</b><span>공공 원문</span></div><div class="stat"><b>24</b><span>최신 지문</span></div><div class="stat"><b>23/24</b><span>자동 PASS</span></div><div class="stat"><b>30</b><span>생성·검증 회차</span></div><div class="stat"><b>13</b><span>회귀 테스트</span></div></div></section>
<div class="layout"><nav><div class="sticky"><h3>목차</h3>{''.join(toc)}</div></nav><main>{body}</main></div>
<div class="footer-note">본 문서는 저장소에서 확인된 구현·실험 근거를 바탕으로 작성한 초안입니다. 기관명, 총 연구기간, 당초 계획 대비표, 참여자 수와 정량 목표는 협약서·연구계획서를 대조해 확정해야 합니다.</div>
</div></body></html>"""
    OUTPUT.write_text(doc, encoding="utf-8")
    print(OUTPUT.resolve())


if __name__ == "__main__":
    main()
