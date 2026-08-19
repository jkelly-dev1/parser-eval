#!/usr/bin/env python3
"""Claude Opus 5 as a document parser, over the same corpus as the rest.

    ./run_cloud.sh claude --corpus real/pages --out out_real/claude

THIS IS A PAID RUN. Every page is one API call. Cost is reported per page from
the response's own usage figures by cloud_cost.py; nothing here estimates.

WHY OPUS 5 AND NOT SONNET. The pair is price-matched on purpose:
claude-opus-5 at $5/$25 per million tokens against gpt-5.6-sol at $5/$30 --
identical input price, 20% apart on output. Running a cheaper model on one side
and the flagship on the other would make the cost column meaningless. Sonnet 5
is the interesting third run and it is not this one. The prices, and the date
they were verified, are in cloud_cost.py.

EFFORT IS MEDIUM, AND IT IS A CHOICE THAT COSTS MONEY. Thinking tokens bill as
output. Low would be cheaper and would understate what the model can do on the
two hand-filled 1929 schedules, which are the pages the whole cloud arm exists
to ask about -- they have no text layer, so a model either reads the pencil or
returns nothing. Max would answer a question nobody asked at several times the
price. The setting is recorded here because it is part of the result: a
cost-per-page figure means nothing without the effort level that produced it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloud import PROMPT, _api_key, b64, drive, page_bytes, record  # noqa: E402

MODEL = "claude-opus-5"
EFFORT = "medium"
MAX_TOKENS = 16000

_CLIENT = None


def client():
    global _CLIENT
    if _CLIENT is None:
        import anthropic
        _CLIENT = anthropic.Anthropic(api_key=_api_key("ANTHROPIC_API_KEY"))
    return _CLIENT


def version() -> str:
    from importlib.metadata import version as v
    return f"{MODEL} (anthropic {v('anthropic')}), effort={EFFORT}"


def extract(job) -> str:
    resp = client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        output_config={"effort": EFFORT},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": b64(page_bytes(job))}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    # A REFUSAL IS NOT A TRANSCRIPTION AND MUST NOT BE GRADED AS ONE. Checking
    # stop_reason before touching content is the documented order: a refusal
    # returns HTTP 200 with empty or partial content, so scoring it would
    # report a declined request as a 0% page.
    if resp.stop_reason == "refusal":
        raise RuntimeError(
            f"refusal: {getattr(resp.stop_details, 'category', None)}")
    text = "".join(b.text for b in resp.content if b.type == "text")
    record(job, resp.model, resp.usage.input_tokens, resp.usage.output_tokens,
           resp.stop_reason)
    return text


if __name__ == "__main__":
    raise SystemExit(drive("claude", version(), extract))
