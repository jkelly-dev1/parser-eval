#!/usr/bin/env python3
"""GPT-5.6-sol as a document parser, over the same corpus as the rest.

    ./run_cloud.sh gpt --corpus real/pages --out out_real/gpt

THIS IS A PAID RUN. Every page is one API call, and the token counts written to
usage.json come from the response rather than from any estimate.

SAME PROMPT, SAME PIXELS, SAME EFFORT LEVEL AS run_claude.py: responses.create
with an input_image data URL and a reasoning effort. A cross-provider
comparison is only meaningful if the provider is the only thing that differs,
and the easiest way to lose that is to let each adapter phrase its own
request.

THE MODEL ID IS NOT GUESSED. gpt-5.6-sol was confirmed callable by listing the
models this account can actually reach, rather than by trusting a name from
documentation or memory. Its price is in cloud_cost.py with the date it was
verified.

READ THE MODEL PAGE FOR MODALITY, NOT THE PRICE TABLE. The pricing page's own
"Images" column was wrong about the GPT-5 family when this was written -- it
implied the model could not take image input, which it plainly can, since that
is the whole of what this adapter does.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloud import PROMPT, _api_key, b64, drive, page_bytes, record  # noqa: E402

MODEL = "gpt-5.6-sol"
EFFORT = "medium"
MAX_TOKENS = 16000

_CLIENT = None


def client():
    global _CLIENT
    if _CLIENT is None:
        import openai
        _CLIENT = openai.OpenAI(api_key=_api_key("OPENAI_API_KEY"))
    return _CLIENT


def version() -> str:
    from importlib.metadata import version as v
    return f"{MODEL} (openai {v('openai')}), effort={EFFORT}"


def extract(job) -> str:
    resp = client().responses.create(
        model=MODEL,
        max_output_tokens=MAX_TOKENS,
        reasoning={"effort": EFFORT},
        input=[{
            "role": "user",
            "content": [
                {"type": "input_image",
                 "image_url": f"data:image/png;base64,{b64(page_bytes(job))}"},
                {"type": "input_text", "text": PROMPT},
            ],
        }],
    )
    u = resp.usage
    record(job, resp.model, u.input_tokens, u.output_tokens,
           getattr(resp, "status", None))
    # AN INCOMPLETE RESPONSE IS A TRUNCATED PAGE, NOT A BAD PARSER. If the
    # model ran out of output budget the transcription stops mid-page, and
    # grading that as recovery would report a token limit as an accuracy
    # finding. Raise so the record carries the error and score.py skips it.
    if getattr(resp, "status", None) == "incomplete":
        raise RuntimeError(f"incomplete: {getattr(resp, 'incomplete_details', None)}")
    return resp.output_text


if __name__ == "__main__":
    raise SystemExit(drive("gpt", version(), extract))
