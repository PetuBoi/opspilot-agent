import pytest

from opspilot.demo import seed
from opspilot.retrieval import KnowledgeBase
from opspilot.store import Store


def test_index_search_sources_reindex_and_duplicates(tmp_path):
    store = Store(tmp_path / "db")
    directory = tmp_path / "kb"
    seed(store, directory)
    kb = KnowledgeBase(store)
    assert kb.index(directory)["documents"] == 24
    result = kb.search("VPN certificate expired")
    assert result[0].document_id == "kb-01"
    assert result[0].source == "kb-01-vpn.md"
    assert result[0].metadata["trust"] == "untrusted"
    assert kb.valid_citations([r.chunk_id for r in result])
    assert not kb.valid_citations(["invented"])
    original = result[0].chunk_id
    (directory / "copy.txt").write_text((directory / result[0].source).read_text("utf-8"), "utf-8")
    assert kb.index(directory)["documents"] == 24
    assert kb.search("VPN certificate expired")[0].chunk_id == original
    assert kb.search('" OR ( DROP TABLE chunks; --') is not None
    assert kb.search("zzzzunfindable") == []
    assert kb.search("") == []
    with pytest.raises(ValueError):
        kb.search("anything", 0)
    with pytest.raises(ValueError):
        kb.index(tmp_path / "missing")
    with pytest.raises(ValueError):
        kb.index(directory, 1)
    (directory / "copy.txt").unlink()
    (directory / "kb-01-vpn.md").unlink()
    kb.index(directory)
    assert not kb.valid_citations([original])


def test_plain_text_and_no_evidence(tmp_path):
    directory = tmp_path / "kb"
    directory.mkdir()
    (directory / "guide.txt").write_text("printer calibration guide", "utf-8")
    kb = KnowledgeBase(Store(tmp_path / "db"))
    kb.index(directory)
    assert kb.search("calibration")[0].metadata["service"] == "unknown"
