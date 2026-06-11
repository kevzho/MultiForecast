"""Daily World Cup refresh workflow entry point."""

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
        capture_output=True,
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
            stderr=result.stderr,
        )


def run_optional_step(label, cmd, cwd=PROJECT_ROOT):
    try:
        run_step(label, cmd, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(f"WARN: {label} failed: {e}")


def main():
    run_optional_step("Rebuild World Cup strengths", [PYTHON, "-m", "worldcup.strengths"])
    run_optional_step("Validate World Cup data", [PYTHON, "-m", "worldcup.data"])


if __name__ == "__main__":
    main()
