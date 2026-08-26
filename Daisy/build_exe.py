"""
build_exe.py
Automated build script for Daisy — Standalone Windows Executable (.exe)
Uses PyInstaller and Daisy.spec to bundle all animations, fonts, and dependencies.

Usage:
    python build_exe.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
SPEC_FILE = BASE_DIR / "Daisy.spec"
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
EXE_TARGET = DIST_DIR / "Daisy.exe"


def clean_previous_builds():
    """Removes previous build and dist artifacts."""
    print("[1/3] Cleaning previous build artifacts...")
    for folder in [DIST_DIR, BUILD_DIR]:
        if folder.exists():
            try:
                shutil.rmtree(folder)
                print(f"      Removed {folder.name}/")
            except Exception as exc:
                print(f"      Warning: could not delete {folder.name}: {exc}")


def build_executable():
    """Runs PyInstaller with Daisy.spec."""
    print("[2/3] Compiling Daisy.exe with PyInstaller...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(SPEC_FILE),
    ]
    print(f"      Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        print(f"[!] Build failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def verify_build():
    """Verifies that the compiled Daisy.exe exists and is valid."""
    print("[3/3] Verifying generated executable...")
    if not EXE_TARGET.exists():
        print(f"[!] Error: Expected output not found at {EXE_TARGET}")
        sys.exit(1)

    size_mb = EXE_TARGET.stat().st_size / (1024 * 1024)
    print(f"\n[+] Build successful!")
    print(f"    Output: {EXE_TARGET}")
    print(f"    Size:   {size_mb:.2f} MB")
    print("\nYou can now run Daisy.exe directly on any Windows machine.")


if __name__ == "__main__":
    clean_previous_builds()
    build_executable()
    verify_build()
