#!/usr/bin/env bash
# Marker (marker-pdf) into its own venv, CPU torch first for the same reason
# as the other two. Marker WANTS A GPU; section 4a of the next-projects file
# flags it as the parser that may have to be reported as "not run, and why".
# This script finds out which it is rather than assuming.
set -euo pipefail
cd "$(dirname "$0")"
P=envs/marker/bin/pip
"$P" install --upgrade pip >/dev/null
"$P" install --index-url https://download.pytorch.org/whl/cpu torch torchvision
"$P" install marker-pdf
envs/marker/bin/python -c "import marker, torch; print('marker ok, torch', torch.__version__)"
