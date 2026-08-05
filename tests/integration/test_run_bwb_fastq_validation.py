"""
Verifies /run-bwb rejects uploaded FASTQ files that aren't gzip-compressed
(.fastq.gz / .fq.gz), and that an accepted .fq.gz upload still gets staged
under a normalized .fastq.gz basename.
"""
import io
import os

import pytest

import web.routes as routes

pytestmark = pytest.mark.integration


def _post_single_sample(client, monkeypatch, filename, fastq_body=b"fastq-bytes"):
    monkeypatch.setitem(routes.app.config, "WTF_CSRF_ENABLED", False)
    data = {
        "workflow": "star_salmon_short_yin",
        "samples[0][name]": "MYSAMPLE",
        "samples[0][group]": "groupA",
        "samples[0][layout]": "SINGLE",
        "samples[0][r1]": (io.BytesIO(fastq_body), filename),
    }
    return client.post("/run-bwb", data=data, content_type="multipart/form-data")


def test_rejects_plain_fastq_upload(client, monkeypatch):
    called = []
    monkeypatch.setattr(routes.JOB_MANAGER, "submit", lambda *a, **k: called.append(1))

    response = _post_single_sample(client, monkeypatch, "sample.fastq")

    # The invalid extension is caught before a job is ever submitted (dash.html
    # doesn't currently render form.workflow.errors, so this is the behavior
    # actually observable from the response).
    assert response.status_code == 200
    assert not called


def test_accepts_fq_gz_and_normalizes_saved_name(client, monkeypatch):
    captured = []
    monkeypatch.setattr(
        routes.JOB_MANAGER, "submit",
        lambda steps, output_dir=None: captured.append(output_dir) or "fake-job",
    )

    response = _post_single_sample(client, monkeypatch, "sample.fq.gz", b"gzipped-bytes")

    assert response.status_code == 200
    assert captured

    output_dir = captured[0]
    upload_root = os.path.dirname(os.path.dirname(output_dir))
    saved_path = os.path.join(upload_root, "unpaired", "MYSAMPLE_R1.fastq.gz")
    assert os.path.exists(saved_path)
    with open(saved_path, "rb") as fh:
        assert fh.read() == b"gzipped-bytes"
