import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_the_worker_started_as_docker_starts_it_has_its_handlers() -> None:
    """Regression: `python -m app.worker` once ran with no handlers at all,
    because app/jobs.py registered them on a different copy of the module."""
    result = subprocess.run(
        [sys.executable, "-m", "app.worker", "--list-handlers"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    handlers = result.stdout.split()
    assert "sms.send" in handlers
    assert "reminders.daily" in handlers
