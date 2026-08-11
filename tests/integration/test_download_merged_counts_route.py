import pytest

import web.routes as routes

pytestmark = pytest.mark.integration


def test_download_merged_counts_route(client):
    response = client.get("/download-merged-counts")

    assert response.status_code == 200
    assert response.mimetype == "text/tab-separated-values"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "mergedCounts.tsv" in response.headers["Content-Disposition"]


def test_download_merged_counts_404_when_file_missing(client, monkeypatch):
    merged_counts_path = routes.os.path.abspath("mergedCounts.tsv")
    real_exists = routes.os.path.exists
    monkeypatch.setattr(
        routes.os.path, "exists",
        lambda path: False if path == merged_counts_path else real_exists(path),
    )

    response = client.get("/download-merged-counts")

    assert response.status_code == 404
