from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import pytesseract


@dataclass
class OcrCandidate:
    variant: str
    psm: int
    raw_text: str
    normalized_text: str
    confidence: float
    score: float
    tokens: list[dict[str, Any]]


@dataclass
class OcrResult:
    raw_text: str
    cleaned_text: str
    confidence: float
    warnings: list[str]
    tokens: list[dict[str, Any]]
    selected_variant: str
    selected_psm: int
    candidates: list[dict[str, Any]]


def _safe_eval_arithmetic(expr: str) -> float | None:
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Constant,
        ast.Load,
    )
    if not re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s]+", expr):
        return None
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    if any(not isinstance(n, allowed_nodes) for n in ast.walk(node)):
        return None
    try:
        value = eval(compile(node, "<math_expr>", "eval"), {"__builtins__": {}}, {})
    except Exception:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def apply_basic_equation_correction(expr: str) -> tuple[str, str | None]:
    candidate = expr.strip()
    if candidate.count("=") != 1:
        return candidate, None

    lhs, rhs = [part.strip() for part in candidate.split("=", 1)]
    lhs_val = _safe_eval_arithmetic(lhs)
    rhs_val = _safe_eval_arithmetic(rhs)
    if lhs_val is None or rhs_val is None:
        return candidate, None

    if abs(lhs_val - rhs_val) < 1e-9:
        return candidate, None

    if abs(lhs_val - round(lhs_val)) < 1e-9:
        corrected_rhs = str(int(round(lhs_val)))
    else:
        corrected_rhs = f"{lhs_val:.6g}"
    corrected = f"{lhs}={corrected_rhs}"
    return corrected, f"Auto-corrected arithmetic mismatch: {candidate} -> {corrected}"


def _normalize_math_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("\n", " ")
    cleaned = cleaned.replace("−", "-")
    cleaned = cleaned.replace("×", r"\cdot ")
    cleaned = cleaned.replace("÷", r"\div ")
    cleaned = cleaned.replace("√", r"\sqrt")
    cleaned = cleaned.replace("π", r"\pi")
    cleaned = cleaned.replace("∞", r"\infty")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace(" ^ ", "^")
    cleaned = re.sub(r"([A-Za-z0-9])\s*\^\s*([A-Za-z0-9])", r"\1^\2", cleaned)
    cleaned = re.sub(r"([0-9])\s*\/\s*([0-9])", r"\\frac{\1}{\2}", cleaned)
    cleaned = re.sub(r"(?<=\b)\|(?=\b)", "1", cleaned)
    cleaned = cleaned.replace("O", "0") if re.fullmatch(r"[0-9O\+\-\*/=\s]+", cleaned) else cleaned
    return cleaned.strip()


def _load_image(image_path: Path) -> Any:
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not read image at: {image_path}")
    return image


def _build_preprocessed_variants(image: Any) -> dict[str, Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    adaptive = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
    _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contrast = cv2.convertScaleAbs(gray, alpha=1.5, beta=5)
    _, contrast_bin = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return {
        "adaptive": adaptive,
        "otsu": otsu,
        "contrast": contrast_bin,
    }


def _score_candidate(text: str, confidence: float) -> float:
    normalized = _normalize_math_text(text)
    score = confidence
    if "=" in normalized:
        score += 8.0
    if re.search(r"[0-9]", normalized):
        score += 4.0
    if re.search(r"[\+\-\*/\^]", normalized):
        score += 4.0
    if not normalized:
        score -= 20.0
    return score


def _run_tesseract_candidate(variant: str, image: Any, psm: int) -> OcrCandidate:
    config = (
        f"--oem 3 --psm {psm} "
        "-c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+-=*/()[]{}^., "
    )
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, config=config)
    tokens: list[dict[str, Any]] = []
    confidences: list[float] = []

    for i, text in enumerate(data["text"]):
        token = text.strip()
        if not token:
            continue
        raw_conf = data["conf"][i]
        try:
            conf = float(raw_conf)
        except ValueError:
            conf = -1.0
        if conf >= 0:
            confidences.append(conf)
        tokens.append({"text": token, "conf": conf})

    raw_text = " ".join(t["text"] for t in tokens).strip()
    normalized = _normalize_math_text(raw_text)
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    score = _score_candidate(raw_text, confidence)
    return OcrCandidate(
        variant=variant,
        psm=psm,
        raw_text=raw_text,
        normalized_text=normalized,
        confidence=confidence,
        score=score,
        tokens=tokens,
    )


def extract_and_clean_math(
    image_path: Path,
    tesseract_cmd: str | None = None,
    debug_dir: Path | None = None,
) -> OcrResult:
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    image = _load_image(image_path)
    variants = _build_preprocessed_variants(image)
    psm_values = (6, 7, 11)
    candidates: list[OcrCandidate] = []

    for variant_name, processed_image in variants.items():
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(debug_dir / f"preprocessed_{variant_name}.png"), processed_image)
        for psm in psm_values:
            candidates.append(_run_tesseract_candidate(variant_name, processed_image, psm))

    if not candidates:
        raise RuntimeError("No OCR candidates were generated.")

    best = max(candidates, key=lambda c: c.score)
    raw_text = best.raw_text
    cleaned = best.normalized_text
    confidence = best.confidence
    tokens = best.tokens

    warnings: list[str] = []
    if not raw_text:
        warnings.append("No text detected by OCR. Try a higher-contrast image.")
    if confidence < 65:
        warnings.append("Low OCR confidence. Verify output manually before rendering.")
    if cleaned != raw_text:
        warnings.append("Expression was normalized from OCR output.")
    warnings.append(f"OCR selected variant={best.variant}, psm={best.psm}.")

    candidate_dicts = [asdict(c) for c in sorted(candidates, key=lambda c: c.score, reverse=True)]
    if debug_dir:
        summary_path = debug_dir / "ocr_candidates.json"
        summary_path.write_text(json.dumps(candidate_dicts, indent=2), encoding="utf-8")

    return OcrResult(
        raw_text=raw_text,
        cleaned_text=cleaned,
        confidence=confidence,
        warnings=warnings,
        tokens=tokens,
        selected_variant=best.variant,
        selected_psm=best.psm,
        candidates=candidate_dicts,
    )
