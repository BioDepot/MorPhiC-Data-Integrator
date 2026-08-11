"""
Verifies /run-bwb passes -e DOCKER_API_VERSION=<host version> into the
bwb_scheduler container, so its bundled (often newer) docker client
negotiates down to whatever the host docker daemon actually supports instead
of failing with "client version X is too new. Maximum supported API version
is Y".
"""
import io

import pytest

import web.routes as routes

pytestmark = pytest.mark.integration


def _post_single_sample(client, monkeypatch):
    monkeypatch.setitem(routes.app.config, "WTF_CSRF_ENABLED", False)
    data = {
        "workflow": "star_salmon_short_yin",
        "samples[0][name]": "MYSAMPLE",
        "samples[0][group]": "groupA",
        "samples[0][layout]": "SINGLE",
        "samples[0][r1]": (io.BytesIO(b"fastq-bytes"), "sample.fastq.gz"),
    }
    return client.post("/run-bwb", data=data, content_type="multipart/form-data")


def _capture_alignment_cmd(client, monkeypatch):
    captured_steps = []
    monkeypatch.setattr(
        routes.JOB_MANAGER, "submit",
        lambda steps, output_dir=None: captured_steps.append(steps) or "fake-job",
    )

    response = _post_single_sample(client, monkeypatch)
    assert response.status_code == 200
    assert captured_steps

    steps = captured_steps[0]
    return next(s["cmd"] for s in steps if s["type"] == "cmd" and "bwb_scheduler" in s["cmd"])


def test_alignment_cmd_includes_detected_host_api_version(client, monkeypatch):
    monkeypatch.setattr(routes, "_detect_host_docker_api_version", lambda: "1.42")

    alignment_cmd = _capture_alignment_cmd(client, monkeypatch)

    assert "-e DOCKER_API_VERSION=1.42" in alignment_cmd
    # The flag must land before the image name, i.e. as a `docker run` option,
    # not as an argument passed to bwbSched itself.
    assert alignment_cmd.index("-e DOCKER_API_VERSION=1.42") < alignment_cmd.index("patrickmckeever/bwb_scheduler")


def test_alignment_cmd_omits_flag_when_version_undetectable(client, monkeypatch):
    monkeypatch.setattr(routes, "_detect_host_docker_api_version", lambda: None)

    alignment_cmd = _capture_alignment_cmd(client, monkeypatch)

    assert "DOCKER_API_VERSION" not in alignment_cmd
