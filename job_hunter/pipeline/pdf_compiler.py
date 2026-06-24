"""
Compiles a tailored .tex resume into a PDF.

Uses native pdflatex when available (GitHub Actions), falls back to a
Docker texlive container for local Windows runs.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

from job_hunter.core.config import ROOT

logger = logging.getLogger(__name__)

_TEXLIVE_IMAGE = "texlive/texlive:latest"
_DOCKER_PULL_LOCK = threading.Lock()
_docker_image_pulled = False

_PDFLATEX_TIMEOUT = 120  # seconds: native pdflatex compile limit
_DOCKER_COMPILE_TIMEOUT = 300  # seconds: Docker-based pdflatex compile limit
_DOCKER_PULL_TIMEOUT = 600  # seconds: Docker image pull on first run


def _ensure_texlive_image() -> None:
    global _docker_image_pulled

    if _docker_image_pulled:
        return

    with _DOCKER_PULL_LOCK:
        if _docker_image_pulled:
            return

        print("  [compile] Pulling texlive Docker image (first run may take several minutes)...")
        pull_result = subprocess.run(  # noqa: S603
            ["docker", "pull", _TEXLIVE_IMAGE],  # noqa: S607
            timeout=_DOCKER_PULL_TIMEOUT,
        )
        if pull_result.returncode == 0:
            _docker_image_pulled = True


def compile_tex(tex_path: str, output_dir: str) -> str | None:
    """
    Compile a .tex file to PDF.

    Args:
        tex_path:   Absolute path to the .tex file.
        output_dir: Directory where the PDF will be written.

    Returns:
        Path to the generated PDF, or None if compilation failed.
    """
    abs_output_dir = os.path.abspath(output_dir)
    abs_tex_path = os.path.abspath(tex_path)

    if shutil.which("pdflatex"):
        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-output-directory",
            abs_output_dir,
            abs_tex_path,
        ]
        cwd = abs_output_dir
        timeout = _PDFLATEX_TIMEOUT
    else:
        _ensure_texlive_image()
        repo_root = ROOT.resolve()
        output_path = Path(abs_output_dir).resolve()
        tex_file = Path(abs_tex_path).resolve()

        try:
            container_output = f"/repo/{output_path.relative_to(repo_root).as_posix()}"
            container_tex = f"/repo/{tex_file.relative_to(repo_root).as_posix()}"
            volumes = ["-v", f"{repo_root}:/repo"]
            cwd = None
            docker_workdir = container_output
        except ValueError:
            container_tex = f"/workspace/{os.path.basename(abs_tex_path)}"
            volumes = ["-v", f"{abs_output_dir}:/workspace"]
            cwd = None
            docker_workdir = "/workspace"

        # pdfx package looks for pdfa.xmpi in the compile working directory.
        # Copy it from profile/ so pdflatex finds it without TEXINPUTS tricks.
        pdfa_src = repo_root / "profile" / "pdfa.xmpi"
        pdfa_dst = output_path / "pdfa.xmpi"
        if pdfa_src.exists() and not pdfa_dst.exists():
            shutil.copy2(pdfa_src, pdfa_dst)

        cmd = [
            "docker",
            "run",
            "--rm",
            *volumes,
            "-w",
            docker_workdir,
            _TEXLIVE_IMAGE,
            "pdflatex",
            "-interaction=nonstopmode",
            "-output-directory",
            docker_workdir,
            container_tex,
        ]
        timeout = _DOCKER_COMPILE_TIMEOUT

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)  # noqa: S603
    if result.returncode != 0:
        logger.warning("[compile] pdflatex exited with code %d", result.returncode)
        logger.debug("[compile] pdflatex output:\n%s", (result.stdout + result.stderr)[-2000:])

    expected_pdf = os.path.join(
        abs_output_dir,
        os.path.basename(tex_path).replace(".tex", ".pdf"),
    )

    if os.path.exists(expected_pdf):
        return expected_pdf

    print(f"  [compile] FAILED — check log in {abs_output_dir}")
    print(result.stdout[-1000:])
    return None
