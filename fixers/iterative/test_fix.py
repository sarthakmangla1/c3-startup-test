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
    assert fix.parse(reply) == [("src/pkg/a.py", "print('ok')")]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        old_ws, old_src = fix.WS, fix.SRC
        try:
            fix.WS = root
            fix.SRC = root / "src"
            assert fix.target_for("src/pkg/a.py") == root / "src/pkg/a.py"
            assert fix.target_for("src/../../outside.py") is None
            assert fix.target_for("README.md") is None
            assert fix.target_for("src/pkg/data.bin") is None
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
            snap = fix.snapshot()
            a.write_text("broken\n")
            (fix.SRC / "new.py").write_text("extra\n")
            fix.restore(snap)
            assert a.read_text() == "original\n"
            assert not (fix.SRC / "new.py").exists()
        finally:
            fix.WS, fix.SRC = old_ws, old_src


def test_terms_include_protocol_identifiers():
    found = fix.terms("lease_report_after_pause lease_fenced duplicate RPC timeout")
    assert "lease_report_after_pause" in found
    assert "lease_fenced" in found
