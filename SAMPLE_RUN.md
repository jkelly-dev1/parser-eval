# SAMPLE_RUN

Captured output. Nothing here is retyped, tidied or reordered; the blocks are
what the commands printed on 2026-08-18, on Python 3.13.7 and pdftotext
25.03.0, from the commands shown above them exactly as shown.

TWO ALTERATIONS, AND THEY ARE THE ONLY TWO. `cloud_cost.py` prints the
absolute directory of each run; those paths appear here as `<repo>`, and you
will see your own. Long tables are cut where an explicit `...` marker says so
and nowhere else.

EVERY BLOCK BELOW IS FREE AND NEEDS NO NETWORK. The two hosted models are the
only part of this project that costs money, and none of it is re-run here --
their output is committed in `out_real/`, because those endpoints do not
return the same bytes twice and re-running them would produce different
numbers rather than reproduce these.

## The labels check themselves, before any parser is graded

105 arithmetic rules the six pages assert about themselves, plus 7 that run
between pages. This is the step that caught four of the author's own labeling
errors on the 1956 scan.

```
$ python3 reconcile.py --corpus real/pages
GROUND TRUTH FIRST. Every sum evaluated against the hand-labeled values.

  6 documents checked, 0 label errors found.

```

## Every parser, scored

`recovered` means the printed value came back in the right row. `textlayer` is
not a parser: it returns the text layer already inside the PDF and does no
work at all, in zero seconds.

```
$ python3 score.py --corpus real/pages --out out_real
parser            dpi  fields  recovered  absent  corrupt  typed  misplcd  quiet%      rows  s/page
---------------------------------------------------------------------------------------------------
claude            300     425      97.4%       1        9      6        1     64%    69/75     57.4
docling           300     425      63.3%      71       39     35       46     52%    49/75     18.4
gpt               300     425      97.9%       3        6      4        0     44%    75/75     64.1
marker            300     425      79.3%      64       16     12        8     23%    44/75    122.5
tesseract         300     425      57.2%     146       29     22        7     16%    73/75      1.3
textlayer         300     425      77.6%      88        7      4        0      4%    47/75      0.0
unstructured      300     425      63.8%      96       48     39       10     32%    42/75      6.6

recovered  the printed value came back, in the right row
absent     nothing like it came back           -- a hole, loud
corrupt    a same-shape look-alike came back
typed      of those, the ones a downstream cast would ACCEPT
           -- the rest carry a character the field cannot hold
           (a quantity read as '#'), and are loud
misplcd    the exact value came back in ANOTHER row -- quiet
quiet%     (typed + misplaced) / all misses

wrote out_real/scores.json
```

THREE OF SEVEN TOOLS LOSE TO DOING NOTHING. Docling, Unstructured and
Tesseract all score below the control, which is the finding this corpus was
built to be able to state.

## Does each parser's version still add up?

A parser can return a wrong figure and have the page still balance. That is a
quiet failure, and it is the thing this project exists to count.

```
$ python3 reconcile.py --corpus real/pages --scores out_real/scores.json
GROUND TRUTH FIRST. Every sum evaluated against the hand-labeled values.

  6 documents checked, 0 label errors found.

PARSERS. For each sum: does the parser's version still add up?

parser        page            holds  survives  broken  incomplete
-----------------------------------------------------------------
claude        census29_sales      2         0       0           0
claude        census29_wages      4         0       1           1
...  (30 more per-page rows)
unstructured  census29_wages      0         0       0           6
unstructured  fdic2023_balance     12         0       0           0
unstructured  fdic_balance        6         0       1           0
unstructured  fdic_earnings      16         1      10          42
unstructured  fdic_income         2         0       4           3

COHERENCE ACROSS PAGES. Every term from the SAME parser.

parser          holds  survives  broken  incomplete
---------------------------------------------------
claude              6         0       1           0
docling             6         0       1           0
gpt                 5         0       2           0
marker              6         0       1           0
tesseract           4         0       2           1
textlayer           6         0       1           0
unstructured        6         0       1           0

HOLDS       every figure in the sum came back right
SURVIVES    a figure came back WRONG and the sum still balances
BROKEN      a wrong figure breaks the sum: a cross-field rule catches it
INCOMPLETE  a figure is missing, so the check cannot run at all

wrote out_real/reconcile.json
```

COHERENCE ACROSS PAGES is the check no single page can perform: the 1956
balance sheet and income statement assert seven identities about each other,
and a parser can read both pages perfectly self-consistently and still
contradict itself between them.

## The control, re-run from scratch

The one parser in the comparison that can honestly be re-run anywhere: it
needs `pdftotext` and nothing else. This is what CI checks on every push.

```
$ python3 adapters/run_textlayer.py --corpus real/pages --out /tmp/textlayer
  fdic_balance_300      0.0s    6704 chars
  fdic_income_300       0.0s    7191 chars
  fdic_earnings_300     0.0s   11214 chars
  census29_wages_300    0.0s       1 chars
  census29_sales_300    0.0s       1 chars
  fdic2023_balance_300    0.0s    3499 chars

textlayer: 6 pages in 0.1s -> /tmp/textlayer

$ diff -r --exclude=manifest.json out_real/textlayer /tmp/textlayer
$ echo $?
0
```

Bit-for-bit identical to the committed output. `manifest.json` is excluded
because it records wall-clock seconds, which cannot match between two runs;
every file carrying a measurement is compared.

Note the two 1929 census schedules returning 1 character. They are photographs
of paper with no text layer at all, so the control has nothing to return and
scores 0.0% on both. That zero is the floor the other tools are measured
against.

## What the paid runs cost

Free to print: it reads the token counts already stored beside the hosted
output, and the prices carry the date they were verified.

```
$ python3 cloud_cost.py --all
prices verified 2026-08-11; re-verify before quoting these if that date is stale

<repo>/out/claude
...  (the two synthetic-corpus runs, 20 pages each)
<repo>/out_real/claude
  page                       in      out      cost
  fdic_balance_300         4948     1238   $0.0557
  fdic_income_300          4948     1691   $0.0670
  fdic_earnings_300        4948     2812   $0.0950
  census29_wages_300       4984     2631   $0.0907
  census29_sales_300       4984     1992   $0.0747
  fdic2023_balance_300     5002     1146   $0.0537
  -----------------------------------------------
  6 page(s)          29814    11510   $0.4368
  per page:   4969 in   1918 out   $0.0728

<repo>/out_real/gpt
  page                       in      out      cost
  fdic_balance_300         5411     2399   $0.0990
  fdic_income_300          5411     2430   $0.1000
  fdic_earnings_300        5411     4773   $0.1702
  census29_wages_300       5361     3701   $0.1378
  census29_sales_300       5361     2753   $0.1094
  fdic2023_balance_300     6286     1282   $0.0699
  -----------------------------------------------
  6 page(s)          33241    17338   $0.6863
  per page:   5540 in   2889 out   $0.1144

=================================================
  ALL RUNS: $1.8583
```

$1.12 for the six real pages across both providers. The earnings table is the
expensive one on both, because a 33x11 landscape table costs output tokens.

## The tests

44 tests, pure standard library, no network, about 20 seconds. Most pin a
specific way the grader or the arithmetic checker can be wrong.

```
$ python -m pytest -q
..........................................                               [100%]
44 passed in 21.20s
```

README.md maps each claim to the test that enforces it. Three of those tests
are mutation-checked: making `canon` strip accounting parentheses, dropping
`join_thousands`' trailing lookahead, and hand-editing one number in
`scores.json` each turn a passing test red.

They do not cover the hosted-model columns, and nothing can: those endpoints
do not return the same bytes twice, so their output is committed as evidence.
The regeneration test grades that committed output, which is the strongest
check available on a number that cannot be reproduced.
