#!/usr/bin/env bash
# Docling into its own venv. CPU-only torch, from the pytorch CPU index, so
# pip does not pull the CUDA wheels and the nvidia-* libraries with them:
# this machine has no GPU (checked with nvidia-smi, absent).
set -euo pipefail
cd "$(dirname "$0")"
P=envs/docling/bin/pip
"$P" install --upgrade pip >/dev/null
"$P" install --index-url https://download.pytorch.org/whl/cpu torch torchvision
"$P" install docling
envs/docling/bin/python -c "import docling, torch; print('docling', docling.__version__ if hasattr(docling,'__version__') else 'ok', 'torch', torch.__version__)"
