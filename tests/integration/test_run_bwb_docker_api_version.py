"""
Verifies /run-bwb passes the host docker daemon's API version into both the
bwb_scheduler container itself (-e DOCKER_API_VERSION=<host version>) and to
bwbSched (--dockerVersion <host version>), since bwbSched also spawns
sibling docker containers of its own. Without this, a bundled docker client
newer than the host daemon fails with "client version X is too new. Maximum
supported API version is Y".
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
    # The -e flag must land before the image name, i.e. as a `docker run`
    # option, not as an argument passed to bwbSched itself.
    image_index = alignment_cmd.index("patrickmckeever/bwb_scheduler")
    assert alignment_cmd.index("-e DOCKER_API_VERSION=1.42") < image_index

    assert "--dockerVersion 1.42" in alignment_cmd
    # --dockerVersion is a bwbSched CLI arg, so it must land after the image
    # name/command, not be mistaken for a `docker run` option.
    assert alignment_cmd.index("--dockerVersion 1.42") > image_index


def test_alignment_cmd_omits_flags_when_version_undetectable(client, monkeypatch):
    monkeypatch.setattr(routes, "_detect_host_docker_api_version", lambda: None)

    alignment_cmd = _capture_alignment_cmd(client, monkeypatch)

    assert "DOCKER_API_VERSION" not in alignment_cmd
    assert "--dockerVersion" not in alignment_cmd
