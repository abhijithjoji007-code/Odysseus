from __future__ import annotations

from pathlib import Path

class DocumentReader:
    EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
    def __init__(self, allowed_roots: list[Path], max_bytes: int = 15_000_000, max_chars: int = 80_000, max_pages: int = 40):
        self.roots = [p.expanduser().resolve() for p in allowed_roots]
        self.max_bytes, self.max_chars, self.max_pages = max_bytes, max_chars, max_pages
    def read(self, value: str) -> tuple[bool, str, dict]:
        path = Path(value).expanduser().resolve()
        if path.suffix.lower() not in self.EXTENSIONS: return False, "Unsupported document type.", {}
        if not path.is_file() or not any(path == r or r in path.parents for r in self.roots): return False, "Document is outside configured search roots or does not exist.", {}
        if path.stat().st_size > self.max_bytes: return False, "Document exceeds the safe size limit.", {}
        try:
            if path.suffix.lower() == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(str(path)); text = "\n".join((p.extract_text() or "") for p in reader.pages[:self.max_pages]); pages = min(len(reader.pages), self.max_pages)
            elif path.suffix.lower() == ".docx":
                from docx import Document
                doc = Document(str(path)); text = "\n".join(p.text for p in doc.paragraphs); pages = None
            else: text, pages = path.read_text(encoding="utf-8", errors="replace"), None
        except Exception as exc: return False, f"Document could not be read safely: {type(exc).__name__}.", {}
        text = text[:self.max_chars]
        return bool(text.strip()), "Document text extracted." if text.strip() else "No readable text was found.", {"path": str(path), "text": text, "pages": pages, "truncated": len(text) >= self.max_chars}
