#!/usr/bin/env bash
# Unstructured with the PDF/image extras into its own venv. Separate venv on
# purpose: unstructured, docling and marker pin overlapping heavy dependencies
# and a resolver conflict between two of them must not turn into "we could not
# run the third".
set -euo pipefail
cd "$(dirname "$0")"
P=envs/unstructured/bin/pip
"$P" install --upgrade pip >/dev/null
"$P" install --index-url https://download.pytorch.org/whl/cpu torch torchvision
"$P" install "unstructured[pdf]"
envs/unstructured/bin/python -c "import unstructured; print('unstructured', unstructured.__version__)"
