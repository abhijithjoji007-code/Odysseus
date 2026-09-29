from pathlib import Path

from app.services.file_finder import FileFinder


def test_file_finder_ranks_matching_pdf(tmp_path: Path):
    notes = tmp_path / "Microbiology_Unit_1_Notes.pdf"
    notes.write_text("test", encoding="utf-8")
    (tmp_path / "random.txt").write_text("test", encoding="utf-8")
    finder = FileFinder([tmp_path])
    matches = finder.search("open my microbiology pdf")
    assert matches
    assert matches[0].path == notes


def test_file_finder_filters_python(tmp_path: Path):
    code = tmp_path / "analysis.py"
    code.write_text("print('ok')", encoding="utf-8")
    (tmp_path / "analysis.pdf").write_text("x", encoding="utf-8")
    matches = FileFinder([tmp_path]).search("find python analysis file")
    assert matches
    assert all(match.path.suffix in {".py", ".ipynb"} for match in matches)


def test_file_finder_ignores_generated_directories(tmp_path: Path):
    hidden = tmp_path / "node_modules" / "microbiology.pdf"
    hidden.parent.mkdir()
    hidden.write_text("x", encoding="utf-8")
    visible = tmp_path / "Microbiology_Notes.pdf"
    visible.write_text("x", encoding="utf-8")
    matches = FileFinder([tmp_path]).search("find my microbiology pdf")
    assert [match.path for match in matches] == [visible]


def test_file_finder_respects_scan_limit(tmp_path: Path):
    for index in range(5):
        (tmp_path / f"notes_{index}.pdf").write_text("x", encoding="utf-8")
    matches = FileFinder([tmp_path], max_scanned_files=2).search("find notes pdf")
    assert len(matches) <= 2
