#!/usr/bin/env python3
"""Build JENNY executables.

Produces two .exe files in ./dist/:
  JENNY.exe       - Keyless (user inputs API key or uses external LLM)
  JENNY_keyed.exe - API key embedded (reads from .env)

Requirements:
  pip install pyinstaller
  cd frontend && npm install  (if not done already)
"""

import os, sys, subprocess, shutil, re
from pathlib import Path

ROOT = Path(__file__).parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
BACKEND_PY = BACKEND / "jenny_backend.py"
SPEC_FILE = ROOT / "jenny.spec"
DIST_DIR = ROOT / "dist"
ENV_FILE = ROOT / ".env"

SENTINEL = 'EMBEDDED_API_KEY = None'


def run(cmd, cwd=None):
    print(f"  > {cmd}")
    r = subprocess.run(cmd, shell=True, cwd=cwd)
    if r.returncode != 0:
        print(f"  FAILED (exit {r.returncode})")
        sys.exit(1)


def build_frontend():
    print("\n[1/3] Building frontend...")
    if not (FRONTEND / "node_modules").exists():
        run("npm install", cwd=FRONTEND)
    run("npm run build", cwd=FRONTEND)
    dist = FRONTEND / "dist"
    if not (dist / "index.html").exists():
        print("  ERROR: frontend/dist/index.html not found after build")
        sys.exit(1)

    # Remove the dev-mode API_BASE override from the built index.html
    # (in production, API_BASE defaults to "" which means same-origin)
    index_html = dist / "index.html"
    content = index_html.read_text(encoding="utf-8")
    content = content.replace(
        '<script>window.JENNY_API_BASE = "http://localhost:5000";</script>\n    ', ''
    )
    index_html.write_text(content, encoding="utf-8")
    print("  Frontend built and patched.")


def build_exe(name, api_key=None):
    print(f"\n[building] {name}.exe ...")
    original = BACKEND_PY.read_text(encoding="utf-8")

    try:
        if api_key:
            patched = original.replace(SENTINEL, f'EMBEDDED_API_KEY = "{api_key}"')
            BACKEND_PY.write_text(patched, encoding="utf-8")

        env = os.environ.copy()
        env["JENNY_EXE_NAME"] = name
        r = subprocess.run(
            [sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm"],
            env=env, cwd=ROOT,
        )
        if r.returncode != 0:
            print(f"  PyInstaller failed for {name}")
            sys.exit(1)
    finally:
        # Always restore original
        BACKEND_PY.write_text(original, encoding="utf-8")

    print(f"  {name}.exe ready in dist/")


def read_api_key():
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main():
    print("=" * 50)
    print("JENNY Executable Builder")
    print("=" * 50)

    # Step 1: Build frontend
    build_frontend()

    # Step 2: Keyless build
    print("\n[2/3] Building keyless executable...")
    build_exe("JENNY")

    # Step 3: Keyed build
    print("\n[3/3] Building keyed executable...")
    api_key = read_api_key()
    if api_key:
        build_exe("JENNY_keyed", api_key=api_key)
    else:
        print("  WARNING: No .env file or ANTHROPIC_API_KEY not found.")
        print("  Skipping keyed build. Create .env with ANTHROPIC_API_KEY=sk-ant-... to enable.")

    print("\n" + "=" * 50)
    print("Build complete!")
    if (DIST_DIR / "JENNY.exe").exists():
        print(f"  Keyless: {DIST_DIR / 'JENNY.exe'}")
    if (DIST_DIR / "JENNY_keyed.exe").exists():
        print(f"  Keyed:   {DIST_DIR / 'JENNY_keyed.exe'}")
    print("=" * 50)


if __name__ == "__main__":
    main()
