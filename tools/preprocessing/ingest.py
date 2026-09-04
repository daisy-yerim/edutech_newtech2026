# -*- coding: utf-8 -*-
"""
ingest.py — RAG 준비 1단계: 자료 읽기(파싱) + 자르기(청킹)

[사용법]
- VS Code에서 Jupyter 확장을 설치하면 아래 `# %%` 마다 "Run Cell" 버튼이 뜸.
- 셀을 위에서부터 순서대로 한 번씩 실행.
- 청킹 실험은 [셀 5]의 CHUNK_SIZE, OVERLAP 값만 바꿔서 셀 5~6만 반복 실행.

[사전 준비]
1. 프로젝트 폴더 구조:
   korean-rag-project/
   ├── data/raw/          <- PDF와 zip을 이름 그대로 넣기 (압축 안 풀어도 됨)
   ├── output/            <- 결과가 여기에 저장됨 (자동 생성)
   └── src/ingest.py      <- 이 파일
2. 터미널에서: pip install pypdf
3. 이 파일을 VS Code로 열고 셀 실행 (실행 위치는 프로젝트 폴더 기준)
"""

# %% [셀 1] 설정 — data/raw 폴더 안의 pdf/zip을 "전부" 자동으로 찾음
# 나중에 파일을 더 추가해도 이 셀을 다시 실행하면 새 파일까지 자동으로 잡힘.
from pathlib import Path

RAW_DIR = Path("data/sources")
OUTPUT_DIR = Path("data/reference")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

pdf_paths = sorted(RAW_DIR.rglob("*.pdf"))
zip_paths = sorted(RAW_DIR.rglob("*.zip"))

if not pdf_paths and not zip_paths:
    raise FileNotFoundError(f"{RAW_DIR} 안에 pdf/zip 파일이 없습니다. 파일을 넣었는지 확인하세요.")

print(f"찾은 PDF {len(pdf_paths)}개:")
for p in pdf_paths:
    print("  -", p.name)
print(f"찾은 ZIP {len(zip_paths)}개:")
for z in zip_paths:
    print("  -", z.name)

# %% [셀 2] PDF 파싱 — data/raw 안의 모든 pdf를 하나씩 순회
# 여러 기준 문서(교육과정, 읽기 연구 등)를 동시에 넣어도 전부 처리됨.
from pypdf import PdfReader

pdf_pages = []  # 모든 pdf의 모든 페이지가 여기 한 리스트에 쌓임

for pdf_path in pdf_paths:
    reader = PdfReader(pdf_path)
    print(f"[{pdf_path.name}] 전체 페이지: {len(reader.pages)}")
    for i, page in enumerate(reader.pages):
        txt = page.extract_text() or ""
        txt = txt.strip()
        if len(txt) > 50:  # 거의 빈 페이지는 제외
            pdf_pages.append({
                "source": pdf_path.name,     # 실제 파일명을 그대로 출처로 기록
                "doc_type": "기준문서",       # 판단 기준(자) 꼬리표
                "page": i + 1,
                "text": txt,
            })

print(f"\n전체 pdf {len(pdf_paths)}개에서 텍스트 있는 페이지 총 {len(pdf_pages)}개")

# %% [셀 3] ZIP 파싱 — data/raw 안의 모든 zip을 순회 (중첩 zip 포함 전부 읽기)
import zipfile, io, json

def read_all_jsons_from_zip(zip_path):
    """바깥 zip과 그 안의 중첩 zip까지 모든 json을 읽어 리스트로 반환."""
    records = []
    zip_name = zip_path.name

    def parse_json_bytes(raw, origin):
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        # 이 데이터셋 구조: {"annotation": [ {text, label, value{...}}, ... ]}
        for ann in data.get("annotation", []):
            records.append({
                "source": zip_name,           # 실제 zip 파일명을 그대로 출처로 기록
                "doc_type": "문항예시",        # 생성 재료/예시 꼬리표
                "origin_file": origin,
                "label": ann.get("label", ""),          # 추론형/사실형 등
                "text": ann.get("text", ""),
                "확실성": ann.get("value", {}).get("확실성", ""),
                "극성": ann.get("value", {}).get("극성", ""),
                "시제": ann.get("value", {}).get("시제", ""),
            })

    with zipfile.ZipFile(zip_path) as oz:
        for name in oz.namelist():
            if name.endswith(".json"):
                parse_json_bytes(oz.read(name), name)
            elif name.endswith(".zip"):
                # 중첩 zip: 메모리에서 바로 열기 (디스크에 안 풀어도 됨)
                inner_bytes = io.BytesIO(oz.read(name))
                try:
                    with zipfile.ZipFile(inner_bytes) as iz:
                        for iname in iz.namelist():
                            if iname.endswith(".json"):
                                parse_json_bytes(iz.read(iname), f"{name} > {iname}")
                except zipfile.BadZipFile:
                    print(f"[경고] 열 수 없는 zip 건너뜀: {name}")
    return records

sentence_records = []
for zip_path in zip_paths:
    recs = read_all_jsons_from_zip(zip_path)
    print(f"[{zip_path.name}] 문장 레코드 {len(recs)}개")
    sentence_records.extend(recs)

print(f"\n전체 zip {len(zip_paths)}개에서 문장 레코드 총 {len(sentence_records)}개")

# 라벨 분포 확인 — 추론형이 몇 개인지 등
from collections import Counter
print(Counter(r["label"] for r in sentence_records).most_common(10))

# %% [셀 4] 청킹 함수 정의
def chunk_text(text, chunk_size, overlap):
    """텍스트를 chunk_size 글자씩, overlap만큼 겹치게 자른다."""
    if overlap >= chunk_size:
        raise ValueError("overlap은 chunk_size보다 작아야 합니다")
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks

# %% [셀 5] 청킹 실험 — 이 값만 바꿔가며 이 셀과 다음 셀을 반복 실행!
CHUNK_SIZE = 500   # <- 실험: 300 / 500 / 800 / 1000 등으로 바꿔보기
OVERLAP = 50       # <- 실험: 0 / 50 / 100 / 200 등으로 바꿔보기

all_chunks = []

# (1) PDF: 페이지 단위 텍스트를 청킹. 어느 파일·페이지 출신인지 유지
for p in pdf_pages:
    safe_name = Path(p["source"]).stem  # 확장자 뺀 파일명 (id에 쓰기 위해)
    for j, c in enumerate(chunk_text(p["text"], CHUNK_SIZE, OVERLAP)):
        all_chunks.append({
            "chunk_id": f"pdf_{safe_name}_p{p['page']}_c{j}",
            "source": p["source"],
            "doc_type": p["doc_type"],
            "page": p["page"],
            "text": c,
        })

# (2) 문장 데이터: 문장 하나가 이미 짧아서 자르지 않고 그대로 1건 = 1청크
#     (이미 문장 단위로 나뉜 데이터는 억지로 자르면 오히려 나빠짐)
for k, r in enumerate(sentence_records):
    if len(r["text"]) < 10:
        continue
    all_chunks.append({
        "chunk_id": f"sent_{k}",
        "source": r["source"],
        "doc_type": r["doc_type"],
        "label": r["label"],
        "text": r["text"],
    })

print(f"CHUNK_SIZE={CHUNK_SIZE}, OVERLAP={OVERLAP}")
print(f"PDF에서 나온 청크: {sum(1 for c in all_chunks if c['chunk_id'].startswith('pdf'))}개")
print(f"문장 데이터 청크: {sum(1 for c in all_chunks if c['chunk_id'].startswith('sent'))}개")
print(f"총 청크 수: {len(all_chunks)}개")

# %% [셀 6] 결과 눈으로 확인 + 파일 저장
# 눈 확인: PDF 청크 앞쪽 2개, 문장 청크 2개
print("===== PDF 청크 예시 =====")
pdf_samples = [c for c in all_chunks if c["chunk_id"].startswith("pdf")][:2]
for c in pdf_samples:
    print(f"[{c['chunk_id']}] ({len(c['text'])}자, 출처:{c['source']})")
    print(c["text"][:150], "...\n")

print("===== 문장 청크 예시 =====")
sent_samples = [c for c in all_chunks if c["chunk_id"].startswith("sent")][:2]
for c in sent_samples:
    print(f"[{c['chunk_id']}] label={c.get('label')}")
    print(c["text"][:150], "\n")

# 파일 저장 — output/chunks_{크기}_{겹침}.json 으로 실험별 구분 저장
out_path = OUTPUT_DIR / f"chunks_{CHUNK_SIZE}_{OVERLAP}.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(all_chunks, f, ensure_ascii=False, indent=1)
print(f"저장 완료 -> {out_path}  ({out_path.stat().st_size / 1024 / 1024:.1f} MB)")

# %% [셀 7] (선택) 여러 설정 한 번에 비교 — 청크 개수와 평균 길이만 빠르게 보기
for cs, ov in [(300, 0), (300, 50), (500, 50), (800, 100), (1000, 200)]:
    n = sum(len(chunk_text(p["text"], cs, ov)) for p in pdf_pages)
    print(f"chunk_size={cs:5d}, overlap={ov:4d} -> PDF 청크 {n:5d}개")
