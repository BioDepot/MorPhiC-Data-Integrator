import time

import pytest

from web.routes import JobManager

pytestmark = pytest.mark.unit


def _wait_for_terminal_status(manager, job_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = manager.get_status(job_id)["status"]
        if status in ("done", "canceled", "error"):
            return status
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach a terminal status in time")


def test_callable_steps_run_in_order_and_complete():
    manager = JobManager()
    calls = []

    job_id = manager.submit([
        {"type": "callable", "fn": lambda: calls.append(1)},
        {"type": "callable", "fn": lambda: calls.append(2)},
        {"type": "callable", "fn": lambda: calls.append(3)},
    ])

    status = _wait_for_terminal_status(manager, job_id)
    assert status == "done"
    assert calls == [1, 2, 3]


def test_failing_step_stops_later_steps_and_reports_error():
    manager = JobManager()
    calls = []

    def boom():
        raise RuntimeError("staging failed")

    job_id = manager.submit([
        {"type": "callable", "fn": lambda: calls.append("first")},
        {"type": "callable", "fn": boom},
        {"type": "callable", "fn": lambda: calls.append("never runs")},
    ])

    status = _wait_for_terminal_status(manager, job_id)
    assert status == "error"
    assert "staging failed" in manager.get_status(job_id)["result"]
    assert calls == ["first"]


def test_cmd_step_runs_via_shell():
    manager = JobManager()

    job_id = manager.submit([
        {"type": "cmd", "cmd": "echo hello-from-job"},
    ])

    status = _wait_for_terminal_status(manager, job_id)
    assert status == "done"
    assert manager.get_status(job_id)["result"].strip() == "hello-from-job"


def test_cmd_step_failure_reports_stderr():
    manager = JobManager()

    job_id = manager.submit([
        {"type": "cmd", "cmd": "echo boom-message 1>&2; exit 1"},
    ])

    status = _wait_for_terminal_status(manager, job_id)
    assert status == "error"
    assert "boom-message" in manager.get_status(job_id)["result"]


def test_multiple_docker_run_steps_get_unique_container_names_and_rm():
    # Regression test: a job that runs more than one "docker run ..." command
    # in sequence (e.g. the alignment scheduler, then the PCA container) used
    # to inject the *same* --name (job_id) into every step. Since none of the
    # commands pass --rm, the first (stopped but not removed) container kept
    # that name, so the second docker run --name failed with "container name
    # already in use". These commands use `echo` so the test doesn't require
    # a real docker installation -- only the --name/--rm string substitution
    # is under test.
    manager = JobManager()

    job_id = manager.submit([
        {"type": "cmd", "cmd": "echo docker run step-one"},
        {"type": "cmd", "cmd": "echo docker run step-two"},
    ])

    status = _wait_for_terminal_status(manager, job_id)
    assert status == "done"

    with manager.lock:
        cmds_run = list(manager.jobs[job_id]["cmds_run"])

    assert len(cmds_run) == 2
    assert all("--rm" in cmd for cmd in cmds_run)

    def container_name(cmd):
        return cmd.split("--name ", 1)[1].split(" ", 1)[0]

    names = [container_name(cmd) for cmd in cmds_run]
    assert len(set(names)) == 2
    assert all(name.startswith(f"{job_id}-") for name in names)


def test_error_result_includes_commands_run_for_debugging():
    manager = JobManager()

    job_id = manager.submit([
        {"type": "cmd", "cmd": "echo docker run ok-step"},
        {"type": "cmd", "cmd": "echo failing-step 1>&2; exit 1"},
    ])

    status = _wait_for_terminal_status(manager, job_id)
    assert status == "error"

    result = manager.get_status(job_id)["result"]
    assert "failing-step" in result
    assert "Commands run for this job:" in result
    assert "ok-step" in result
