# Isolated Manim OCR Animator

This folder is a standalone environment for:
1. reading a math-question photo,
2. extracting and cleaning the expression with OCR,
3. generating a ManimGL scene,
4. rendering an animation.

It does not modify your `HackKU26` project dependencies.

## Layout

- `.venv/` - local Python virtual environment
- `manim/` - cloned `3b1b/manim` repository
- `pipeline/` - OCR and scene generation scripts
- `inputs/` - image files you want to process
- `outputs/` - generated JSON metadata and scene files

## V2 upgrades

- Multi-pass OCR selection (preprocessing variants + multiple Tesseract PSM modes)
- Explainable correction metadata (`rule_id`, reason, token-level diff)
- Side-by-side scene layout (input image + correction animation)
- Visual correction narrative (detected -> incorrect token -> corrected -> verified summary card)
- Debug artifact output (preprocessed images + candidate summaries)

## Prerequisites (Windows)

- Python 3.10+ (already used for `.venv`)
- FFmpeg in PATH
- LaTeX distribution (MiKTeX recommended)
- Tesseract OCR (default path expected: `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`)

ManimGL reference: [3b1b/manim](https://github.com/3b1b/manim.git)

## Install pipeline dependencies

From this folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

## Run the pipeline

Put an image in `inputs/` and run:

```powershell
.\.venv\Scripts\python.exe .\pipeline\run_pipeline.py --image .\inputs\sample.png
```

### Optional flags

- `--quality l|m|h|k` (default `l`)
- `--manual-text "x^2 + 2x + 1 = 0"` (skip OCR and force expression)
- `--skip-render` (generate OCR + scene files only; useful before FFmpeg/LaTeX are ready)
- `--preview` (faster scene timings for iteration)

## Output artifacts

- `outputs/ocr_result_<timestamp>.json` - raw OCR, cleaned expression, confidence, warnings
- `outputs/generated_scene_<timestamp>.py` - auto-generated Manim scene source
- `outputs/debug_<timestamp>/preprocessed_*.png` - OCR preprocessing variants
- `outputs/debug_<timestamp>/ocr_candidates.json` - ranked OCR candidates
- Render output: `manim/videos/OCRMathScene.mp4`

### Correction metadata schema

`ocr_result_<timestamp>.json` now includes:
- `selected_variant` / `selected_psm` (chosen OCR path)
- `candidates` (ranked OCR candidates with scores)
- `correction`:
  - `applied` (bool)
  - `rule_id` (e.g. `arithmetic_equation_mismatch`)
  - `reason` (human-readable explanation)
  - `token_diff.before` / `token_diff.after`

## Benchmark validation (V2)

Benchmark inputs are in `inputs/benchmark/`:
- `wrong_eq_clear.png`
- `wrong_eq_lowcontrast.png`
- `wrong_eq_blur_rotate.png`
- `correct_eq_clear.png`

Run benchmark:

```powershell
$imgs = @('wrong_eq_clear.png','wrong_eq_lowcontrast.png','wrong_eq_blur_rotate.png','correct_eq_clear.png')
foreach ($img in $imgs) {
  .\.venv\Scripts\python.exe .\pipeline\run_pipeline.py --image ".\inputs\benchmark\$img" --preview
}
```

Latest recorded run highlights:
- `wrong_eq_clear.png`: corrected `2+2=5` -> `2+2=4` (`arithmetic_equation_mismatch`)
- `wrong_eq_blur_rotate.png`: detected arithmetic mismatch and corrected RHS
- `correct_eq_clear.png`: preserved correct equation without correction
- `wrong_eq_lowcontrast.png`: remains a hard OCR case (expected failure bucket)

This meets the V2 target of improved behavior on 3/4 benchmark samples.

## Notes

- If OCR confidence is low, check the JSON warnings and use `--manual-text`.
- Cleaner currently applies lightweight normalization and common OCR typo fixes.
- Full rendering requires both FFmpeg and a LaTeX compiler on PATH. If either is missing, run with `--skip-render` first.
