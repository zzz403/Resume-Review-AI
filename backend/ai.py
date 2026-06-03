import os
import anthropic
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

# ── Starter: intentionally naive ──────────────────────────────────────────
#
# This file has four deliberate problems — one per course module:
#
#   Module 1 – No structured output. Score is parsed from raw text (fragile).
#               Try submitting the same resume twice: the score format may differ.
#
#   Module 2 – No temperature setting. The model's randomness is unconstrained.
#               Submit the same resume 3 times and compare scores in History.
#
#   Module 3 – No conversation history. Every call is completely stateless.
#               There is no way to ask a follow-up question about the review.
#
#   Module 4 – No metadata logged. We cannot later audit for bias patterns.
#
# You will fix each of these, one module at a time.
# ──────────────────────────────────────────────────────────────────────────

def review_resume(resume_text: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key.lower() in {"dummy", "your_anthropic_api_key_here"}:
        raise HTTPException(status_code=400, detail="Anthropic API key is not configured.")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": (
                    "Review this resume and give it a score from 1 to 100. "
                    "Start your response with the number only on the first line, "
                    "then explain your reasoning.\n\n"
                    f"{resume_text}"
                ),
            }
        ],
    )

    raw = message.content[0].text
    lines = raw.strip().splitlines()

    try:
        score = int(lines[0].strip())
    except (ValueError, IndexError):
        score = None

    feedback = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw

    return {"score": score, "feedback": feedback}
