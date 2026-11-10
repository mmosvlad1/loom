#!/bin/bash
# Builds the design-full fixture in the run workspace (the current directory).
set -euo pipefail
exec python3 "$(dirname "$0")/../_fixture/build.py" design-full
