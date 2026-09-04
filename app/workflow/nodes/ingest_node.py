"""교수자가 업로드한 PDF/TXT/MD에서 모델 입력용 텍스트를 추출한다."""

from pathlib import Path

DemoState = dict
MAX_SOURCE_CHARS = 12000


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    pages = []
    for page in PdfReader(str(path)).pages:
        text = (page.extract_text() or "").strip()
        if len(text) > 50:
            pages.append(text)
    return "\n".join(pages)


def _extract_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _representative_excerpt(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    """긴 자료의 처음만 자르지 않고 앞·중간·끝을 고르게 보존한다."""
    if len(text) <= limit:
        return text
    part = limit // 3
    middle = len(text) // 2
    return "\n\n[중간 생략]\n\n".join([
        text[:part],
        text[middle - part // 2:middle + part // 2],
        text[-part:],
    ])


def ingest_node(state: DemoState) -> dict:
    path = Path(state["uploaded_filename"])
    if not path.exists():
        raise FileNotFoundError(f"업로드 파일을 찾을 수 없습니다: {path}")

    if path.suffix.lower() == ".pdf":
        original = _extract_pdf(path)
    elif path.suffix.lower() in {".txt", ".md"}:
        original = _extract_text(path)
    else:
        raise ValueError(f"지원하지 않는 형식입니다: {path.suffix}")

    original = original.strip()
    if not original:
        raise ValueError(f"{path.name}에서 텍스트를 추출하지 못했습니다.")

    truncated = len(original) > MAX_SOURCE_CHARS
    text = _representative_excerpt(original)
    note = f"[자료 수집] {path.name} · 모델 입력 {len(text):,}자"
    if truncated:
        note += f" (원문 {len(original):,}자에서 앞·중간·끝 발췌)"
    return {"source_text": text, "log": [note]}
