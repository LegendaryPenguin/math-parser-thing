from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from build_scene import write_scene_file
from extract_math import apply_basic_equation_correction, extract_and_clean_math


def _run_command(command: list[str], cwd: Path, extra_path_entries: list[str] | None = None) -> None:
    env = os.environ.copy()
    if extra_path_entries:
        env["PATH"] = os.pathsep.join(extra_path_entries + [env.get("PATH", "")])
    result = subprocess.run(command, cwd=str(cwd), check=False, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")


def _detect_manimgl_executable(venv_path: Path) -> list[str]:
    exe = venv_path / "Scripts" / "manimgl.exe"
    py = venv_path / "Scripts" / "python.exe"
    if exe.exists():
        return [str(exe)]
    if py.exists():
        return [str(py), "-m", "manimlib"]
    return ["manimgl"]


def _detect_tesseract() -> str | None:
    which = shutil.which("tesseract")
    if which:
        return which
    default_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if default_path.exists():
        return str(default_path)
    return None


def _detect_ffmpeg_bin_dir() -> str | None:
    which = shutil.which("ffmpeg")
    if which:
        return str(Path(which).parent)

    winget_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    candidates = sorted(winget_root.glob("Gyan.FFmpeg*/ffmpeg-*-full_build/bin/ffmpeg.exe"))
    if candidates:
        return str(candidates[-1].parent)
    return None


def _detect_latex_bin_dir() -> str | None:
    for exe in ("pdflatex", "xelatex", "latex"):
        which = shutil.which(exe)
        if which:
            return str(Path(which).parent)

    miktex_bin = Path.home() / "AppData" / "Local" / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64"
    if (miktex_bin / "pdflatex.exe").exists():
        return str(miktex_bin)
    return None


def _token_diff(before: str, after: str) -> dict[str, str]:
    start = 0
    while start < len(before) and start < len(after) and before[start] == after[start]:
        start += 1

    end_before = len(before)
    end_after = len(after)
    while end_before > start and end_after > start and before[end_before - 1] == after[end_after - 1]:
        end_before -= 1
        end_after -= 1

    return {
        "before": before[start:end_before],
        "after": after[start:end_after],
    }


def _build_correction_payload(before: str, after: str, note: str | None) -> dict[str, object]:
    if not note or before == after:
        return {"applied": False, "rule_id": "none", "reason": "", "token_diff": {"before": "", "after": ""}}

    rule_id = "arithmetic_equation_mismatch"
    if re.search(r"normalized", note, flags=re.IGNORECASE):
        rule_id = "ocr_normalization"
    return {
        "applied": True,
        "rule_id": rule_id,
        "reason": note,
        "token_diff": _token_diff(before, after),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR -> cleanup -> Manim render pipeline")
    parser.add_argument("--image", required=True, help="Path to input image containing math question")
    parser.add_argument("--quality", default="l", choices=["l", "m", "h", "k"], help="Manim quality preset")
    parser.add_argument("--output-dir", default="../outputs", help="Output directory for artifacts")
    parser.add_argument("--manual-text", default="", help="Optional override text instead of OCR result")
    parser.add_argument("--skip-render", action="store_true", help="Only generate OCR and scene artifacts")
    parser.add_argument("--preview", action="store_true", help="Use faster animation timings for iteration")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    root_dir = script_dir.parent
    venv_dir = root_dir / ".venv"

    image_path = Path(args.image).expanduser().resolve()
    output_dir = (script_dir / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_dir = output_dir / f"debug_{stamp}"

    tesseract_cmd = _detect_tesseract()
    if not tesseract_cmd and not args.manual_text:
        raise RuntimeError(
            "Tesseract executable was not found. Install Tesseract or pass --manual-text to skip OCR."
        )

    if args.manual_text:
        raw_text = args.manual_text
        cleaned_text = args.manual_text
        confidence = 100.0
        warnings = ["Manual text override used; OCR skipped."]
        tokens = []
        selected_variant = "manual"
        selected_psm = -1
        candidates: list[dict[str, object]] = []
        correction_note: str | None = None
    else:
        ocr = extract_and_clean_math(image_path=image_path, tesseract_cmd=tesseract_cmd, debug_dir=debug_dir)
        raw_text = ocr.raw_text
        cleaned_text = ocr.cleaned_text
        confidence = ocr.confidence
        warnings = ocr.warnings
        tokens = ocr.tokens
        selected_variant = ocr.selected_variant
        selected_psm = ocr.selected_psm
        candidates = ocr.candidates
        corrected_text, correction_note = apply_basic_equation_correction(cleaned_text)
        if correction_note:
            cleaned_text = corrected_text
            warnings.append(correction_note)

    correction = _build_correction_payload(raw_text, cleaned_text, correction_note if not args.manual_text else None)
    scene_file = output_dir / f"generated_scene_{stamp}.py"
    write_scene_file(
        scene_file,
        raw_text,
        cleaned_text,
        correction_reason=str(correction["reason"]),
        correction_rule=str(correction["rule_id"]),
        confidence=confidence,
        image_path=str(image_path),
        preview_mode=args.preview,
    )

    artifact = {
        "timestamp": stamp,
        "input_image": str(image_path),
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "ocr_confidence": confidence,
        "warnings": warnings,
        "tokens": tokens,
        "selected_variant": selected_variant,
        "selected_psm": selected_psm,
        "candidates": candidates,
        "correction": correction,
        "scene_file": str(scene_file),
        "tesseract_cmd": tesseract_cmd,
        "debug_dir": str(debug_dir) if not args.manual_text else "",
    }
    json_path = output_dir / f"ocr_result_{stamp}.json"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    if not cleaned_text:
        raise RuntimeError(f"OCR returned empty expression. See artifact: {json_path}")

    if args.skip_render:
        print(f"Scene file: {scene_file}")
        print(f"OCR artifact: {json_path}")
        print("Skipped render (--skip-render).")
        return

    ffmpeg_bin_dir = _detect_ffmpeg_bin_dir()
    if not ffmpeg_bin_dir:
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg and rerun, or use --skip-render to only generate artifacts."
        )
    latex_bin_dir = _detect_latex_bin_dir()
    if not latex_bin_dir:
        raise RuntimeError(
            "LaTeX compiler was not found. Install MiKTeX/LaTeX and rerun, or use --skip-render."
        )

    manim_cmd = _detect_manimgl_executable(venv_dir)
    render_cmd = [
        *manim_cmd,
        str(scene_file),
        "OCRMathScene",
        "-w",
        f"-q{args.quality}",
    ]
    _run_command(
        render_cmd,
        cwd=root_dir / "manim",
        extra_path_entries=[ffmpeg_bin_dir, latex_bin_dir],
    )

    print(f"Scene file: {scene_file}")
    print(f"OCR artifact: {json_path}")
    print("Render complete. Check Manim media output directory for video/image artifacts.")


if __name__ == "__main__":
    main()
