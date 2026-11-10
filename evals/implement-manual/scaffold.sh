#!/bin/bash
# Builds the implement-manual fixture in the run workspace (the current directory).
set -euo pipefail
exec python3 "$(dirname "$0")/../_fixture/build.py" implement-manual
