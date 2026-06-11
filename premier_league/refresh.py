from premier_league.engine.config import SEASON
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run_step(label, cmd, cwd=PROJECT_ROOT):
    print(f"\n=== {label} ===")
    print(" ".join(cmd))

    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        if result.stderr:
            print(result.stderr)
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr
        )


def run_optional_step(label, cmd, cwd=PROJECT_ROOT):
    try:
        run_step(label, cmd, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(f"WARN: {label} failed: {e}")


def delete_sim_cache():
    cache_dir = PROJECT_ROOT / "cache"
    if not cache_dir.exists():
        return

    for path in cache_dir.glob(f"simulations_{SEASON}*.json"):
        path.unlink()
        print(f"Deleted cache file: {path}")


def main(launch_app=False):
    run_optional_step("Fetch latest data", [PYTHON, "-m", "premier_league.engine.fetch_data"])
    run_step("Rebuild Elo ratings", [PYTHON, "-m", "premier_league.engine.elo_run"])
    run_optional_step("Refresh remaining fixtures", [PYTHON, "-m", "premier_league.engine.remaining_fixtures"])
    run_step("Build summary table", [PYTHON, "-m", "premier_league.engine.table"])

    delete_sim_cache()

    run_step("Run simulation pipeline", [PYTHON, "-m", "premier_league.run"])

    if launch_app:
        run_step("Launch app", [PYTHON, "-m", "streamlit", "run", "app.py"])


if __name__ == "__main__":
    launch = "--launch-app" in sys.argv
    main(launch_app=launch)
