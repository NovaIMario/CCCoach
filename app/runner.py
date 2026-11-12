"""Compile and run user code (C++ or Python) against custom input.

This runs untrusted code, so it is limited in several ways:
  - each run gets its own temporary directory, deleted afterwards
  - a wall-clock timeout (2s run, 15s compile)
  - on Linux: CPU time, memory, file size and process count limits (setrlimit)
  - a minimal environment (no secrets such as GEMINI_API_KEY are passed in)
  - output is cut at 64 KB

It is NOT a full sandbox (the process can still read world-readable files and use
the network). For a public deployment, run the app in the provided Docker image
as a non-root user, or set ENABLE_CODE_RUNNER=0.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

RUN_TIMEOUT = 2.0
COMPILE_TIMEOUT = 15.0
MEMORY_BYTES = 256 * 1024 * 1024
MAX_OUTPUT = 64 * 1024
MAX_CODE = 100 * 1024

LANGUAGES = ("cpp", "python")


@dataclass
class RunResult:
    status: str          # "ok", "compile_error", "runtime_error", "time_limit", "error"
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None

    def to_dict(self):
        return self.__dict__


def _limits():  # runs in the child process, Linux only
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (int(RUN_TIMEOUT) + 1, int(RUN_TIMEOUT) + 1))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT * 16, MAX_OUTPUT * 16))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))  # stops fork bombs
    os.setsid()


def _clean_env(workdir: str) -> dict:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": workdir, "TMPDIR": workdir, "LANG": "C.UTF-8"}
    if os.name == "nt":  # Windows needs these to start processes at all
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        env["TEMP"] = env["TMP"] = workdir
    return env


def _truncate(s: str) -> str:
    return s if len(s) <= MAX_OUTPUT else s[:MAX_OUTPUT] + "\n... output truncated ..."


def run_code(language: str, code: str, stdin: str = "") -> RunResult:
    if language not in LANGUAGES:
        return RunResult("error", stderr=f"Unsupported language: {language}")
    if len(code) > MAX_CODE:
        return RunResult("error", stderr="Code is too long (limit 100 KB)")

    workdir = tempfile.mkdtemp(prefix="cccoach-")
    env = _clean_env(workdir)
    preexec = _limits if sys.platform.startswith("linux") else None
    try:
        if language == "cpp":
            src = os.path.join(workdir, "main.cpp")
            exe = os.path.join(workdir, "main.exe" if os.name == "nt" else "main")
            with open(src, "w", encoding="utf-8") as f:
                f.write(code)
            try:
                comp = subprocess.run(["g++", "-O2", "-std=c++17", src, "-o", exe], capture_output=True,
                                      text=True, timeout=COMPILE_TIMEOUT, cwd=workdir, env=env)
            except FileNotFoundError:
                return RunResult("error", stderr="g++ is not installed on the server")
            except subprocess.TimeoutExpired:
                return RunResult("compile_error", stderr="Compilation took too long")
            if comp.returncode != 0:
                return RunResult("compile_error", stderr=_truncate(comp.stderr))
            cmd = [exe]
        else:
            src = os.path.join(workdir, "main.py")
            with open(src, "w", encoding="utf-8") as f:
                f.write(code)
            cmd = [sys.executable, "-I", src]  # -I: ignore env vars and user site-packages

        try:
            proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=RUN_TIMEOUT,
                                  cwd=workdir, env=env, preexec_fn=preexec)
        except subprocess.TimeoutExpired:
            return RunResult("time_limit", stderr=f"Time limit exceeded ({RUN_TIMEOUT:g}s)")
        status = "ok" if proc.returncode == 0 else "runtime_error"
        return RunResult(status, _truncate(proc.stdout), _truncate(proc.stderr), proc.returncode)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
