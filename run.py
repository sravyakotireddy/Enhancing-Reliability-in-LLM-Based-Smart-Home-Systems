#!/usr/bin/env python3
"""
Start the Smart Home dashboard stack for local development.

Runs the FastAPI backend (port 8000) and the Vite frontend (port 5173) together.
Use one terminal; press Ctrl+C to stop both servers.

Usage (from the project root):
  python run.py

Prerequisites:
  - Python 3.10+ with project deps: pip install -r requirements.txt
  - Node.js + npm with frontend deps: cd frontend && npm install
  - Optional: .env in project root with OPENAI_API_KEY for LLM features
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_DIR = ROOT / "frontend"


def _which_npm() -> str | None:
    return shutil.which("npm")


def _run_backend(host: str, port: int, reload: bool) -> subprocess.Popen:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")
    return subprocess.Popen(
        cmd,
        cwd=ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


def _run_frontend() -> subprocess.Popen:
    npm = _which_npm()
    if not npm:
        print("ERROR: npm not found. Install Node.js from https://nodejs.org/", file=sys.stderr)
        sys.exit(1)
    if not (FRONTEND_DIR / "package.json").is_file():
        print(f"ERROR: missing {FRONTEND_DIR / 'package.json'}", file=sys.stderr)
        sys.exit(1)
    return subprocess.Popen(
        [npm, "run", "dev"],
        cwd=FRONTEND_DIR,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        shell=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Smart Home API + dashboard frontend.")
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Only start FastAPI (no npm).",
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="Only start Vite (no uvicorn).",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable uvicorn --reload (slightly faster startup).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=BACKEND_PORT,
        metavar="N",
        help=f"Backend port (default: {BACKEND_PORT}).",
    )
    args = parser.parse_args()

    if args.backend_only and args.frontend_only:
        print("ERROR: use at most one of --backend-only / --frontend-only", file=sys.stderr)
        sys.exit(1)

    os.chdir(ROOT)

    procs: list[subprocess.Popen] = []

    def shutdown(_signum=None, _frame=None) -> None:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        deadline = time.monotonic() + 3.0
        for p in procs:
            while p.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
        for p in procs:
            if p.poll() is None:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    labels: list[str] = []
    if not args.frontend_only:
        procs.append(
            _run_backend(BACKEND_HOST, args.port, reload=not args.no_reload)
        )
        labels.append("backend")
    if not args.backend_only:
        procs.append(_run_frontend())
        labels.append("frontend")

    if not args.frontend_only:
        print(f"Backend:  http://{BACKEND_HOST}:{args.port}")
    if not args.backend_only:
        print("Frontend: http://127.0.0.1:5173  (see Vite output if the port differs)")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            for i, p in enumerate(procs):
                code = p.poll()
                if code is not None:
                    label = labels[i] if i < len(labels) else "process"
                    print(f"\n{label} exited with code {code}. Stopping others.", file=sys.stderr)
                    shutdown()
                    return
            time.sleep(0.25)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
