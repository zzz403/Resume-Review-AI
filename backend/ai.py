from dotenv import load_dotenv
from fastapi import HTTPException

import llm

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
    if not llm.is_configured():
        raise HTTPException(status_code=400, detail=f"{llm.get_provider()} API key is not configured.")

    try:
        raw = llm.complete(
            (
                "Review this resume and give it a score from 1 to 100. "
                "Start your response with the number only on the first line, "
                "then explain your reasoning.\n\n"
                f"{resume_text}"
            ),
            max_tokens=512,
        )
    except llm.LLMAuthError as exc:
        raise HTTPException(status_code=400, detail=f"{llm.get_provider()} API key was rejected.") from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"{llm.get_provider()} request failed: {exc}") from exc

    lines = raw.strip().splitlines()

    try:
        score = int(lines[0].strip())
    except (ValueError, IndexError):
        score = None

    feedback = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw

    return {"score": score, "feedback": feedback}
