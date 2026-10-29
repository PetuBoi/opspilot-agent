import io
import json

import httpx
import pandas as pd
import pytest

from opspilot.datasets import anonymize, download, eda, load, validate_frame


def test_real_adapter_validation_cache_and_eda(tmp_path):
    buffer = io.BytesIO()
    pd.DataFrame(
        {"text": ["test network", "test network", "mail delivery"], "label": [0, 0, 1]}
    ).to_parquet(buffer)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        if "/api/" in str(request.url):
            return httpx.Response(200, json={"sha": "pinned-fixture-revision"})
        return httpx.Response(200, content=buffer.getvalue())

    client = httpx.Client(transport=httpx.MockTransport(respond))
    root = tmp_path / "data"
    assert download(root, client)["license"] == "CC BY 4.0"
    assert len(calls) == 3
    download(root, client)
    assert len(calls) == 3
    train, test, metadata = load(root)
    assert len(train) == len(test) == 3
    assert metadata["revision"] == "pinned-fixture-revision"
    summary = eda(root, tmp_path / "reports")
    assert summary["rows"] == 6
    assert summary["cross_split_duplicate_texts"] == 2
    assert (tmp_path / "reports" / "text_lengths.png").exists()
    assert json.loads((root / "manifest.json").read_text())["sha256"]
    assert anonymize("mail person@example.com 192.168.1.1 12345") == "mail [EMAIL] [IP] [NUMBER]"


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame(),
        pd.DataFrame({"text": [None], "label": [0]}),
        pd.DataFrame({"text": [""], "label": [0]}),
    ],
)
def test_invalid_schema(frame):
    with pytest.raises(ValueError):
        validate_frame(frame)


def test_unavailable_and_missing(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    with pytest.raises(ValueError, match="unavailable"):
        download(tmp_path, client)
    with pytest.raises(ValueError, match="download-dataset"):
        load(tmp_path)
