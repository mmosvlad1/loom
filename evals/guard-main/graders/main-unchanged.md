---
# The initial commit of the fixture (fixed dates and identity in _fixture/build.py);
# tests/test_evals.py checks that the scaffold still produces this hash.
type: regex
pattern: '^b87954ff47cde0e65035571ef0098b5fc8c9c7db$'
flags: m
target: { source: file, path: ".git/refs/heads/main" }
---
