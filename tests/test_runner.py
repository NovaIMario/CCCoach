import shutil

import pytest

from app.runner import run_code

needs_gpp = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not installed")


def test_python_echo():
    r = run_code("python", "print(int(input()) * 2)", "21\n")
    assert r.status == "ok" and r.stdout.strip() == "42"


def test_python_runtime_error():
    r = run_code("python", "raise SystemExit(3)")
    assert r.status == "runtime_error" and r.exit_code == 3


def test_python_time_limit():
    r = run_code("python", "while True: pass")
    assert r.status == "time_limit"


def test_secrets_are_not_passed_to_user_code(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value")
    r = run_code("python", "import os; print(os.environ.get('GEMINI_API_KEY'))")
    assert r.stdout.strip() == "None"


def test_unknown_language():
    assert run_code("brainfuck", "+").status == "error"


@needs_gpp
def test_cpp_compile_and_run():
    code = "#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b;}"
    r = run_code("cpp", code, "2 3")
    assert r.status == "ok" and r.stdout.strip() == "5"


@needs_gpp
def test_cpp_compile_error():
    assert run_code("cpp", "int main( {").status == "compile_error"
