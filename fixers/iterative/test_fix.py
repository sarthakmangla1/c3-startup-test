import importlib.util
from pathlib import Path
import tempfile

SPEC = importlib.util.spec_from_file_location("c3fix", Path(__file__).with_name("fix.py"))
fix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fix)


def test_parser_and_path_guard():
    reply = """=== FILE: src/pkg/a.py ===
print('ok')
=== END ===
"""
    assert fix.parse_files(reply) == [("src/pkg/a.py", "print('ok')")]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        old_ws, old_src = fix.WS, fix.SRC
        try:
            fix.WS = root
            fix.SRC = root / "src"
            assert fix.safe_target("src/pkg/a.py") == root / "src/pkg/a.py"
            assert fix.safe_target("src/../../oops.py") is None
            assert fix.safe_target("README.md") is None
            assert fix.safe_target("src/pkg/data.bin") is None
        finally:
            fix.WS, fix.SRC = old_ws, old_src


def test_snapshot_restore():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        old_ws, old_src = fix.WS, fix.SRC
        try:
            fix.WS = root
            fix.SRC = root / "src"
            a = fix.SRC / "pkg" / "a.py"
            a.parent.mkdir(parents=True)
            a.write_text("original\n")
            snap = fix.snapshot_src()
            a.write_text("broken\n")
            (fix.SRC / "new.py").write_text("extra\n")
            fix.restore_src(snap)
            assert a.read_text() == "original\n"
            assert not (fix.SRC / "new.py").exists()
        finally:
            fix.WS, fix.SRC = old_ws, old_src


def test_terms_include_protocol_identifiers():
    terms = fix.token_terms("lease_report_after_pause lease_fenced duplicate RPC timeout")
    assert "lease_report_after_pause" in terms
    assert "lease_fenced" in terms
