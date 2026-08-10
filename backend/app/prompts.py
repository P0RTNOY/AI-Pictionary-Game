def build_svg_prompt(challenge: str, artist_tier: str = "balanced") -> str:
    if artist_tier == "confusing":
        artist_instruction = "Confusing Artist: rough, playful, and a little strange, but still clearly related to the exact prompt."
    elif artist_tier == "literal":
        artist_instruction = "Literal Artist: very clear, direct, and includes the most important prompt components."
    else:
        artist_instruction = "Balanced Artist: reasonably clear and readable, with the main prompt components represented."

    return f"""Create a clear visual SVG scene that represents this exact situation:
"{challenge}"

{artist_instruction}

Requirements:
- Include the important characters or objects.
- Show the main action; do not ignore what the characters are doing.
- Include the setting and any twist or mood when present.
- Do not draw a generic abstract icon.
- Do not include the full prompt as text.
- Short object labels are allowed only when they help and do not reveal the full answer.
- Use several meaningful shapes/paths, not only a background and text.
- Use a 1024x1024 viewBox.
- Return only valid SVG, no markdown and no code blocks.

Safety:
Do not include scripts, event handlers, external images, external fonts, or remote URLs.
Use a 1024x1024 viewBox.
"""


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
