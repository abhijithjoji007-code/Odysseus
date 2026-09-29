from pathlib import Path
from app.services.document_reader import DocumentReader

def test_reader_enforces_roots_and_bounds(tmp_path: Path):
    allowed = tmp_path / "notes"; allowed.mkdir()
    note = allowed / "bio.md"; note.write_text("Chapter 1\nCells", encoding="utf-8")
    ok, _, data = DocumentReader([allowed], max_chars=8).read(str(note))
    assert ok and data["text"] == "Chapter "
    outside = tmp_path / "secret.txt"; outside.write_text("no", encoding="utf-8")
    assert not DocumentReader([allowed]).read(str(outside))[0]
