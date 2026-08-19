# Security notes

## What this repository contains

Six pages cut from four public-domain documents, 425 hand-labeled values, the
raw output of seven parsers over those pages, and the scripts that grade and
reconcile them. There is no service here, nothing listens on a port, and
nothing is deployed anywhere.

What a security reader should note is that this repository ships the documents
themselves, which most benchmarks do not. That is a deliberate choice with a
rights obligation attached, and it is discharged in
`Sample_Documents/PROVENANCE.txt`.

## Document rights

Every document here is a work of the United States Government, a pre-1930
publication, or both. `Sample_Documents/PROVENANCE.txt` states the basis for
each one individually, names the source, and records where a rights statement
could not be read from the publisher and what was relied on instead.

The bar applied was a positive statement of rights, not the absence of a
prohibition. Three candidate documents were rejected for failing it and the
reasons are recorded, including one on a `.gov` domain that turned out to be
contractor work with a third-party cover photograph. A `.gov` URL is not a
statement of rights.

One document carries handwriting. The 1929 Census of Manufactures schedules are
federal records released by the National Archives with neither an access nor a
use restriction, and they are schedules about businesses rather than households.
That is why they are here and the population schedules that are far easier to
find are not. They do carry the hand and signatures of people who filled a form
in 1929. That is stated in PROVENANCE.txt rather than left for a reader to
discover.

If you believe a document here should not be redistributed, that is the issue
worth opening first.

## Credentials

The two hosted-model adapters read their key from the environment, and
`run_cloud.sh` populates that environment by sourcing the file `ENV_FILE`
points at, defaulting to `~/.secrets/ai.env`:

    ENV_FILE=~/.secrets/ai.env ./run_cloud.sh claude --corpus real/pages --out out_real/claude

No key is stored in this repository, none is written to any file under `out/`
or `out_real/`, none is logged, and none is ever passed on a command line.
`adapters/cloud.py` fails with a legible message naming the variable rather
than sending an unauthenticated request.

Be aware of one thing this does not do. It reads the key from the process
environment, so a key already exported in your shell will be used. It does not
insist that the key come from `ENV_FILE`. If you keep more than one key around,
set `ENV_FILE` explicitly and check which account a run billed.

## Spending

The paid path is one API call per page and lives in a separate script. Nothing
in the default workflow calls a model. `score.py`, `reconcile.py`,
`cloud_cost.py` and the `textlayer` control are free, need no network, and
reproduce every published number except the two hosted columns.

There is no pre-flight cost guard, and you should know that before running
it. `run_cloud.sh` has no `--confirm` flag, no estimate-and-exit default and
no spending cap. It starts calling the API when you run it. Cost is reported
after the fact by `cloud_cost.py`, computed from the responses' own token counts
against prices carrying the date they were verified. On this six-page corpus a
full run of both providers was $1.12; `--only <doc_id>` and `--limit N` are the
way to spend less than that.

## The hosted runs cannot be regenerated

`out_real/claude` and `out_real/gpt` are evidence rather than build output. They
cost money, and this project's own finding is that the two endpoints do not
return the same bytes twice. Re-running them does not reproduce the published
numbers; it produces different ones. They are committed for that reason, and
`.gitignore` says so.

## Reporting

Issues are disabled on this repository, so neither of the two channels below is
a public thread.

For a SECURITY concern, use GitHub's private vulnerability reporting: the
"Report a vulnerability" button on the Security tab. It opens an advisory
visible only to the maintainer, and it is the same channel every repository in
this portfolio uses.

For a FACTUAL correction, a wrong number, a mislabeled value, a rights argument
that does not hold, open a pull request. This is a demonstration and a personal
learning project: not deployed, no users, no data belonging to anyone. A wrong
number here is the defect that matters, and this repository's whole subject is
measurements that look right and are not.
