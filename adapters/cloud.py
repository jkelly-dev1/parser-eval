"""Shared plumbing for the two hosted vision models.

WHY THE TWO CLOUD ADAPTERS SHARE A FILE AND THE FOUR LOCAL ONES DO NOT. The
local parsers are genuinely different programs and each one is invoked the way
its own documentation says to. The two cloud models are the same operation
twice -- one image, one instruction, one block of text back -- and the only
thing a cross-provider comparison can afford to vary is the provider. So the
prompt, the pixels, the resize, the effort level and the output handling are
written once here and neither adapter is allowed its own version.

THE PROMPT IS THE INVOCATION, and for a model it is the entire configuration.
Docling has pipeline options; a VLM has a paragraph of English. It is quoted in
full below rather than assembled from fragments, so that anyone arguing with
the numbers can argue with the actual instruction that produced them.

CREDENTIALS ARE READ FROM THE FILE ENV_FILE POINTS AT, never from this repo,
never logged, and never passed on a command line. The key lives outside the
repository entirely and the runner sources it at call time, so nothing here
ever holds it and nothing here needs to be scrubbed before publishing.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import parse_args, run                              # noqa: E402

# EVERY PAGE IS SENT AT THE SAME PIXEL SIZE TO BOTH PROVIDERS. 2576 px on the
# long edge is Anthropic's high-resolution ceiling; anything larger is
# downscaled server-side, so sending more would mean the two providers were
# shown different images while the log claimed otherwise. Resizing here, once,
# keeps that honest.
#
# IT DOES NOT BOUND THE PAYLOAD, AND THE TWO ARE EASY TO CONFUSE. Only four of
# the six pages exceed 2576 on the long edge; the two 1929 schedules are 2408
# and 2424 and pass through at full size. They are therefore the LARGEST
# requests, not the smallest: census29_wages is 3.9 MB as sent and 5.2 MB once
# base64-encoded, against 0.7 MB for the born-digital page that does get
# resized. A page that arrives larger than these is not made safe by this
# constant.
LONG_EDGE = 2576

# THE ONE INSTRUCTION, VERBATIM. It asks for a transcription and not an
# extraction on purpose: score.py grades whether the values printed on the page
# came back as text, which is exactly what it asks the four local parsers. A
# prompt naming the fields would be asking the models an easier question than
# the parsers were asked, and the comparison would be worthless.
PROMPT = """Transcribe this document page completely and faithfully.

Rules:
- Output every piece of text that appears on the page, including headers,
  labels, form field names, table contents, footers and stamps.
- Preserve the reading order and the table structure. Render tables as
  Markdown tables, one row per line, so that values stay with their row.
- Transcribe handwritten entries as well as printed text. If a handwritten
  value is unclear, give your best reading rather than omitting it.
- Copy numbers, dates, reference numbers and codes exactly as printed, digit
  for digit. Do not reformat, round, or correct them.
- Do not summarize, do not describe the document, and do not add commentary.
  Output only the transcription."""

USAGE: list[dict] = []


def _api_key(var: str) -> str:
    """Read one credential from the environment, with a legible failure."""
    key = os.environ.get(var)
    if not key:
        raise SystemExit(
            f"{var} is not set. Run this through run_cloud.sh, which sources "
            f"the file ENV_FILE points at (default ~/.secrets/ai.env). The key "
            f"is never stored in this repo.")
    return key


def page_bytes(job: dict) -> bytes:
    """The page as PNG, resized so both providers see identical pixels."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    with Image.open(job["png"]) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = LONG_EDGE / max(w, h)
        if scale < 1:
            im = im.resize((round(w * scale), round(h * scale)),
                           Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()


def b64(png: bytes) -> str:
    return base64.standard_b64encode(png).decode("ascii")


def record(job: dict, model: str, in_tok: int, out_tok: int,
           stop: str | None) -> None:
    """Keep the per-page token counts so cost is MEASURED, not estimated.

    The two providers tokenize text differently and count visual tokens
    differently, so the same page is a different number of tokens on each.
    Price per token is not price per page, and the only honest cross-provider
    comparison is cost per document measured on one corpus. This is what makes
    that possible; cloud_cost.py turns it into dollars against dated prices.
    """
    USAGE.append({
        "doc_id": job["doc_id"], "dpi": job["dpi"], "model": model,
        "input_tokens": in_tok, "output_tokens": out_tok, "stop": stop,
    })


def drive(parser_name: str, version: str, extract) -> int:
    """Run the corpus, then write usage.json beside the manifest."""
    args = parse_args(parser_name)          # same argv, same answer as run()
    rc = run(parser_name, version, extract, source="png")
    (args.out / "usage.json").write_text(json.dumps(USAGE, indent=2) + "\n")
    tot_in = sum(u["input_tokens"] for u in USAGE)
    tot_out = sum(u["output_tokens"] for u in USAGE)
    print(f"tokens: {tot_in} in, {tot_out} out over {len(USAGE)} page(s)"
          f"  ->  {args.out / 'usage.json'}")
    return rc
