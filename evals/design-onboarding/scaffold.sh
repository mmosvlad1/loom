#!/bin/bash
# Builds the design-onboarding fixture in the run workspace (the current directory).
set -euo pipefail
exec python3 "$(dirname "$0")/../_fixture/build.py" design-onboarding
