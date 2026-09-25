"""Build, verify and package WinFixAI.exe.

Run with the Windows Python that has the project's requirements plus
PyInstaller and pytest installed (``scripts/build_windows.ps1`` sets that up):

    python scripts/build.py                  # full build, tests and self-test
    python scripts/build.py --skip-tests     # don't run pytest
    python scripts/build.py --skip-self-test # don't launch the packaged exe

Produces, in ``dist/``:

    WinFixAI.exe        the application (single file, windowed)
    WinFixAI.zip        exe + README + LICENSE + THIRD-PARTY-NOTICES
    WinFixAI.sha256     SHA-256 of the exe and the zip (sha256sum format)
    build_report.txt    versions, metadata, bundled-content and secret checks
    test_report.txt     pytest results and the packaged exe's self-test

PyInstaller cannot cross-compile: this must run on Windows (or Wine).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
EXE = DIST / "WinFixAI.exe"
ZIP = DIST / "WinFixAI.zip"
SHA = DIST / "WinFixAI.sha256"
SPEC = ROOT / "WinFixAI.spec"
NOTICES = BUILD / "THIRD-PARTY-NOTICES.txt"

# Distributions that end up inside the executable.
RUNTIME_DISTS = [
    "PySide6_Essentials", "shiboken6", "psutil", "pydantic", "pydantic_core",
    "pydantic-settings", "python-dotenv", "typing_extensions", "typing-inspection",
    "annotated-types", "httpx", "httpcore", "h11", "anyio", "idna", "certifi", "sniffio",
    "keyring", "pywin32-ctypes", "jaraco.classes", "jaraco.functools", "jaraco.context",
    "more-itertools", "importlib_metadata", "zipp",
    "anthropic", "httpx2", "jiter", "docstring_parser",
]
# Anything matching these must never be inside the executable.
FORBIDDEN_BUNDLED = [r"(^|[\\/])\.env$", r"\.db$", r"\.db-wal$", r"settings\.json$",
                     r"(^|[\\/])tests?[\\/]", r"(^|[\\/])logs[\\/]", r"\.log$",
                     r"(^|[\\/])\.venv[\\/]", r"test_report", r"self_test"]
FORBIDDEN_MODULES = {"tests", "pytest", "_pytest", "fastapi", "uvicorn", "dotenv_secrets"}
SECRET_PATTERNS = [
    re.compile(rb"sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"),
    # (?<![A-Za-z]) skips identifiers such as the manifest's publicKeyToken.
    re.compile(rb"(?i)(?<![A-Za-z])(?:api[_-]?key|secret|token)\s*[:=]\s*['\"]"
               rb"[A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"ghp_[A-Za-z0-9]{36}"),
]


def log(message: str) -> None:
    print(message, flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- checks -------------------------------------------------------------------------
def app_version() -> str:
    text = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def check_versions(version: str) -> list[str]:
    problems = []
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if f'version = "{version}"' not in pyproject:
        problems.append("pyproject.toml version differs from app.__version__")
    info = (ROOT / "scripts" / "file_version_info.txt").read_text(encoding="utf-8")
    if f"'FileVersion', '{version}.0'" not in info:
        problems.append("file_version_info.txt FileVersion differs from app.__version__")
    return problems


def scan_source_for_secrets() -> list[str]:
    """No keys in the code that gets bundled, and no .env inside the package."""
    findings = []
    for path in (ROOT / "app").rglob("*"):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        if path.name == ".env" or path.suffix in (".db", ".log"):
            findings.append(f"{path.relative_to(ROOT)}: must not be inside app/")
            continue
        if path.suffix not in (".py", ".json", ".txt", ".toml", ".svg"):
            continue
        data = path.read_bytes()
        for pattern in SECRET_PATTERNS:
            if pattern.search(data):
                findings.append(f"{path.relative_to(ROOT)}: looks like a secret")
    return findings


# --- third-party notices -------------------------------------------------------------
def _license_texts(dist: md.Distribution) -> list[str]:
    texts = []
    for file in dist.files or []:
        name = file.name.upper()
        if any(key in name for key in ("LICENSE", "LICENCE", "COPYING", "NOTICE")) and \
                not name.endswith((".PY", ".PYC")):
            try:
                raw = Path(file.locate()).read_bytes()
            except OSError:
                continue
            texts.append(raw.decode("utf-8", errors="replace").strip())
    return texts


def write_notices() -> list[str]:
    BUILD.mkdir(exist_ok=True)
    parts = [
        "WinFix AI - third-party software notices",
        "=" * 44,
        "",
        "WinFixAI.exe bundles the following open-source components. Each is used under",
        "its own license, reproduced below.",
        "",
        "Qt for Python (PySide6) and Qt are licensed under the GNU Lesser General Public",
        "License v3 (LGPL-3.0). Their source code is available from",
        "https://code.qt.io and https://download.qt.io/official_releases/QtForPython/.",
        "You may replace the bundled Qt/PySide6 libraries: build WinFix AI from its",
        "source code (see README.md) against your own copy of PySide6.",
        "",
    ]
    listed = []
    for name in RUNTIME_DISTS:
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            continue
        meta = dist.metadata
        license_name = meta.get("License-Expression") or meta.get("License") or ""
        if len(license_name) > 80:
            license_name = license_name.splitlines()[0][:80]
        listed.append(f"{meta['Name']} {dist.version}")
        parts += ["-" * 78, f"{meta['Name']} {dist.version}",
                  f"License: {license_name or 'see below'}",
                  f"Home: {meta.get('Home-page') or meta.get('Project-URL') or ''}", ""]
        texts = _license_texts(dist)
        parts += texts[:2] if texts else ["(License text not shipped with the package.)"]
        parts.append("")
    icons = ROOT / "app" / "gui" / "assets" / "icons" / "LICENSE.txt"
    parts += ["-" * 78, "Fluent UI System Icons (Microsoft Corporation)", "License: MIT", "",
              icons.read_text(encoding="utf-8").strip(), ""]
    parts += ["-" * 78, f"Python {platform.python_version()}",
              "License: Python Software Foundation License", "https://docs.python.org/3/license.html", ""]
    NOTICES.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return listed


# --- build ---------------------------------------------------------------------------
def run_pyinstaller() -> None:
    for folder in (BUILD / "WinFixAI", DIST):
        shutil.rmtree(folder, ignore_errors=True)
    DIST.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean",
           "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller")]
    log("Running: " + " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)
    if not EXE.exists():
        raise SystemExit(f"PyInstaller finished but {EXE} is missing")


def bundled_files() -> list[str]:
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(EXE))
    names = list(reader.toc.keys())
    try:  # the PYZ holds the Python modules
        pyz = reader.open_embedded_archive("PYZ.pyz")
        names += [f"PYZ:{n}" for n in pyz.toc.keys()]
    except Exception:  # noqa: BLE001 - reader API differs between versions
        pass
    return names


def exe_metadata() -> dict:
    import pefile

    pe = pefile.PE(str(EXE), fast_load=True)
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
    info = {}
    for entry in getattr(pe, "FileInfo", []) or []:
        for item in entry:
            for table in getattr(item, "StringTable", []) or []:
                for key, value in table.entries.items():
                    info[key.decode()] = value.decode()
    icons = 0
    for res in getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None).entries if \
            hasattr(pe, "DIRECTORY_ENTRY_RESOURCE") else []:
        if res.id == pefile.RESOURCE_TYPE["RT_GROUP_ICON"]:
            icons = len(res.directory.entries)
    info["_icon_groups"] = icons
    info["_subsystem"] = "Windows GUI" if pe.OPTIONAL_HEADER.Subsystem == 2 else \
        f"other ({pe.OPTIONAL_HEADER.Subsystem})"
    info["_machine"] = hex(pe.FILE_HEADER.Machine)
    pe.close()
    return info


def scan_exe_for_secrets() -> list[str]:
    data = EXE.read_bytes()
    hits = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(data):
            hits.append(match.group(0)[:12].decode(errors="replace") + "...")
    return hits


# --- tests ------------------------------------------------------------------------------
def run_pytest() -> tuple[int, str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
                           "-o", "addopts=", "-rfEs", "--tb=short", "tests"],
                          cwd=ROOT, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout + proc.stderr


def run_self_test(timeout: int) -> tuple[int, str, float]:
    out = BUILD / "self_test"
    shutil.rmtree(out, ignore_errors=True)
    report = out / "self_test_report.txt"
    start = time.monotonic()
    try:
        proc = subprocess.run([str(EXE), "--self-test", "--report", str(report),
                               "--screenshots", str(out / "screenshots")],
                              cwd=DIST, timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code = -1
    elapsed = time.monotonic() - start
    text = report.read_text(encoding="utf-8") if report.exists() else \
        "The packaged executable did not write a self-test report."
    return code, text, elapsed


# --- package -----------------------------------------------------------------------------
QUICK_START = """WinFix AI {version}
=================

Troubleshoot Windows problems with evidence, not guesswork.

Run
---
Double-click WinFixAI.exe. No installation or Python needed.
Windows 10 (1809 or later) or Windows 11, 64-bit.

Windows SmartScreen may say "Windows protected your PC" because this build is
not code-signed. Choose "More info" and then "Run anyway" if you trust the
source. Check the file first: its SHA-256 must match WinFixAI.sha256.

    Get-FileHash .\\WinFixAI.exe -Algorithm SHA256

What it does
------------
* Runs read-only checks to find the likely cause of a problem.
* Proposes a fix from a fixed list of reviewed actions. Nothing changes until
  you approve it. Some fixes ask for administrator permission (UAC).
* Measures again afterwards to show whether the problem is resolved.

Your data
---------
History, settings and logs: %LOCALAPPDATA%\\WinFixAI
API keys (only if you turn on cloud analysis): Windows Credential Manager
Nothing leaves your PC unless you turn on cloud analysis in Settings.

Options
-------
WinFixAI.exe --demo        Sample data and simulated fixes. Changes nothing.
WinFixAI.exe --self-test   Checks every page in demo mode and writes a report.
WinFixAI.exe --version

Uninstall: delete WinFixAI.exe and the %LOCALAPPDATA%\\WinFixAI folder. If you
turned on "Start with Windows", turn it off in Settings first.
"""


def make_zip(version: str) -> list[str]:
    ZIP.unlink(missing_ok=True)
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    entries = {
        "WinFixAI/WinFixAI.exe": EXE.read_bytes(),
        "WinFixAI/README.txt": QUICK_START.format(version=version).replace("\n", "\r\n"),
        "WinFixAI/LICENSE.txt": license_text.replace("\n", "\r\n"),
        "WinFixAI/THIRD-PARTY-NOTICES.txt": NOTICES.read_text(encoding="utf-8")
        .replace("\n", "\r\n"),
    }
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return list(entries)


# --- main -------------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-self-test", action="store_true")
    parser.add_argument("--self-test-timeout", type=int, default=600)
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    version = app_version()
    log(f"WinFix AI {version} - build started {started:%Y-%m-%d %H:%M:%S} UTC")
    if platform.system() != "Windows":
        log("PyInstaller cannot cross-compile; run this with a Windows Python.")
        return 1

    problems = check_versions(version)
    source_secrets = scan_source_for_secrets()
    if problems or source_secrets:
        for item in problems + source_secrets:
            log(f"ERROR: {item}")
        return 1
    listed = write_notices()
    log(f"Third-party notices: {len(listed)} packages")

    tests_code, tests_output = (None, "Skipped (--skip-tests).")
    if not args.skip_tests:
        log("Running tests...")
        tests_code, tests_output = run_pytest()
        log(tests_output.strip().splitlines()[-1] if tests_output.strip() else "no output")

    run_pyinstaller()
    files = bundled_files()
    data_files = [f for f in files if not f.startswith("PYZ:")]
    modules = [f[4:] for f in files if f.startswith("PYZ:")]
    forbidden = sorted({f for f in data_files for pattern in FORBIDDEN_BUNDLED
                        if re.search(pattern, f, re.IGNORECASE)})
    forbidden += sorted(m for m in modules
                        if m.split(".")[0] in FORBIDDEN_MODULES or m.startswith("app.api"))
    exe_secrets = scan_exe_for_secrets()
    meta = exe_metadata()
    expected = {"ProductName": "WinFix AI", "CompanyName": "WinFix AI",
                "FileVersion": f"{version}.0", "ProductVersion": f"{version}.0",
                "OriginalFilename": "WinFixAI.exe"}
    meta_problems = [f"{k} is {meta.get(k)!r}, expected {v!r}"
                     for k, v in expected.items() if meta.get(k) != v]
    if not meta.get("_icon_groups"):
        meta_problems.append("no icon resource")

    self_code, self_text, self_seconds = (None, "Skipped (--skip-self-test).", 0.0)
    if not args.skip_self_test:
        log("Launching the packaged executable for its self-test...")
        self_code, self_text, self_seconds = run_self_test(args.self_test_timeout)
        log(f"Self-test exit code {self_code} after {self_seconds:.0f} s")

    zip_entries = make_zip(version)
    exe_hash, zip_hash = sha256(EXE), sha256(ZIP)
    SHA.write_text(f"{exe_hash} *WinFixAI.exe\n{zip_hash} *WinFixAI.zip\n", encoding="utf-8")

    def dep(name: str) -> str:
        try:
            return md.version(name)
        except md.PackageNotFoundError:
            return "not installed"

    ok = (not forbidden and not exe_secrets and not meta_problems
          and tests_code in (0, None) and self_code in (0, None))
    report = [
        "WinFix AI - build report",
        "=" * 24,
        f"Result: {'SUCCESS' if ok else 'FAILED'}",
        f"Version: {version}",
        f"Built: {started:%Y-%m-%d %H:%M:%S} UTC on {platform.platform()}",
        f"Build Python: {platform.python_version()} ({sys.executable})",
        f"PyInstaller: {dep('pyinstaller')}   PySide6: {dep('PySide6_Essentials')}",
        f"Git commit: {git_commit()}",
        "",
        "Artifacts",
        f"  {EXE}  {EXE.stat().st_size / 1_048_576:.1f} MB  sha256 {exe_hash}",
        f"  {ZIP}  {ZIP.stat().st_size / 1_048_576:.1f} MB  sha256 {zip_hash}",
        f"  {SHA}",
        f"  Zip contents: {', '.join(zip_entries)}",
        "",
        "Executable metadata",
        *[f"  {k}: {v}" for k, v in sorted(meta.items()) if not k.startswith("_")],
        f"  Icon resources: {meta.get('_icon_groups')}",
        f"  Subsystem: {meta.get('_subsystem')}   Machine: {meta.get('_machine')}",
        *[f"  PROBLEM: {p}" for p in meta_problems],
        "",
        "Bundled content checks",
        f"  Files and modules in the executable: {len(files)}",
        f"  WinFix modules: {sum(1 for m in modules if m == 'app' or m.startswith('app.'))}",
        f"  Forbidden files (.env, databases, settings, logs, tests, reports): "
        f"{'none' if not forbidden else ', '.join(forbidden)}",
        f"  Secret-like strings in the executable: "
        f"{'none' if not exe_secrets else ', '.join(exe_secrets)}",
        "  Secret-like strings in app/ source: none",
        f"  HTTP API server (fastapi/uvicorn/app.api) bundled: "
        f"{'yes' if any(m.startswith(('fastapi', 'uvicorn', 'app.api')) for m in modules) else 'no'}",
        "",
        "Checks run",
        f"  Unit/integration/safety/UI tests: "
        f"{'skipped' if tests_code is None else ('passed' if tests_code == 0 else 'FAILED')}",
        f"  Packaged exe self-test: "
        f"{'skipped' if self_code is None else ('passed' if self_code == 0 else 'FAILED')}"
        f" ({self_seconds:.0f} s)",
        "",
        "Bundled third-party packages (licenses in THIRD-PARTY-NOTICES.txt)",
        *[f"  {p}" for p in listed],
    ]
    (DIST / "build_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    tests = [
        "WinFix AI - test report",
        "=" * 23,
        f"Version: {version}   Generated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC",
        f"Environment: {platform.platform()}, Python {platform.python_version()}",
        "",
        "1. Source test suite (pytest: unit, integration, safety, UI)",
        f"   Exit code: {tests_code}",
        "",
        tests_output.strip(),
        "",
        "2. Packaged executable self-test (WinFixAI.exe --self-test)",
        f"   Exit code: {self_code}   Duration: {self_seconds:.0f} s",
        "   Runs in demo mode with an isolated data folder: sample measurements,",
        "   simulated fixes, nothing on the PC is changed.",
        "",
        self_text.strip(),
    ]
    (DIST / "test_report.txt").write_text("\n".join(tests) + "\n", encoding="utf-8")

    log("")
    for path in (EXE, ZIP, SHA, DIST / "build_report.txt", DIST / "test_report.txt"):
        log(f"{path.resolve()}")
    log(f"SHA-256 WinFixAI.exe: {exe_hash}")
    log(f"SHA-256 WinFixAI.zip: {zip_hash}")
    log("BUILD " + ("SUCCEEDED" if ok else "FAILED - see dist/build_report.txt"))
    return 0 if ok else 1


def git_commit() -> str:
    if os.environ.get("WINFIX_GIT_COMMIT"):
        return os.environ["WINFIX_GIT_COMMIT"]
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=10).stdout.strip() \
            or "unknown"
    except (OSError, subprocess.SubprocessError):
        return os.environ.get("GITHUB_SHA", "unknown")[:7]


if __name__ == "__main__":
    raise SystemExit(main())
