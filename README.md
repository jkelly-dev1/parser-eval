# parser-eval

Six document parsers, one grader, and an opinion about which errors you can
afford.

The tools are raw Tesseract, two layout-model-plus-OCR parsers (Docling and
Unstructured), a local vision-language model (Marker, running surya-2 through
llama.cpp on CPU), and two hosted ones (Claude Opus 5 and GPT-5.6-sol). A
seventh entry is not a parser at all: `textlayer` returns whatever text layer
is already inside the PDF, in zero seconds. It is the control, and on every
page that has a text layer it beats three of the four local tools. All seven
are invoked through one contract, over one frozen corpus, and graded by one
script.

> **Status: complete and unreviewed.** The machinery, the corpus and the
> results are all present. A real-document corpus is not usable here because
> its sources cannot be redistributed; this one ships with the code, and
> `Sample_Documents/PROVENANCE.txt` states the basis for every document.
> Nothing here has been reviewed by anyone but its author, and the numbers
> below should be read with that in mind.

## What makes this different from a parser leaderboard

A leaderboard reports accuracy. This grades every miss by **how it fails**:

| verdict | meaning | cost |
|---|---|---|
| `ABSENT` | nothing like the value came back | a hole, and anything downstream can see it |
| `CORRUPT` | a same-shape look-alike came back | expensive **if** it still parses as the field's type |
| `MISPLACED` | the exact value, attached to the wrong row | a well-formed record describing something else |

That split is the point. A parser with half the error rate and twice the
quiet-error fraction is the more dangerous one, and no single accuracy number
tells you which you have. `CORRUPT` is split again on whether the returned
characters could belong to that field at all: a quantity returned as `#` is a
same-shape look-alike and is loud the moment anything casts it.

`reconcile.py` asks the harder question of a corpus whose pages carry
arithmetic: when a parser gets a figure wrong, does the error **break a sum
the document asserts about itself**? Ground truth that checks itself is worth
looking for -- it verifies the labels before any parser is graded, and the same
arithmetic then becomes the loud-versus-quiet test.

## Results on the real corpus

Six real pages, 425 hand-labeled values, rendered at 300 DPI. Percentage of
values recovered **in the right row**. Full write-up in `FINDINGS.txt`.

| page | fields | gpt | claude | marker | **textlayer** | unstructured | docling | tesseract |
|---|---|---|---|---|---|---|---|---|
| fdic2023_balance * | 65 | 100.0% | 100.0% | 92.3% | **100.0%** | 95.4% | 95.4% | 92.3% |
| fdic_balance | 37 | 100.0% | 100.0% | 64.9% | **91.9%** | 89.2% | 91.9% | 78.4% |
| fdic_income | 40 | 92.5% | 92.5% | 42.5% | **87.5%** | 75.0% | 80.0% | 77.5% |
| fdic_earnings | 207 | 99.0% | 98.6% | 93.2% | **94.7%** | 63.3% | 50.2% | 52.2% |
| census29_wages | 44 | 93.2% | 88.6% | 38.6% | **0.0%** | 15.9% | 34.1% | 9.1% |
| census29_sales | 32 | 96.9% | 100.0% | 81.2% | **0.0%** | 25.0% | 68.8% | 34.4% |
| **corpus** | **425** | **97.9%** | **97.4%** | **79.3%** | **77.6%** | **63.8%** | **63.3%** | **57.2%** |
| seconds/page | | 64.1 | 57.4 | 122.5 | **0.0** | 6.6 | 18.4 | 1.3 |

\* born-digital. Every other page is a photograph of paper.

- **Three of seven tools lose to doing nothing.** `textlayer` is the control:
  it returns the text layer already in the file and does no work. On the
  born-digital page it scores 100% and ties the hosted models, and every tool
  that *processes* that page does worse. On the pages with an inherited OCR
  layer it beats Docling, Unstructured and Tesseract outright. Marker's and
  Docling's figures on the FDIC pages are a 99-100% subset of that layer --
  they are relaying it, not reading the page.
- **The same tool, 1000x slower, depending on the file.** Marker takes 0.4s on
  a page with a text layer and 405s on one without, because it only starts its
  vision model when it has to. Nothing in its interface tells you which run
  you are about to get.
- **Handwriting is a different problem.** On the 1929 hand-filled schedules
  Tesseract recovers 9.1% and the hosted models 88-100%. The tool family is
  the whole decision.
- **The quiet failures were real but rare.** Docling read two cells of one row
  as 945 and 285 where the page prints 935 and 295 -- errors of +10 and -10
  that cancel, so the row still adds up and the extraction passes. The hosted
  models produced **no** quiet failures: 6 broken sums, 0 survived.
- **Structure is a separate skill from reading.** Tesseract finds 73 of 75
  rows and recovers the least of any tool. Docling put 46 character-perfect
  values in the wrong row.
- **Cost.** $1.12 for the whole corpus, both hosted models: Claude
  $0.0728/page, GPT $0.1144/page. On the born-digital page that buys nothing,
  because the free control already scores 100%. On the handwritten page it
  buys the difference between 9% and 93%.

## Results on the generated corpus

Ten purchase orders, rendered at 150 and 300 DPI, 342 graded values per run.
These predate the real corpus and are kept because they isolate resolution,
which the real corpus (300 DPI only) does not test:

| parser | 150 DPI | 300 DPI | quiet share of misses @150 |
|---|---|---|---|
| claude-opus-5 | 100.0% | 100.0% | -- (no misses) |
| gpt-5.6-sol | 98.8% | 100.0% | 100% |
| docling | 99.7% | 99.1% | 100% |
| marker | 99.3%[1] | 100.0%[1] | 100% |
| unstructured | 71.9% | 72.8% | 28% |
| tesseract | 49.7% | 96.8% | 66% |

[1] partial: Marker hangs on this hardware and could be driven through 4 of 10
documents at 150 DPI and 3 of 10 at 300. One content error in 267 values.

- **Resolution is the whole story for raw OCR.** Tesseract nearly doubles
  between 150 and 300 DPI on identical pages, and its 150 DPI failures are
  mostly quiet: 113 of 172 misses still parse as the value they replaced,
  including a date four days wrong.
- **The VLMs have no 150 DPI cliff.** Claude scores 342 of 342 at both.
  GPT's only four errors are all at 150 and all the same mistake -- an
  *inserted* character (`PO-17733` -> `PO-117733`), which is a different
  failure from OCR's confusion of similar glyphs.
- **The hosted models are not reproducible and the local one is.** The same
  page twice: Marker returns identical bytes; the two hosted endpoints
  disagree with themselves. That points at inference configuration, not
  architecture.

## Claims backed by tests

The rule this repo follows: no claim without a test. 44 tests, pure standard
library, no network, about 20 seconds. Most of them pin a specific way the
GRADER or the ARITHMETIC CHECKER can be wrong rather than anything about a
parser, which is what a comparison project should expect: the instrument is
the part most likely to be measuring the wrong thing.

| Claim | Test |
| --- | --- |
| Accounting parentheses are read as the minus sign | `tests/test_grader.py::test_accounting_parentheses_are_read_as_the_minus_sign` (mutation-checked: make `canon` strip parens and it fails) |
| A loss with its sign discarded is still scored wrong | `tests/test_grader.py::test_a_loss_with_its_sign_discarded_is_still_wrong` (mutation-checked with the same edit) |
| A positive figure ending a sentence is not a negative | `tests/test_grader.py::test_a_positive_figure_ending_a_sentence_is_not_a_negative` |
| A parenthesized figure survives tokenization intact | `tests/test_grader.py::test_a_parenthesized_figure_survives_tokenization_intact` |
| A colon with no space after it does not hide a value | `tests/test_grader.py::test_tokens_split_on_a_colon_with_no_space_after_it` |
| An HTML entity is not scored as a corrupted character | `tests/test_grader.py::test_an_html_entity_is_not_scored_as_a_corrupted_character` |
| Space-separated thousands join into one number | `tests/test_grader.py::test_thousands_separated_by_spaces_join_into_one_number` |
| But two adjacent cells are never welded into one number | `tests/test_grader.py::test_but_two_adjacent_cells_are_never_welded_into_one_number` (mutation-checked: drop the trailing lookahead and it fails) |
| Formatting that carries no information is stripped | `tests/test_grader.py::test_formatting_that_carries_no_information_is_stripped` |
| A leading minus is never stripped | `tests/test_grader.py::test_but_a_leading_minus_is_never_stripped` |
| Every sum each page asserts holds against the hand labels | `tests/test_reconcile.py::test_every_sum_each_page_asserts_holds_against_the_hand_labels` |
| The rules that RAN are counted, not just the ones that passed | `tests/test_reconcile.py::test_the_rules_that_ran_are_counted_not_just_the_ones_that_passed` |
| An unparseable figure fails one value, not the whole run | `tests/test_reconcile.py::test_an_unparseable_figure_raises_rather_than_crashing_the_whole_run` |
| A label that merely contains a digit is not a figure | `tests/test_reconcile.py::test_a_label_that_merely_contains_a_digit_is_not_a_figure` (mutation-checked: drop the letter guard in `num` and it fails) |
| A digit misread as a letter is unparseable, not a smaller number | `tests/test_reconcile.py::test_a_digit_misread_as_a_letter_is_unparseable_not_a_smaller_number` (mutation-checked with the same edit) |
| The seven identities between pages hold | `tests/test_cost_and_coherence.py::test_the_identities_between_pages_hold_against_the_labels` |
| Every page ships its document, its render and its labels | `tests/test_corpus.py::test_every_page_ships_its_document_its_render_and_its_labels` |
| Every source document has a statement of rights | `tests/test_corpus.py::test_every_source_document_has_a_statement_of_rights` |
| The control recovers nothing where there is no text layer | `tests/test_corpus.py::test_the_control_recovers_nothing_where_there_is_no_text_layer` |
| The control does recover text where there is one | `tests/test_corpus.py::test_the_control_does_recover_text_where_there_is_a_layer` |
| The published scores regenerate from the published output | `tests/test_corpus.py::test_published_scores_regenerate_from_the_published_parser_output` (mutation-checked: edit one number in `scores.json` and it fails) |
| The corpus is six pages and 425 labeled values | `tests/test_corpus.py::test_the_corpus_is_six_pages_and_425_labeled_values` |
| A model with no price is reported unpriced, not charged zero | `tests/test_cost_and_coherence.py::test_a_model_with_no_price_is_reported_unpriced_not_charged_zero` |
| A dated model snapshot prices as its base model | `tests/test_cost_and_coherence.py::test_a_dated_snapshot_prices_as_its_base_model` |
| Prices carry the date they were verified | `tests/test_cost_and_coherence.py::test_prices_carry_the_date_they_were_verified` |

WHAT THESE TESTS DO NOT COVER, because saying so is the point of the project:
the hosted-model columns. Those endpoints do not return the same bytes twice,
so their output is committed as evidence rather than regenerated -- and the
regeneration test above grades that committed output, which is the strongest
check available on a number that cannot be reproduced.

```
pip install "pytest>=8,<10"
python -m pytest -q
```

## Layout

```
FINDINGS.txt      what the numbers mean. Read this before quoting them.
score.py          the grader. One code path for every corpus.
reconcile.py      does a parser's error break the document's own arithmetic?
cloud_cost.py     what the hosted runs cost, from their own usage figures
build_real.py     cuts graded pages out of source documents
build_scan.py     re-renders pages as image-only PDFs at both resolutions
adapters/         one per parser, all honoring the same contract
adapters/run_textlayer.py
                  THE CONTROL: returns the text layer already in the PDF and
                  does no work. Run it first; a parser that cannot beat it on
                  a given page is not earning its seconds.
run_cloud.sh      runs a hosted model; sources the key from ENV_FILE
```

## Running it

Each local parser gets its own virtualenv, because their dependencies
conflict:

```
./install_docling.sh
./install_unstructured.sh
./install_marker.sh
```

Then build the corpus and run parsers over it. Every adapter takes the same
arguments:

```
python3 adapters/run_tesseract.py
envs/docling/bin/python adapters/run_docling.py
python3 score.py
```

The hosted models need a key, read from the file `ENV_FILE` points at
(default `~/.secrets/ai.env`) and never stored here:

```
./run_cloud.sh claude --out out/claude
python3 cloud_cost.py --all
```

## What the corpus was required to have, and where each requirement landed

The first corpus was thrown away and this one was specified before it was
built, from four properties -- these being what had actually separated the
tools rather than what a corpus is usually assumed to need. All four are in
the shipped six pages, and each one earns its place by a result that would be
missing without it.

1. **Handwriting on a poor scan.** `census29_wages` and `census29_sales`, two
   1929 Census of Manufactures schedules filled in by hand in pencil, with
   struck-through corrections and marginal notes in other hands. THIS IS THE
   PROPERTY THAT DIVIDES THE TOOL FAMILIES RATHER THAN RANKING THEM: on the
   wages sheet, GPT 93.2% and Claude 88.6% against Marker 38.6%, Docling
   34.1%, Unstructured 15.9%, Tesseract 9.1% -- and the control 0.0%, because
   there is no text layer to return. A corpus without a page like this
   collapses into "everything works".
2. **Internal arithmetic.** 105 rules the pages assert about themselves, plus
   7 identities that run between pages, all holding against the hand labels.
   This is what makes the ground truth verified rather than careful, and it
   was not decorative: four labels were typed wrong and the arithmetic caught
   all four.
3. **A born-digital page with a text layer.** `fdic2023_balance`, page 134 of
   the FDIC's 2023 annual report -- and it is the same publication as the 1956
   balance sheet, 67 years apart, which is closer to a controlled comparison
   than a corpus of real documents usually gets. It answered its question
   sharply: the control scores 100% there, ties both hosted models, and beats
   every local parser -- Docling and Unstructured 95.4%, Marker and Tesseract
   92.3%.
4. **A dense multi-column table.** `fdic_earnings`, Table 114, 33 rows by 11
   numeric columns printed landscape on a portrait page. It carries 69 of the
   105 rules on its own, in two directions, and it is where the spread is
   widest -- GPT 99.0% down to Docling 50.2%.

Documents had to be unambiguously redistributable, and the bar was a positive
statement of rights rather than the absence of a prohibition. Works of the US
federal government are not subject to copyright and proved to be the cleanest
source of dense financial tables.

THE HANDWRITING REQUIREMENT WAS THE HARD ONE, AND NOT FOR THE REASON EXPECTED.
The obstacle was never copyright; it was privacy. The handwriting that is easy
to find is genuine records carrying private individuals' hands -- population
schedules, draft cards, ship manifests -- public domain and still somebody's
personal data. The fallback plan was to manufacture a page: print a
public-domain form, fill it in, photocopy it crooked. That was not needed. The
1929 schedules are real records about BUSINESSES rather than households,
released by the National Archives with neither an access nor a use
restriction, so the corpus gets genuine handwriting without publishing anyone's
private information and without staging the difficulty.
`Sample_Documents/PROVENANCE.txt` argues the rights one document at a time.

## A caveat that belongs in the open

The grader was wrong before it was right, repeatedly, and always in the
direction of the interesting answer. Every matching rule in `score.py` exists
because some parser's output format was being scored as damage -- HTML tags,
HTML entities, Markdown escapes, diacritics, digit regrouping. If you add a
seventh parser, **assume the first run measures its serializer** rather than
its accuracy, and read its raw output next to the verdict before believing
either.

## Related repositories

One of sixteen small projects, each measuring one thing and publishing where it
fails:
[prompt-injection-benchmark](https://github.com/jkelly-dev1/prompt-injection-benchmark),
[ai-data-boundary-proxy](https://github.com/jkelly-dev1/ai-data-boundary-proxy),
[agentic-review-gate](https://github.com/jkelly-dev1/agentic-review-gate),
[temporal-multi-agent](https://github.com/jkelly-dev1/temporal-multi-agent),
[federated-retrieval-router](https://github.com/jkelly-dev1/federated-retrieval-router),
[vlm-extraction-integrity](https://github.com/jkelly-dev1/vlm-extraction-integrity),
[llm-observability-stack](https://github.com/jkelly-dev1/llm-observability-stack),
[ai-compliance-checker](https://github.com/jkelly-dev1/ai-compliance-checker),
[airgapped-ai-bundle](https://github.com/jkelly-dev1/airgapped-ai-bundle),
[agent-sandbox-escape](https://github.com/jkelly-dev1/agent-sandbox-escape),
[hardened-mcp-server](https://github.com/jkelly-dev1/hardened-mcp-server),
[llm-eval-gate](https://github.com/jkelly-dev1/llm-eval-gate),
[least-privilege-agent](https://github.com/jkelly-dev1/least-privilege-agent),
[citation-abstention-rag](https://github.com/jkelly-dev1/citation-abstention-rag),
[typed-agent-service](https://github.com/jkelly-dev1/typed-agent-service).

Two are worth reading directly against this one.
[vlm-extraction-integrity](https://github.com/jkelly-dev1/vlm-extraction-integrity)
asks the next question down the pipeline: given that a value came off the page,
which defenses catch it when it is WRONG. It measures eight cumulative
validation rungs against fourteen error classes on synthetic pages it generates
itself. This one measures whether the value comes off the page at all, on real
documents it did not get to design -- and the two choices of corpus are the
trade being made. A generated page can be made to contain exactly the error you
want to study; a 1956 scan contains the errors it contains, and four of the
labels here were wrong until the page's own arithmetic caught them.
[llm-eval-gate](https://github.com/jkelly-dev1/llm-eval-gate)
shares this one's central worry from the other end. It measures its own judges
before it trusts their verdicts, and refuses to gate inside their noise floor.
The errors here concentrate in the grader rather than in the parsers, which is
the same finding arrived at from the other end: THE INSTRUMENT IS PART OF THE
EXPERIMENT, and it is the part nobody tests.

## License

MIT. See `LICENSE`.
