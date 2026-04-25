from __future__ import annotations

from pathlib import Path


SCENE_TEMPLATE = """from manimlib import *


class OCRMathScene(Scene):
    def construct(self):
        raw_expr = r\"\"\"{raw_expr}\"\"\"
        clean_expr = r\"\"\"{clean_expr}\"\"\"
        correction_reason = r\"\"\"{correction_reason}\"\"\"
        correction_rule = r\"\"\"{correction_rule}\"\"\"
        confidence = {confidence}
        image_path = r\"\"\"{image_path}\"\"\"
        preview_mode = {preview_mode}

        title = Text("OCR Math Animator").scale(0.6).to_edge(UP)
        self.play(FadeIn(title, shift=UP))

        # Left panel: source image for side-by-side explanation
        source = None
        if image_path:
            source = ImageMobject(image_path)
            source.set_height(3.2)
            source.to_edge(LEFT, buff=0.8)
            source_frame = SurroundingRectangle(source, color=GREY_B, buff=0.12)
            source_label = Text("Input", font_size=30).next_to(source, UP, buff=0.15)
            self.play(FadeIn(source), ShowCreation(source_frame), FadeIn(source_label), run_time=0.9)

        stage_group = VGroup()
        if source is not None:
            stage_group.shift(RIGHT * 2.2)

        raw = Text(raw_expr).scale(0.9)
        raw.set_color(RED)
        raw.move_to(stage_group.get_center())

        explain = Text("Detected expression", font_size=34).set_color(GREY_B)
        explain.next_to(raw, DOWN, buff=0.35)

        write_time = 1.2 if preview_mode else 2.0
        self.play(Write(raw), FadeIn(explain), run_time=write_time)
        self.wait(0.2 if preview_mode else 0.4)

        if clean_expr != raw_expr:
            wrong_token = Text(raw_expr[-1] if raw_expr else "?", font_size=42).set_color(RED)
            wrong_token.next_to(raw, UP, buff=0.28)
            wrong_label = Text("Incorrect token", font_size=28).set_color(RED).next_to(wrong_token, UP, buff=0.1)
            self.play(FadeIn(wrong_token), FadeIn(wrong_label), run_time=0.6 if preview_mode else 1.0)

            fixed = Text(clean_expr).scale(0.9)
            fixed.set_color(YELLOW)
            self.play(Transform(raw, fixed), run_time=1.2 if preview_mode else 2.2)
            self.play(FadeOut(wrong_token), FadeOut(wrong_label), run_time=0.4)

            reason_line = Text(correction_reason or "Rule-based correction applied", font_size=25)
            reason_line.set_color(YELLOW)
            reason_line.next_to(raw, DOWN, buff=0.35)
            self.play(Transform(explain, reason_line), run_time=0.6 if preview_mode else 1.0)
        else:
            self.play(Indicate(raw), run_time=0.8 if preview_mode else 1.4)
            self.wait(0.2 if preview_mode else 0.4)

        verified = Text(clean_expr).scale(0.9).set_color(GREEN)
        self.play(Transform(raw, verified), run_time=0.9 if preview_mode else 1.3)
        box = SurroundingRectangle(raw, buff=0.25, color=GREEN)
        self.play(ShowCreation(box), run_time=0.7 if preview_mode else 1.0)

        summary_title = Text("Verified", font_size=34).set_color(GREEN)
        summary_title.to_edge(DOWN, buff=1.2)
        summary_details = Text(
            f"Rule: {{correction_rule or 'none'}} | Confidence: {{confidence:.1f}}",
            font_size=24
        ).set_color(GREY_B)
        summary_details.next_to(summary_title, DOWN, buff=0.2)
        self.play(FadeIn(summary_title), FadeIn(summary_details), run_time=0.8 if preview_mode else 1.2)
        self.wait(0.6 if preview_mode else 1.2)
"""


def _escape_for_triple_quoted_tex(value: str) -> str:
    return value.replace('"""', r"\"\"\"")


def write_scene_file(
    output_path: Path,
    raw_expr: str,
    clean_expr: str,
    *,
    correction_reason: str = "",
    correction_rule: str = "",
    confidence: float = 0.0,
    image_path: str = "",
    preview_mode: bool = False,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = SCENE_TEMPLATE.format(
        raw_expr=_escape_for_triple_quoted_tex(raw_expr or ""),
        clean_expr=_escape_for_triple_quoted_tex(clean_expr or ""),
        correction_reason=_escape_for_triple_quoted_tex(correction_reason or ""),
        correction_rule=_escape_for_triple_quoted_tex(correction_rule or ""),
        confidence=confidence,
        image_path=_escape_for_triple_quoted_tex(image_path or ""),
        preview_mode=str(bool(preview_mode)),
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path
