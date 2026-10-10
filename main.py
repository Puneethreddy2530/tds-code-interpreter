import os
import re
import subprocess
import sys
import tempfile
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

app = FastAPI(title="TDS Code Interpreter with AI Error Analysis")

# The assignment's browser-based tester needs CORS enabled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20000)


class CodeResponse(BaseModel):
    error: List[int]
    result: str


class ErrorAnalysis(BaseModel):
    error_lines: List[int]


@app.get("/")
def health_check():
    return {"status": "ok", "endpoint": "/code-interpreter"}


@app.get("/health")
def health():
    return {"status": "ok"}


def execute_python_code(code: str) -> dict:
    """Run a snippet and return stdout exactly on success, or its traceback on failure.

    This uses a child process and a timeout so an accidental infinite loop does not
    hold the API worker forever. It is still a classroom demo, not a secure sandbox.
    """
    # Keep the executed program from inheriting application secrets such as
    # GEMINI_API_KEY through its ordinary environment variables.
    child_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="tds-code-") as workdir:
            completed = subprocess.run(
                [sys.executable, "-I", "-c", code],
                cwd=workdir,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        if completed.returncode == 0:
            # stdout is returned unmodified (including its final newline).
            return {"success": True, "output": completed.stdout}
        # Python's traceback is normally emitted to stderr. Preserve it exactly.
        return {"success": False, "output": completed.stderr or completed.stdout}
    except subprocess.TimeoutExpired as exc:
        captured = exc.stderr or b""
        if isinstance(captured, bytes):
            captured = captured.decode("utf-8", errors="replace")
        message = "Traceback (most recent call last):\nTimeoutError: Python code execution exceeded 5 seconds"
        if captured:
            message = captured + "\n" + message
        return {"success": False, "output": message}
    except Exception as exc:
        return {
            "success": False,
            "output": f"Traceback (most recent call last):\n{type(exc).__name__}: {exc}",
        }


def fallback_error_lines(traceback_text: str, code: str) -> List[int]:
    """Extract code-frame line numbers if the model API is unavailable."""
    lines = set()
    for match in re.finditer(r'File "<string>", line (\d+)', traceback_text):
        lines.add(int(match.group(1)))
    # SyntaxError often reports its location in a different format.
    for match in re.finditer(r"<string>, line (\d+)", traceback_text):
        lines.add(int(match.group(1)))
    max_line = max(1, len(code.splitlines()))
    return sorted(line for line in lines if 1 <= line <= max_line)


def analyze_error_with_ai(code: str, traceback_text: str) -> List[int]:
    """Ask Gemini for 1-based line numbers from the submitted snippet only."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=api_key)
    prompt = f"""Identify the 1-based line number(s) in the user's submitted Python code that caused the error.
Return only line numbers belonging to the submitted snippet, not lines from the API server or Python runtime.
For example, for code `x = 10\\ny = 0\\nresult = x / y`, the answer is [3].
If the traceback has a `File <string>, line N` frame, use that frame as the primary evidence.

SUBMITTED PYTHON CODE:
{code}

TRACEBACK:
{traceback_text}
"""

    response = client.models.generate_content(
        model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ErrorAnalysis,
            temperature=0,
        ),
    )
    parsed = ErrorAnalysis.model_validate_json(response.text or "{}")
    max_line = max(1, len(code.splitlines()))
    return sorted({n for n in parsed.error_lines if 1 <= n <= max_line})


@app.post("/code-interpreter", response_model=CodeResponse)
def code_interpreter(request: CodeRequest):
    execution = execute_python_code(request.code)
    if execution["success"]:
        return CodeResponse(error=[], result=execution["output"])

    # Per assignment: invoke AI analysis only when execution fails.
    try:
        error_lines = analyze_error_with_ai(request.code, execution["output"])
    except Exception:
        # Keeps the endpoint usable if the model is briefly unavailable; the
        # traceback parser is only a fallback, not the primary analysis path.
        error_lines = fallback_error_lines(execution["output"], request.code)

    return CodeResponse(error=error_lines, result=execution["output"])
