"""Execution utilities for ISCE2 alos2App.py."""

from __future__ import annotations

from pathlib import Path
import subprocess

from .constants import ALOS2APP_STEPS


def validate_alos2_steps(start_step: str | None = None, end_step: str | None = None) -> None:
    """Validate requested alos2App.py start and end steps."""
    if start_step is not None and start_step not in ALOS2APP_STEPS:
        raise ValueError(f"Invalid start_step: {start_step}\nValid steps are: {ALOS2APP_STEPS}")

    if end_step is not None and end_step not in ALOS2APP_STEPS:
        raise ValueError(f"Invalid end_step: {end_step}\nValid steps are: {ALOS2APP_STEPS}")

    if start_step is not None and end_step is not None:
        if ALOS2APP_STEPS.index(start_step) > ALOS2APP_STEPS.index(end_step):
            raise ValueError(f"start_step must occur before end_step: {start_step} > {end_step}")


def run_isce2_alos2app(
    xml_file,
    work_dir,
    alos2app_cmd="alos2App.py",
    start_step=None,
    end_step=None,
    log_file=None,
    steps=True,
) -> subprocess.CompletedProcess:
    """Run ``alos2App.py`` and stream terminal output to a log file."""
    xml_file = Path(xml_file).resolve()
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    validate_alos2_steps(start_step, end_step)

    cmd = [alos2app_cmd, str(xml_file)]

    if steps:
        cmd.append("--steps")

    if start_step is not None:
        cmd.append(f"--start={start_step}")

    if end_step is not None:
        cmd.append(f"--end={end_step}")

    if log_file is None:
        log_file = work_dir / "alos2App_full_terminal.log"
    else:
        log_file = Path(log_file).resolve()

    print("Running:")
    print(" ".join(cmd))
    print(f"Working directory: {work_dir}")
    print(f"Log file: {log_file}")

    with open(log_file, "w", encoding="utf-8", errors="replace") as log:
        log.write("Running:\n")
        log.write(" ".join(cmd) + "\n")
        log.write(f"Working directory: {work_dir}\n\n")
        log.flush()

        process = subprocess.Popen(
            cmd,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

        full_output = []

        if process.stdout is not None:
            for line in process.stdout:
                print(line, end="")
                log.write(line)
                log.flush()
                full_output.append(line)

        return_code = process.wait()

    stdout_text = "".join(full_output)

    if return_code != 0:
        raise subprocess.CalledProcessError(
            return_code,
            cmd,
            output=stdout_text,
            stderr=None,
        )

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=return_code,
        stdout=stdout_text,
        stderr=None,
    )
