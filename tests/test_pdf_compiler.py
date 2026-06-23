"""Tests for pipeline/pdf_compiler.py — subprocess and shutil.which are mocked."""

from unittest.mock import MagicMock, patch

import pytest

from job_hunter.pipeline import pdf_compiler


@pytest.fixture(autouse=True)
def reset_docker_pull_cache():
    pdf_compiler._docker_image_pulled = False
    yield
    pdf_compiler._docker_image_pulled = False


def _fake_run_creates_pdf(pdf_path):
    """Returns a side_effect that writes a fake PDF file on subprocess.run calls."""

    def _run(cmd, **kwargs):
        if "pdflatex" in " ".join(str(c) for c in cmd):
            pdf_path.write_bytes(b"%PDF-fake")
        result = MagicMock()
        result.stdout = ""
        return result

    return _run


def test_compile_tex_returns_pdf_path_when_pdflatex_succeeds(tmp_path) -> None:
    tex = tmp_path / "resume.tex"
    tex.write_text(r"\documentclass{article}\begin{document}x\end{document}")
    expected_pdf = tmp_path / "resume.pdf"

    with (
        patch("job_hunter.pipeline.pdf_compiler.shutil.which", return_value="/usr/bin/pdflatex"),
        patch(
            "job_hunter.pipeline.pdf_compiler.subprocess.run",
            side_effect=_fake_run_creates_pdf(expected_pdf),
        ),
    ):
        result = pdf_compiler.compile_tex(str(tex), str(tmp_path))

    assert result == str(expected_pdf)


def test_compile_tex_runs_from_output_dir_without_copying_assets(tmp_path) -> None:
    tex = tmp_path / "resume.tex"
    tex.write_text(r"\documentclass{article}\begin{document}x\end{document}")
    image = tmp_path / "Profile-2025.png"
    image.write_bytes(b"image")
    cls = tmp_path / "altacv.cls"
    cls.write_text("class")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    expected_pdf = out_dir / "resume.pdf"

    with (
        patch("job_hunter.pipeline.pdf_compiler.shutil.which", return_value="/usr/bin/pdflatex"),
        patch(
            "job_hunter.pipeline.pdf_compiler.subprocess.run",
            side_effect=_fake_run_creates_pdf(expected_pdf),
        ) as run,
    ):
        result = pdf_compiler.compile_tex(str(tex), str(out_dir))

    assert result == str(expected_pdf)
    assert not (out_dir / "Profile-2025.png").exists()
    assert not (out_dir / "altacv.cls").exists()
    assert run.call_args.kwargs["cwd"] == str(out_dir)


def test_compile_tex_returns_none_when_no_pdf_produced(tmp_path) -> None:
    tex = tmp_path / "resume.tex"
    tex.write_text("bad latex")
    mock_result = MagicMock()
    mock_result.stdout = "LaTeX error"

    with (
        patch("job_hunter.pipeline.pdf_compiler.shutil.which", return_value="/usr/bin/pdflatex"),
        patch("job_hunter.pipeline.pdf_compiler.subprocess.run", return_value=mock_result),
    ):
        result = pdf_compiler.compile_tex(str(tex), str(tmp_path))

    assert result is None


def test_compile_tex_uses_docker_when_no_pdflatex(tmp_path) -> None:
    tex = tmp_path / "resume.tex"
    tex.write_text("content")
    expected_pdf = tmp_path / "resume.pdf"
    docker_calls = []

    def _run(cmd, **kwargs):
        docker_calls.append(cmd)
        if "pdflatex" in " ".join(str(c) for c in cmd):
            expected_pdf.write_bytes(b"%PDF-fake")
        result = MagicMock()
        result.stdout = ""
        return result

    with (
        patch("job_hunter.pipeline.pdf_compiler.shutil.which", return_value=None),
        patch("job_hunter.pipeline.pdf_compiler.subprocess.run", side_effect=_run),
    ):
        result = pdf_compiler.compile_tex(str(tex), str(tmp_path))

    assert any("docker" in str(c) for c in docker_calls[0])
    assert result == str(expected_pdf)


def test_compile_tex_pulls_docker_image_once_when_reused(tmp_path) -> None:
    tex = tmp_path / "resume.tex"
    tex.write_text("content")
    expected_pdf = tmp_path / "resume.pdf"
    docker_calls = []

    def _run(cmd, **kwargs):
        docker_calls.append(cmd)
        if "pdflatex" in " ".join(str(c) for c in cmd):
            expected_pdf.write_bytes(b"%PDF-fake")
        result = MagicMock()
        result.stdout = ""
        return result

    with (
        patch("job_hunter.pipeline.pdf_compiler.shutil.which", return_value=None),
        patch("job_hunter.pipeline.pdf_compiler.subprocess.run", side_effect=_run),
    ):
        first = pdf_compiler.compile_tex(str(tex), str(tmp_path))
        second = pdf_compiler.compile_tex(str(tex), str(tmp_path))

    pull_calls = [call for call in docker_calls if call[:2] == ["docker", "pull"]]
    run_calls = [call for call in docker_calls if call[:2] == ["docker", "run"]]

    assert first == str(expected_pdf)
    assert second == str(expected_pdf)
    assert len(pull_calls) == 1
    assert len(run_calls) == 2
