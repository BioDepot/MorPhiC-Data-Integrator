import subprocess

import pytest

from web.routes import _detect_host_docker_api_version

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_cache():
    # _detect_host_docker_api_version is lru_cache'd for the life of the
    # process; clear it around each test so mocks don't leak between tests.
    _detect_host_docker_api_version.cache_clear()
    yield
    _detect_host_docker_api_version.cache_clear()


def test_returns_stripped_daemon_api_version(mocker):
    mocker.patch(
        "web.routes.subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="1.42\n", stderr=""),
    )

    assert _detect_host_docker_api_version() == "1.42"


def test_returns_none_when_docker_cli_missing(mocker):
    mocker.patch("web.routes.subprocess.run", side_effect=FileNotFoundError("docker not found"))

    assert _detect_host_docker_api_version() is None


def test_returns_none_when_docker_command_fails(mocker):
    mocker.patch(
        "web.routes.subprocess.run",
        side_effect=subprocess.CalledProcessError(returncode=1, cmd=["docker"]),
    )

    assert _detect_host_docker_api_version() is None


def test_returns_none_on_timeout(mocker):
    mocker.patch(
        "web.routes.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["docker"], timeout=10),
    )

    assert _detect_host_docker_api_version() is None


def test_result_is_cached(mocker):
    run_mock = mocker.patch(
        "web.routes.subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="1.42\n", stderr=""),
    )

    assert _detect_host_docker_api_version() == "1.42"
    assert _detect_host_docker_api_version() == "1.42"
    assert run_mock.call_count == 1
