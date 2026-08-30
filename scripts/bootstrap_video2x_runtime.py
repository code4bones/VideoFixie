#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from textwrap import dedent


DEFAULT_APPIMAGE = Path("bin") / "Video2X-x86_64.AppImage"
RUNTIME_DIR = Path("share") / "video2x"
WRAPPER_PATH = Path("bin") / "video2x"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap project-local Video2X runtime from an AppImage.")
    parser.add_argument("--project-root", default=".", help="Project root containing ./bin and ./share.")
    parser.add_argument("--appimage", default=str(DEFAULT_APPIMAGE), help="Source Video2X AppImage path.")
    parser.add_argument("--force", action="store_true", help="Replace an existing ./share/video2x runtime.")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    appimage = _project_path(project_root, args.appimage)
    if not appimage.exists():
        raise FileNotFoundError(f"Video2X AppImage not found: {appimage}")

    with tempfile.TemporaryDirectory(prefix="videofixie-video2x-") as tmp_dir:
        subprocess.run(
            [str(appimage), "--appimage-extract"],
            cwd=tmp_dir,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        extracted = Path(tmp_dir) / "squashfs-root"
        install_from_extracted_appdir(extracted, project_root, force=args.force)

    runtime = project_root / RUNTIME_DIR
    print(f"Video2X runtime: {runtime}")
    print(f"Video2X wrapper: {project_root / WRAPPER_PATH}")
    print(f"Models: {runtime / 'models'}")
    return 0


def install_from_extracted_appdir(extracted_appdir: Path, project_root: Path, *, force: bool = False) -> None:
    extracted = extracted_appdir.resolve()
    project = project_root.resolve()
    _validate_appdir(extracted)

    runtime = project / RUNTIME_DIR
    if runtime.exists():
        if not force:
            raise FileExistsError(f"Runtime already exists: {runtime}. Use --force to replace it.")
        shutil.rmtree(runtime)

    runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(extracted, runtime, symlinks=True)
    _ensure_models_link(runtime)
    _write_wrapper(project / WRAPPER_PATH)


def _validate_appdir(appdir: Path) -> None:
    required = (
        appdir / "usr" / "bin" / "video2x",
        appdir / "usr" / "share" / "video2x" / "models",
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Extracted AppDir is missing required Video2X files: {missing_text}")


def _ensure_models_link(runtime: Path) -> None:
    link = runtime / "models"
    target = Path("usr") / "share" / "video2x" / "models"
    if link.is_symlink() or link.exists():
        if link.is_dir() and not link.is_symlink():
            shutil.rmtree(link)
        else:
            link.unlink()
    link.symlink_to(target, target_is_directory=True)


def _write_wrapper(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        dedent(
            """\
            #!/bin/sh
            set -eu

            SELF_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
            ROOT=$(CDPATH= cd -- "$SELF_DIR/.." && pwd)
            APPDIR="$ROOT/share/video2x"

            export APPDIR
            export PATH="$APPDIR/usr/bin:$PATH"
            if [ -d "$APPDIR/usr/lib" ]; then
                export LD_LIBRARY_PATH="$APPDIR/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
            fi

            cd "$APPDIR"
            exec "$APPDIR/usr/bin/video2x" "$@"
            """
        ),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | 0o755)


def _project_path(project_root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else project_root / value


if __name__ == "__main__":
    raise SystemExit(main())
