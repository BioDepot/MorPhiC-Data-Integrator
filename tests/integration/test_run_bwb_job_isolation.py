"""
Verifies that each /run-bwb submission that needs the alignment workflow gets
its own paired/unpaired/output directories, so two runs (e.g. back-to-back,
or overlapping) never mix up each other's FASTQ inputs or workflow outputs.

JOB_MANAGER.submit is mocked so no docker/scheduler command actually runs;
this only exercises the synchronous request handling (uploaded FASTQ staging
and directory/command construction) in web/routes.py's /run-bwb.
"""
import io
import os
import re

import pytest

import web.routes as routes

pytestmark = pytest.mark.integration


def _post_single_sample(client, monkeypatch, sample_name, fastq_body):
    monkeypatch.setitem(routes.app.config, "WTF_CSRF_ENABLED", False)
    data = {
        "workflow": "star_salmon_short_yin",
        "samples[0][name]": sample_name,
        "samples[0][group]": "groupA",
        "samples[0][layout]": "SINGLE",
        "samples[0][r1]": (io.BytesIO(fastq_body), f"{sample_name}_upload.fastq.gz"),
    }
    return client.post("/run-bwb", data=data, content_type="multipart/form-data")


def test_two_runs_get_isolated_paired_unpaired_output_dirs(client, monkeypatch):
    captured_calls = []

    def fake_submit(steps, output_dir=None):
        captured_calls.append({"steps": steps, "output_dir": output_dir})
        return f"fake-job-{len(captured_calls)}"

    monkeypatch.setattr(routes.JOB_MANAGER, "submit", fake_submit)

    response1 = _post_single_sample(client, monkeypatch, "SAMPLEONE", b"run-one-bytes")
    assert response1.status_code == 200
    response2 = _post_single_sample(client, monkeypatch, "SAMPLETWO", b"run-two-bytes")
    assert response2.status_code == 200

    assert len(captured_calls) == 2
    output_dir_1 = captured_calls[0]["output_dir"]
    output_dir_2 = captured_calls[1]["output_dir"]

    # Job-scoped final output dirs must differ between runs.
    assert output_dir_1 != output_dir_2

    # The bwbSched alignment command (first "cmd" step) must reference
    # distinct, run-scoped paired/unpaired/output container paths.
    alignment_cmd_1 = next(s["cmd"] for s in captured_calls[0]["steps"] if s["type"] == "cmd")
    alignment_cmd_2 = next(s["cmd"] for s in captured_calls[1]["steps"] if s["type"] == "cmd")

    def extract_run_ids(cmd):
        return set(re.findall(r"/data/([0-9a-f-]{36})/", cmd))

    run_ids_1 = extract_run_ids(alignment_cmd_1)
    run_ids_2 = extract_run_ids(alignment_cmd_2)
    assert len(run_ids_1) == 1
    assert len(run_ids_2) == 1
    assert run_ids_1 != run_ids_2

    # Derive each run's host-side upload root from its final output_dir
    # (upload_root/processing/Tables) and confirm the staged FASTQ landed
    # only in that run's own paired dir, not the other run's.
    upload_root_1 = os.path.dirname(os.path.dirname(output_dir_1))
    upload_root_2 = os.path.dirname(os.path.dirname(output_dir_2))
    assert upload_root_1 != upload_root_2

    # samples[0][layout] is SINGLE, so the uploaded FASTQ is staged into the
    # unpaired dir.
    unpaired_1 = os.path.join(upload_root_1, "unpaired")
    unpaired_2 = os.path.join(upload_root_2, "unpaired")

    assert os.path.exists(os.path.join(unpaired_1, "SAMPLEONE_R1.fastq.gz"))
    assert not os.path.exists(os.path.join(unpaired_1, "SAMPLETWO_R1.fastq.gz"))

    assert os.path.exists(os.path.join(unpaired_2, "SAMPLETWO_R1.fastq.gz"))
    assert not os.path.exists(os.path.join(unpaired_2, "SAMPLEONE_R1.fastq.gz"))

    with open(os.path.join(unpaired_1, "SAMPLEONE_R1.fastq.gz"), "rb") as fh:
        assert fh.read() == b"run-one-bytes"
    with open(os.path.join(unpaired_2, "SAMPLETWO_R1.fastq.gz"), "rb") as fh:
        assert fh.read() == b"run-two-bytes"
