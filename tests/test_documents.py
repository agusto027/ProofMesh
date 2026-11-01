from pathlib import Path

import pytest

from proofmesh.evidence.documents import read_context_document


def test_context_document_is_scoped_to_configured_root(tmp_path: Path):
    (tmp_path / "notes.md").write_text("A short user note.", encoding="utf-8")
    assert read_context_document("notes.md", str(tmp_path))["excerpt"] == "A short user note."
    with pytest.raises(ValueError):
        read_context_document("../outside.txt", str(tmp_path))
