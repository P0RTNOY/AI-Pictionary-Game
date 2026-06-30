def build_svg_prompt(challenge: str) -> str:
    return f"""Generate an SVG of {challenge}. Respond with the SVG only, no code blocks.

Make it a clear, funny, understandable scene for a guessing game.
Use a 1024x1024 viewBox.
Do not write the full prompt as text in the image.
Object labels are allowed when they help the drawing.
Do not include scripts, event handlers, external images, external fonts, or remote URLs."""


def build_judge_prompt(original: str, guess: str) -> str:
    return f"""
You are judging a guessing game.

Original situation:
"{original}"

Player guess:
"{guess}"

Score the guess from 0 to 100.

Rules:
- 100 means the guess captures all important parts.
- 70-90 means mostly correct.
- 40-69 means partially correct.
- 0-39 means mostly wrong.
- Ignore grammar and spelling mistakes.
- Reward semantic meaning, not exact wording.

Return JSON only:
{{
  "score": number,
  "matched_parts": ["..."],
  "missed_parts": ["..."],
  "short_feedback": "..."
}}
"""
