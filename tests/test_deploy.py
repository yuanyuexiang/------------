"""Deployment orchestration: fail closed on migration errors and restore healthy releases."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "deploy.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
@pytest.mark.parametrize(
    "failure", ["", "pull", "migration", "health", "first-health", "startup", "homepage"]
)
def test_deploy_failure_boundaries(tmp_path, failure):
    root = tmp_path / "production"
    release = root / "releases" / "new"
    previous = root / "releases" / "old"
    for directory in (release, previous):
        directory.mkdir(parents=True)
        (directory / "release.env").write_text("JB_API_IMAGE=example:test\n")
        (directory / "compose.prod.yml").write_text("name: jinbang\n")
    (root / ".env").write_text("DEPLOY_DOMAIN=example.test\n")
    if failure not in ("first-health", "startup", "homepage"):
        (root / "current").symlink_to(previous)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "commands"
    # Fake external commands only; the actual deployment script and traps run unchanged.
    for name, body in {
        "flock": "exit 0\n",
        "docker": '''
printf '%s\\n' "$*" >> "$COMMAND_LOG"
case " $* " in
  *" pull "*) test "$FAILURE" != pull || exit 11 ;;
  *" upgrade head "*) test "$FAILURE" != migration || exit 12 ;;
  *" --wait-timeout 360 "*) test "$FAILURE" != startup || exit 13 ;;
  *" ps -aq "*) printf 'worker-container\\n' ;;
esac
exit 0
''',
        "curl": '''
printf 'curl %s\\n' "$*" >> "$COMMAND_LOG"
case "$FAILURE" in health|first-health) exit 22 ;; esac
case "$*" in
  *"https://example.test/" ) test "$FAILURE" != homepage || exit 28 ;;
esac
exit 0
''',
    }.items():
        executable = bindir / name
        executable.write_text("#!/bin/sh\n" + body)
        executable.chmod(0o755)
    result = subprocess.run(
        ["bash", str(SCRIPT), str(release)],
        env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}",
             "COMMAND_LOG": str(log), "FAILURE": failure},
        capture_output=True, text=True,
    )
    commands = log.read_text()
    assert (result.returncode == 0) == (failure == ""), result.stderr
    if not failure:
        assert (root / "current").resolve() == release
        assert (root / "previous").resolve() == previous
        assert commands.index("pg_dump") < commands.index("upgrade head")
        assert commands.index("upgrade head") < commands.index("curl")
        probes = [line for line in commands.splitlines() if line.startswith("curl ")]
        assert len(probes) == 2
        for probe in probes:
            assert "--retry-all-errors" in probe
            assert "--retry-max-time 300" in probe
            assert "--insecure" not in probe
        assert "Passed https-api" in result.stdout
        assert "Passed https-homepage" in result.stdout
    elif failure in ("first-health", "startup", "homepage"):
        assert not (root / "current").exists()
        assert "stop jb-web jb-worker jb-api" in commands
        assert "worker-container" in commands
        assert commands.index("inspect --format") < commands.index("stop jb-web")
        if failure == "startup":
            assert "curl" not in commands
        elif failure == "homepage":
            assert "Passed https-api" in result.stdout
            assert "Passed https-homepage" not in result.stdout
            assert "step=https-homepage, exit=28" in result.stderr
    else:
        assert (root / "current").resolve() == previous
        if failure == "pull":
            assert "stop jb-worker jb-api" not in commands
        elif failure == "migration":
            assert "curl" not in commands
            assert str(previous / "compose.prod.yml") not in commands
        elif failure == "health":
            assert str(previous / "compose.prod.yml") in commands
            assert "Restoring previous application images" in result.stderr
