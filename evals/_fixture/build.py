#!/usr/bin/env python3
"""Build the fixture repository of one loom eval scenario in the current directory.

Usage: build.py <scenario>

Every case's scaffold script calls this file. `claude plugin eval --scaffold`
runs the scaffold in the empty run workspace (the agent's working directory)
with a minimal environment: PATH, a temporary HOME, TMPDIR, TERM=dumb, and a
120-second limit. The script needs only `python3` (3.9+, standard library) and
`git`.

The fixture is a tiny Python shop (`shop/`) with stdlib unittest checks, a
`.claude/loom.json` as in LOOM_SPEC.md section 19.1, a git repository with one
commit on `main`, and the task directory of one prepared task (#7, "Add bulk
discount tiers to order pricing"). Commit dates and identities are fixed, so
the commit hashes are the same on every run.

Scenarios:
  research-full     full mode, branch feat/7-..., 01-research-questions.md approved; a style guide and one
                    HTML screen at the default paths, and a `## Screens` section in the ticket
  design-full       full mode, research approved; the style guide, the screen, and the ticket section
                    of research-full
  implement-manual  quick mode, plan approved; implementation phase 1 has a Manual line
  guard-main        on main with a staged change and no task
  describe-pr-quick quick mode, both implementation phases done and committed, no remote, no PR;
                    loom.json maps docs.tasks to notes/loom-tasks and requires the PR section ## Test plan
  design-onboarding the onboarding task #1 (setup task, full mode) on chore/1-loom-setup after the kickoff
                    commit, research approved; AGENTS.md without CLAUDE.md, a CI job named `test`
  screens-local     the screens task #12 (oneshot) on docs/12-loom-screens, cut from main without a commit;
                    a brief with one screen and its states in the Scope, the Audience, References `none`,
                    and a chosen direction; no style guide and no screen in the repository
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional

TASK = "7-bulk-discount-tiers"
BRANCH = "feat/" + TASK
TASK_DIR = os.path.join(".loom", "tasks", TASK)
ISSUE_URL = "https://github.com/example/shop/issues/7"
UPDATED = "2026-11-09"

# LOOM_SPEC.md section 19.1, verbatim.
LOOM_JSON = {
    "version": 1,
    "tracker": "github",
    "mainBranch": "main",
    "workDir": ".loom/tasks",
    "docsDir": "docs",
    "checks": {
        "lint": "make lint",
        "typecheck": "make typecheck",
        "test": "make test",
        "check": "make check",
    },
    "hooks": {"stopLint": False, "maxCheckAttempts": 3},
    "rounds": {"cap": {"S": 2, "M": 3, "L": 5}},
    "implement": {"maxFixAttempts": 2, "autoAdvance": True},
}

# describe-pr-quick adds optional keys of LOOM_SPEC.md 19.1: a docs map with a
# non-default `tasks` path outside docsDir, and one required PR section. It keeps
# the default `docs.decisions`: the fixture has no decision with `ADR? = yes`.
DESCRIBE_PR_LOOM_JSON = dict(LOOM_JSON, docs={"tasks": "notes/loom-tasks"},
                             pullRequest={"requiredSections": ["## Test plan"]})

# ---------------------------------------------------------------------------
# Project files (committed on main)
# ---------------------------------------------------------------------------

CART_PY = '''\
"""Shopping cart: items and quantities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Item:
    sku: str
    name: str
    unit_price: float


@dataclass
class Cart:
    items: Dict[str, Item] = field(default_factory=dict)
    quantities: Dict[str, int] = field(default_factory=dict)

    def add(self, item: Item, quantity: int = 1) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.items[item.sku] = item
        self.quantities[item.sku] = self.quantities.get(item.sku, 0) + quantity

    def remove(self, sku: str) -> None:
        self.items.pop(sku, None)
        self.quantities.pop(sku, None)

    def item_count(self) -> int:
        return sum(self.quantities.values())

    def subtotal(self) -> float:
        return sum(self.items[sku].unit_price * qty for sku, qty in self.quantities.items())
'''

PRICING_PY = '''\
"""Order pricing: discount codes and totals."""
from __future__ import annotations

from typing import Optional

from shop.cart import Cart

DISCOUNT_CODES = {
    "WELCOME10": 0.10,
    "VIP20": 0.20,
}

TAX_RATE = 0.08


def code_discount(code: Optional[str]) -> float:
    """Return the discount rate of a code, or 0.0 for no code or an unknown code."""
    if not code:
        return 0.0
    return DISCOUNT_CODES.get(code.upper(), 0.0)


def order_total(cart: Cart, code: Optional[str] = None) -> float:
    """Subtotal minus the code discount, plus tax, rounded to cents."""
    discounted = cart.subtotal() * (1 - code_discount(code))
    return round(discounted * (1 + TAX_RATE), 2)
'''

RECEIPT_PY = '''\
"""Plain-text receipts."""
from __future__ import annotations

from typing import List, Optional

from shop.cart import Cart, Item
from shop.pricing import code_discount, order_total


def format_receipt(cart: Cart, code: Optional[str] = None) -> str:
    lines: List[str] = []
    for sku, qty in sorted(cart.quantities.items()):
        item = cart.items[sku]
        lines.append("%-20s %3d x %8.2f" % (item.name, qty, item.unit_price))
    rate = code_discount(code)
    if rate:
        lines.append("Discount %s: -%d%%" % (code.upper(), round(rate * 100)))
    lines.append("Total: %.2f" % order_total(cart, code))
    return "\\n".join(lines)


def demo() -> str:
    cart = Cart()
    cart.add(Item("A1", "Notebook", 3.50), 12)
    cart.add(Item("B2", "Pen", 1.25), 40)
    return format_receipt(cart, "WELCOME10")


if __name__ == "__main__":
    print(demo())
'''

TEST_CART_PY = '''\
import unittest

from shop.cart import Cart, Item


class CartTest(unittest.TestCase):
    def test_add_accumulates_quantity(self):
        cart = Cart()
        cart.add(Item("A1", "Notebook", 3.50), 2)
        cart.add(Item("A1", "Notebook", 3.50), 3)
        self.assertEqual(cart.quantities["A1"], 5)
        self.assertEqual(cart.item_count(), 5)

    def test_add_rejects_non_positive_quantity(self):
        with self.assertRaises(ValueError):
            Cart().add(Item("A1", "Notebook", 3.50), 0)

    def test_subtotal(self):
        cart = Cart()
        cart.add(Item("A1", "Notebook", 3.50), 2)
        cart.add(Item("B2", "Pen", 1.25), 4)
        self.assertAlmostEqual(cart.subtotal(), 12.0)


if __name__ == "__main__":
    unittest.main()
'''

TEST_PRICING_PY = '''\
import unittest

from shop.cart import Cart, Item
from shop.pricing import code_discount, order_total
from shop.receipt import format_receipt


class PricingTest(unittest.TestCase):
    def test_unknown_code_has_no_discount(self):
        self.assertEqual(code_discount("NOPE"), 0.0)
        self.assertEqual(code_discount(None), 0.0)

    def test_code_is_case_insensitive(self):
        self.assertEqual(code_discount("welcome10"), 0.10)

    def test_order_total_applies_code_and_tax(self):
        cart = Cart()
        cart.add(Item("A1", "Notebook", 10.0), 1)
        self.assertEqual(order_total(cart, "VIP20"), 8.64)

    def test_receipt_lists_items_and_total(self):
        cart = Cart()
        cart.add(Item("A1", "Notebook", 10.0), 1)
        text = format_receipt(cart)
        self.assertIn("Notebook", text)
        self.assertIn("Total: 10.80", text)


if __name__ == "__main__":
    unittest.main()
'''

MAKEFILE = '''\
# Checks of the fixture shop. Standard library only, so evals need no uv or ruff.
PYTHON ?= python3

.PHONY: lint typecheck test check

lint:
\t$(PYTHON) -B -c "import ast, glob; [ast.parse(open(p).read(), p) for p in glob.glob('shop/*.py') + glob.glob('tests/*.py')]"

typecheck:
\t@echo "typecheck: no type checker in this fixture"

test:
\t$(PYTHON) -B -m unittest discover -s tests -t .

check: lint typecheck test
'''

README_MD = '''\
# shop

A tiny shop library: a cart, discount codes, and receipts.

Run the checks with `make check`.
'''

GITIGNORE = ".loom/\n__pycache__/\n"

# UI design files at the default paths of the docs roles `style` and `screens` (LOOM_SPEC.md 9.14.1),
# for research-full and design-full. The screen is a plain HTML page with inline styles (9.14.3).
STYLE_GUIDE_PATH = "docs/design/DESIGN.md"
SCREEN_PATH = "docs/design/screens/order-summary.html"

STYLE_GUIDE_MD = '''\
# Style guide

## Direction

Plain ledger. Calm and quiet, like a printed paper slip; numbers line up in one column.

## Colors

- `ink: #1f2933`: text
- `paper: #fdfcf8`: page background
- `accent: #2f6f4f`: discount lines
- `rule: #d9d4c7`: separators

## Typography

- Families: `"IBM Plex Mono", monospace`
- `body`: 14px/20px, 400
- `total`: 18px/24px, 600

## Spacing and shape

- Spacing scale: `space-1` 4px, `space-2` 8px, `space-3` 16px
- Radius: none. Borders: 1px `rule`. No shadows.

## States

- Empty: one muted line "No items".
- Error: the line in `ink`, with an icon.

## Rules

- Do: right-align every amount.
- Do not: use more than one accent color.
'''

# The marker phrase of the research-full grader screen-content-absent: it occurs only in this
# screen file (tests/test_evals.py checks this). It sits on the line of the bulk discount, so a
# content search for "bulk" or "discount" that reaches the screen puts it into the trace.
SCREEN_MARKER = "Quillfeather Stationers"

SCREEN_HTML = '''\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Order summary</title>
<style>
  body { background: #fdfcf8; color: #1f2933; font: 14px/20px "IBM Plex Mono", monospace; }
  .slip { max-width: 360px; margin: 16px auto; border: 1px solid #d9d4c7; padding: 16px; }
  .line { display: flex; justify-content: space-between; }
  .accent { color: #2f6f4f; }
  .total { font-size: 18px; line-height: 24px; font-weight: 600; }
</style>
</head>
<body>
<main class="slip">
  <div class="line"><span>Notebook x 12</span><span>42.00</span></div>
  <div class="line"><span>Pen x 40</span><span>50.00</span></div>
  <div class="line accent" title="{marker}"><span>Bulk discount: -10%</span><span>-9.20</span></div>
  <div class="line total"><span>Total</span><span>89.42</span></div>
</main>
</body>
</html>
'''.replace("{marker}", SCREEN_MARKER)

DESIGN_FILES = {STYLE_GUIDE_PATH: STYLE_GUIDE_MD, SCREEN_PATH: SCREEN_HTML}

# The `## Screens` section of the issue format (LOOM_SPEC.md 9.14.4), appended to the ticket body.
TICKET_SCREENS = "\n## Screens\n\n- `%s`\n" % SCREEN_PATH

# ---------------------------------------------------------------------------
# Task artifacts (in .loom/, ignored by git)
# ---------------------------------------------------------------------------

TICKET_BODY = '''\
# Add bulk discount tiers to order pricing

Labels: type:feat, size:M, mode:{mode}
URL: {url}

Wholesale customers buy notebooks and pens in large quantities. Give them an
automatic bulk discount: 5% off for 10 or more items in the cart, 10% off for
50 or more items. Show the bulk discount on the receipt. When a discount code
also applies, the larger of the two discounts wins.
'''

RESEARCH_QUESTIONS_BODY = '''\
# Research Questions

## Key Context Pointers

- Paths: shop/pricing.py, shop/cart.py, shop/receipt.py

## Questions

1. How does `shop/pricing.py` compute an order total today, and which functions and modules call it?
2. How does `shop/cart.py` store items and quantities, and which modules read them?
3. How does `shop/receipt.py` build the receipt text, and which tests cover the receipt and pricing code?
'''

RESEARCH_BODY = '''\
# Research

## Summary

The shop has three modules. `Cart` holds items and quantities in two dicts keyed by SKU (`shop/cart.py:16-18`). `order_total` applies one code discount to the cart subtotal, then adds tax (`shop/pricing.py:23-26`). `format_receipt` prints one line per item, an optional discount line, and the total (`shop/receipt.py:10-19`).

## Findings

### 1. The order total is the subtotal minus one code discount, plus 8% tax

Question: How does `shop/pricing.py` compute an order total today, and which functions and modules call it?

Discount codes live in the `DISCOUNT_CODES` dict (`shop/pricing.py:8-11`). `code_discount` returns the rate of a code, case-insensitively, or `0.0` (`shop/pricing.py:16-20`). `order_total` multiplies the subtotal by `1 - rate`, adds `TAX_RATE` (`shop/pricing.py:13`), and rounds to cents (`shop/pricing.py:23-26`). `format_receipt` is the only caller in `shop/` (`shop/receipt.py:15-18`).

#### Testing patterns

`tests/test_pricing.py:8-26` holds stdlib `unittest` tests with literal carts; no fixtures or mocks.

### 2. The cart keeps items and quantities in two dicts keyed by SKU

Question: How does `shop/cart.py` store items and quantities, and which modules read them?

`Cart.add` validates the quantity and accumulates it per SKU (`shop/cart.py:20-24`). `item_count` sums all quantities (`shop/cart.py:30-31`). `subtotal` multiplies unit prices by quantities (`shop/cart.py:33-34`). `shop/pricing.py:25` and `shop/receipt.py:12-14` read the cart.

#### Testing patterns

`tests/test_cart.py:6-22` covers accumulation, validation, and the subtotal.

### 3. The receipt prints items, an optional discount line, and the total

Question: How does `shop/receipt.py` build the receipt text, and which tests cover the receipt and pricing code?

`format_receipt` sorts items by SKU, prints a discount line only when the code has a rate, and ends with the total (`shop/receipt.py:10-19`). `demo` builds a sample cart for `python3 -m shop.receipt` (`shop/receipt.py:22-26`).

#### Testing patterns

`tests/test_pricing.py:21-26` checks the item line and the total of one receipt.

## Patterns & Conventions

- Modules start with a one-line docstring and `from __future__ import annotations` (`shop/pricing.py:1-2`).
- Money values are floats, rounded only in `order_total` (`shop/pricing.py:26`).

## External Sources

None.

## Not Found / Unclear

None.
'''


PLAN_BODY = '''\
# Plan

## Phase Overview

- [ ] 1. Bulk discount tiers on totals and receipts, verifiable via make check
- [ ] 2. Larger of code and bulk discount wins, verifiable via make check

## Open Questions

None.

## Resolved Decisions

| # | Question | Decision | Rationale | Round | ADR? |
|---|---|---|---|---|---|

## Phase 1: Bulk discount tiers

### Goal

`order_total` applies a bulk discount of 5% from 10 items and 10% from 50 items, and the receipt shows it. Discount codes are ignored when a bulk tier applies.

### Changes

```text
shop/
├── pricing.py    # changed: add bulk_discount(item_count) -> float; order_total uses it
└── receipt.py    # changed: print "Bulk discount: -<n>%" when a tier applies
tests/
└── test_pricing.py  # changed: tests for both tiers and the receipt line
```

```python
BULK_TIERS = ((50, 0.10), (10, 0.05))

def bulk_discount(item_count: int) -> float: ...
```

### Verification

- [ ] Automated: make check
- [ ] Manual: run `python3 -m shop.receipt` and confirm that the demo receipt shows `Bulk discount: -10%` on its own line, above the total

## Phase 2: Larger discount wins

### Goal

When a discount code and a bulk tier both apply, `order_total` uses the larger rate, and the receipt names only that discount.

### Changes

```text
shop/
├── pricing.py    # changed: order_total takes max(code rate, bulk rate)
└── receipt.py    # changed: print only the discount that applies
tests/
└── test_pricing.py  # changed: tests for code vs bulk precedence
```

### Verification

- [ ] Automated: make check
'''

# ---------------------------------------------------------------------------
# The implemented plan (describe-pr-quick): the code after each phase commit
# ---------------------------------------------------------------------------


def patch(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        sys.exit("build.py: patch target not found exactly once: %r" % old)
    return text.replace(old, new)


PRICING_PHASE_1_PY = '''\
"""Order pricing: discount codes, bulk discount tiers, and totals."""
from __future__ import annotations

from typing import Optional

from shop.cart import Cart

DISCOUNT_CODES = {
    "WELCOME10": 0.10,
    "VIP20": 0.20,
}

# (minimum item count, rate), largest tier first.
BULK_TIERS = ((50, 0.10), (10, 0.05))

TAX_RATE = 0.08


def code_discount(code: Optional[str]) -> float:
    """Return the discount rate of a code, or 0.0 for no code or an unknown code."""
    if not code:
        return 0.0
    return DISCOUNT_CODES.get(code.upper(), 0.0)


def bulk_discount(item_count: int) -> float:
    """Return the bulk discount rate for an item count, or 0.0 below the smallest tier."""
    for minimum, rate in BULK_TIERS:
        if item_count >= minimum:
            return rate
    return 0.0


def order_total(cart: Cart, code: Optional[str] = None) -> float:
    """Subtotal minus the bulk discount (else the code discount), plus tax, rounded to cents."""
    rate = bulk_discount(cart.item_count()) or code_discount(code)
    discounted = cart.subtotal() * (1 - rate)
    return round(discounted * (1 + TAX_RATE), 2)
'''

PRICING_PHASE_2_PY = patch(
    patch(PRICING_PHASE_1_PY, "from typing import Optional\n", "from typing import Optional, Tuple\n"),
    '''def order_total(cart: Cart, code: Optional[str] = None) -> float:
    """Subtotal minus the bulk discount (else the code discount), plus tax, rounded to cents."""
    rate = bulk_discount(cart.item_count()) or code_discount(code)
''',
    '''def applied_discount(cart: Cart, code: Optional[str] = None) -> Tuple[str, float]:
    """Return the larger of the bulk and code discounts as (name, rate); the bulk discount wins a tie.

    The name is "bulk", the upper-case code, or "" when no discount applies.
    """
    bulk = bulk_discount(cart.item_count())
    rate = code_discount(code)
    if bulk and bulk >= rate:
        return "bulk", bulk
    if rate and code:
        return code.upper(), rate
    return "", 0.0


def order_total(cart: Cart, code: Optional[str] = None) -> float:
    """Subtotal minus the larger of the bulk and code discounts, plus tax, rounded to cents."""
    _, rate = applied_discount(cart, code)
''',
)

RECEIPT_PHASE_1_PY = patch(
    patch(RECEIPT_PY, "from shop.pricing import code_discount, order_total\n",
          "from shop.pricing import bulk_discount, code_discount, order_total\n"),
    '''    rate = code_discount(code)
    if rate:
''',
    '''    bulk = bulk_discount(cart.item_count())
    rate = code_discount(code)
    if bulk:
        lines.append("Bulk discount: -%d%%" % round(bulk * 100))
    elif rate:
''',
)

RECEIPT_PHASE_2_PY = patch(
    patch(RECEIPT_PHASE_1_PY, "from shop.pricing import bulk_discount, code_discount, order_total\n",
          "from shop.pricing import applied_discount, order_total\n"),
    '''    bulk = bulk_discount(cart.item_count())
    rate = code_discount(code)
    if bulk:
        lines.append("Bulk discount: -%d%%" % round(bulk * 100))
    elif rate:
        lines.append("Discount %s: -%d%%" % (code.upper(), round(rate * 100)))
''',
    '''    name, rate = applied_discount(cart, code)
    if name == "bulk":
        lines.append("Bulk discount: -%d%%" % round(rate * 100))
    elif name:
        lines.append("Discount %s: -%d%%" % (name, round(rate * 100)))
''',
)

MAIN_GUARD = '\n\nif __name__ == "__main__":\n'

TEST_PRICING_PHASE_1_PY = patch(
    patch(TEST_PRICING_PY, "from shop.pricing import code_discount, order_total\n",
          "from shop.pricing import bulk_discount, code_discount, order_total\n"),
    MAIN_GUARD,
    '''

class BulkDiscountTest(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(bulk_discount(9), 0.0)
        self.assertEqual(bulk_discount(10), 0.05)
        self.assertEqual(bulk_discount(49), 0.05)
        self.assertEqual(bulk_discount(50), 0.10)

    def test_order_total_applies_the_bulk_tier(self):
        cart = Cart()
        cart.add(Item("B2", "Pen", 1.0), 10)
        self.assertEqual(order_total(cart), 10.26)

    def test_receipt_shows_the_bulk_discount(self):
        cart = Cart()
        cart.add(Item("B2", "Pen", 1.0), 50)
        text = format_receipt(cart)
        self.assertIn("Bulk discount: -10%", text)
        self.assertIn("Total: 48.60", text)
''' + MAIN_GUARD,
)

TEST_PRICING_PHASE_2_PY = patch(
    patch(TEST_PRICING_PHASE_1_PY, "from shop.pricing import bulk_discount, code_discount, order_total\n",
          "from shop.pricing import applied_discount, bulk_discount, code_discount, order_total\n"),
    MAIN_GUARD,
    '''

class LargerDiscountWinsTest(unittest.TestCase):
    def test_larger_code_wins(self):
        cart = Cart()
        cart.add(Item("B2", "Pen", 1.0), 10)
        self.assertEqual(applied_discount(cart, "VIP20"), ("VIP20", 0.20))
        self.assertEqual(order_total(cart, "VIP20"), 8.64)
        text = format_receipt(cart, "VIP20")
        self.assertIn("Discount VIP20: -20%", text)
        self.assertNotIn("Bulk discount", text)

    def test_bulk_wins_a_tie(self):
        cart = Cart()
        cart.add(Item("B2", "Pen", 1.0), 50)
        self.assertEqual(applied_discount(cart, "WELCOME10"), ("bulk", 0.10))
        text = format_receipt(cart, "WELCOME10")
        self.assertIn("Bulk discount: -10%", text)
        self.assertNotIn("WELCOME10", text)
''' + MAIN_GUARD,
)

# Each phase commit as implement makes it: (files, subject, body, date).
PHASE_COMMITS = (
    ({"shop/pricing.py": PRICING_PHASE_1_PY, "shop/receipt.py": RECEIPT_PHASE_1_PY,
      "tests/test_pricing.py": TEST_PRICING_PHASE_1_PY},
     "feat(pricing): add bulk discount tiers (#7)", "Phase 1: Bulk discount tiers",
     "2026-11-09T11:00:00+00:00"),
    ({"shop/pricing.py": PRICING_PHASE_2_PY, "shop/receipt.py": RECEIPT_PHASE_2_PY,
      "tests/test_pricing.py": TEST_PRICING_PHASE_2_PY},
     "feat(pricing): apply the larger of code and bulk discount (#7)", "Phase 2: Larger discount wins",
     "2026-11-09T12:00:00+00:00"),
)

LOG_BODY = '''\
## Phase 1 — in-progress
Started: 2026-11-09

## Phase 1 — done — {hash1}
Checks: make check: pass; lint ✓ typecheck ✓ test ✓ (10 passed)
Reviewer: pass; nits: None
Deviations: None
Additions: None
Manual verification: run `python3 -m shop.receipt` and confirm that the demo receipt shows `Bulk discount: -10%` on its own line, above the total

## Phase 2 — in-progress
Started: 2026-11-09

## Phase 2 — done — {hash2}
Checks: make check: pass; lint ✓ typecheck ✓ test ✓ (12 passed)
Reviewer: pass; nits: None
Deviations: the bulk discount wins a tie with a code (the plan does not define a tie), so the demo receipt (52 items, WELCOME10) still shows `Bulk discount: -10%`
Additions: `applied_discount(cart, code) -> Tuple[str, float]` in shop/pricing.py returns the discount that applies; `order_total` and `format_receipt` share it
Manual verification: None
'''


def ticked(plan: str) -> str:
    """The plan after implement: Phase Overview and Automated lines ticked; Manual lines stay for the user."""
    for old in ("- [ ] 1. ", "- [ ] 2. ", "- [ ] Automated: "):
        plan = plan.replace(old, old.replace("[ ]", "[x]"))
    return plan


def frontmatter(fields: Dict[str, str]) -> str:
    return "---\n" + "".join("%s: %s\n" % (k, v) for k, v in fields.items()) + "---\n"


def write(path: str, text: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Shop Dev",
    "GIT_AUTHOR_EMAIL": "dev@example.com",
    "GIT_COMMITTER_NAME": "Shop Dev",
    "GIT_COMMITTER_EMAIL": "dev@example.com",
    "GIT_AUTHOR_DATE": "2026-11-01T10:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-11-01T10:00:00+00:00",
    "GIT_TERMINAL_PROMPT": "0",
}


def git(*args: str, date: Optional[str] = None) -> str:
    env = dict(os.environ)
    env.update(GIT_ENV)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    proc = subprocess.run(["git"] + list(args), env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    if proc.returncode != 0:
        sys.exit("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout.strip()


def build_repo(config: Optional[Dict[str, Any]] = None, loom_json: bool = True,
               gitignore: str = GITIGNORE, extra: Optional[Dict[str, str]] = None) -> None:
    """Project files, one commit on main, and local git identity for later commits.

    `loom_json=False` leaves out `.claude/loom.json` (a repository before setup); `extra` adds files.
    """
    write("shop/__init__.py", '"""A tiny shop library."""\n')
    write("shop/cart.py", CART_PY)
    write("shop/pricing.py", PRICING_PY)
    write("shop/receipt.py", RECEIPT_PY)
    write("tests/__init__.py", "")
    write("tests/test_cart.py", TEST_CART_PY)
    write("tests/test_pricing.py", TEST_PRICING_PY)
    write("Makefile", MAKEFILE)
    write("README.md", README_MD)
    write(".gitignore", gitignore)
    if loom_json:
        write(".claude/loom.json", json.dumps(config or LOOM_JSON, indent=2) + "\n")
    for path, text in sorted((extra or {}).items()):
        write(path, text)
    git("init", "-q", "-b", "main")
    # Later commits (implement, the guard scenario) run without global config.
    git("config", "user.name", "Shop Dev")
    git("config", "user.email", "dev@example.com")
    git("config", "commit.gpgsign", "false")
    git("add", "-A")
    git("commit", "-q", "-m", "chore: initial shop library")


def ticket(mode: str, screens: bool = False) -> None:
    """`screens=True` adds the `## Screens` section (research-full and design-full only)."""
    fields = {"task": TASK, "phase": "ticket", "mode": mode, "size": "M", "issue": "7", "url": ISSUE_URL}
    write(os.path.join(TASK_DIR, "00-ticket.md"),
          frontmatter(fields) + TICKET_BODY.format(mode=mode, url=ISSUE_URL) + (TICKET_SCREENS if screens else ""))


def artifact(name: str, phase: str, based_on: str, body: str, **extra: str) -> None:
    fields = {"task": TASK, "phase": phase, "status": "approved", "based_on": based_on}
    fields.update(extra)
    fields["updated"] = UPDATED
    write(os.path.join(TASK_DIR, name), frontmatter(fields) + "\n" + body)


def research(based_on: str) -> None:
    artifact("02-research.md", "research", based_on, RESEARCH_BODY,
             git_commit=git("rev-parse", "--short", "HEAD"))


def scenario_research_full() -> None:
    build_repo(extra=DESIGN_FILES)
    git("switch", "-q", "-c", BRANCH)
    ticket("full", screens=True)
    artifact("01-research-questions.md", "research-questions", "[00-ticket.md]", RESEARCH_QUESTIONS_BODY)


def scenario_design_full() -> None:
    scenario_research_full()
    research("[01-research-questions.md]")


def scenario_implement_manual(config: Optional[Dict[str, Any]] = None) -> None:
    build_repo(config)
    git("switch", "-q", "-c", BRANCH)
    ticket("quick")
    research("[00-ticket.md]")
    artifact("04-plan.md", "plan", "[00-ticket.md, 02-research.md]", PLAN_BODY)


def scenario_describe_pr_quick() -> None:
    """Quick mode after implement: both phases committed and logged, plan ticked, no remote, no PR.

    Its loom.json maps the task summaries to `notes/loom-tasks` and requires `## Test plan`.
    """
    scenario_implement_manual(DESCRIBE_PR_LOOM_JSON)
    hashes = []
    for files, subject, body, date in PHASE_COMMITS:
        for path, text in files.items():
            write(path, text)
        git("add", "--", *sorted(files))
        git("commit", "-q", "-m", subject, "-m", body, date=date)
        hashes.append(git("rev-parse", "--short", "HEAD"))
        # implement writes every commit message to this file and keeps it (git-flow.md).
        write(os.path.join(TASK_DIR, "commit-msg.txt"), "%s\n\n%s\n" % (subject, body))
    artifact("04-plan.md", "plan", "[00-ticket.md, 02-research.md]", ticked(PLAN_BODY))
    write(os.path.join(TASK_DIR, "log.md"), LOG_BODY.format(hash1=hashes[0], hash2=hashes[1]))


def scenario_guard_main() -> None:
    build_repo()
    with open("README.md", "a", encoding="utf-8") as fh:
        fh.write("\nDiscount codes: WELCOME10, VIP20.\n")
    git("add", "README.md")


# ---------------------------------------------------------------------------
# design-onboarding: the onboarding task of a repository with code (LOOM_SPEC.md 9.13)
# ---------------------------------------------------------------------------

SETUP_ISSUE = 1
SETUP_TASK = "%d-loom-setup" % SETUP_ISSUE
SETUP_BRANCH = "chore/" + SETUP_TASK
SETUP_TASK_DIR = os.path.join(".loom", "tasks", SETUP_TASK)
SETUP_ISSUE_URL = "https://github.com/example/shop/issues/%d" % SETUP_ISSUE

# The kickoff's minimal loom.json (LOOM_SPEC.md 9.13.2 step 7): every other key keeps its default.
KICKOFF_LOOM_JSON = {"version": 1, "mainBranch": "main"}

# The kickoff settings of settings.json (9.13.2 step 8): `extraKnownMarketplaces`, `enabledPlugins`,
# and the permission rules of the setup template, without the rule for the check commands
# (`Bash(make *)`) and without the `statusLine`, and the `$schema` line of a new file.
KICKOFF_SETTINGS = {
    "$schema": "https://json.schemastore.org/claude-code-settings.json",
    "extraKnownMarketplaces": {"loom": {"source": {"source": "github", "repo": "mmosvlad1/loom"}}},
    "enabledPlugins": {"loom@loom": True},
    "permissions": {
        "allow": [
            "Bash(git status *)", "Bash(git diff *)", "Bash(git log *)", "Bash(git add *)",
            "Bash(git commit *)", "Bash(git switch *)", "Bash(git pull *)", "Bash(git fetch *)",
            "Bash(git rebase *)", "Bash(git stash push *)", "Bash(git stash list *)",
            "Bash(git stash show *)", "Bash(git stash pop *)", "Bash(git branch *)",
            "Bash(gh issue view *)", "Bash(gh issue list *)", "Bash(gh pr view *)", "Bash(gh pr checks *)",
            "Bash(gh run view *)", "Bash(gh run list *)", "Bash(gh pr list *)", "Bash(gh label list *)",
            "Bash(gh repo view *)", "Bash(loom-state --json)", "Bash(loom-state --json --pr)",
            "Bash(loom-state --slug *)", "Bash(mkdir -p .loom/tasks/_archive)",
            "Bash(mv .loom/tasks/* .loom/tasks/_archive/)", "Bash(mv .loom/tasks/_archive/* .loom/tasks/)",
        ],
        "ask": [
            "Bash(git push *)", "Bash(gh pr create *)", "Bash(gh pr edit *)", "Bash(gh pr merge *)",
            "Bash(gh issue create *)", "Bash(gh issue edit *)", "Bash(gh label create *)",
            "Bash(gh api *)",
        ],
    },
}

# An AGENTS.md that Claude Code loads by itself (no CLAUDE.md), with a rule that conflicts with loom.
AGENTS_MD = """\
# Agent instructions

- Run `make check` before you finish a change.
- Work on a branch named `feature/<short-name>`.
- Push and open pull requests without asking for confirmation.
- Keep commit subjects short and in the imperative mood.
"""

# The existing CI: one job named `test` that runs only the unit tests, not `make check`.
CI_YML = """\
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: make test
"""

ONBOARDING_GITIGNORE = "__pycache__/\n"

# The issue body of templates/setup-issue-onboarding.md, verbatim (tests/test_evals.py compares them).
SETUP_ISSUE_BODY = """\
## Context

The project starts to use the loom plugin for issue-to-PR work. The repository already has code, so this setup runs as a loom task in full mode: research describes the repository, design discusses how loom fits the project, and the plan and its implementation phases write the configuration. `/loom:setup` does only the kickoff: the minimal `.claude/loom.json`, the kickoff settings of `.claude/settings.json`, and the fixed research questions.

## Acceptance Criteria

- [ ] `.claude/loom.json` is complete: the check commands, the docs map, and `ci.requiredCheck`
- [ ] `checks.check` passes on the main branch and finishes within 540 seconds
- [ ] The required CI check runs `checks.check` on pull requests and on pushes to the main branch, and `ci.requiredCheck` names it
- [ ] `.claude/settings.json` registers the loom marketplace, enables `loom@loom`, and allowlists the routine commands and the check commands
- [ ] Each docs role (vision, overview, decisions, conventions, tasks) has a document: mapped, migrated, or created
- [ ] `CLAUDE.md` has the loom section; a new `CLAUDE.md` imports `@AGENTS.md` when the repository has an `AGENTS.md`
- [ ] `.gitignore` ignores the loom work directory

## Out of Scope

- Every other gap of the repository: each one becomes a follow-up issue after this PR.
- No migration of issues, labels, or branches.
- The main branch ruleset: `/loom:finish-task` offers it after this PR is merged, when the required CI check exists on the main branch.
"""

# skills/setup/references/onboarding-questions.md with the Key Context Pointers of `--setup-path` filled
# (tests/test_evals.py compares them).
ONBOARDING_QUESTIONS_BODY = """\
# Research Questions

## Key Context Pointers

- Instruction files: `AGENTS.md`
- Workflows: `.github/workflows/ci.yml`
- PR templates: None.
- Docs directories: None.

## Questions

1. **Stacks and check commands.** Which languages, package managers, and lock files does the repository use, and where? Which commands run lint, format check, typecheck, unit tests, build, and e2e tests today (`Makefile`, `justfile`, `Taskfile.yml`, `package.json` scripts, `tox.ini`, `noxfile.py`, `scripts/`)? Is there one root command that runs several of them? Which services, secrets, or network access does each command need? What are the exit status and the run time of each command that research runs (the check runs rule of research)?
2. **CI.** Which workflows exist in `.github/workflows/` (and other CI configuration)? For each: the triggers, the check names as GitHub reports them (job `name`, with matrix suffixes), the commands each job runs, how actions and tools are pinned, and how long the jobs ran in the latest run on the main branch (`gh run list`, `gh run view`).
3. **Documentation.** Where do the docs live (README, `docs/`, `doc/`, ADR directories, wiki links)? What are the structure, the file formats, and the file naming? Which documents describe the product and its users, the architecture and its components, past decisions (with their file name pattern and layout), code conventions, and past work (changelogs, task notes)?
4. **Agent instruction files and Claude Code configuration.**
   - Which of `AGENTS.md`, `.claude/AGENTS.md`, `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/`, `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.github/instructions/`, `GEMINI.md`, and similar files exist, at the git top level and in subdirectories?
   - Which of them does Claude Code load (the instruction files rule of research), and which does `CLAUDE.md` import with `@`?
   - What do they state about branches, commits, push, pull requests, confirmations, the planning workflow, checks, and code? Quote each rule with `file:line`.
   - What else does `.claude/` hold: `commands/`, `skills/`, `agents/`, the hooks and the enabled plugins of `.claude/settings.json`?
5. **Conventions.** Which linter, formatter, and type checker configurations exist, with their main settings? How are tests laid out (directories, naming, fixtures)? How are modules and packages laid out?
6. **Git process.**
   - What are the default branch, the branch name patterns in use, and the commit message format on the main branch?
   - Which merge method does the history show, and which merge methods does the repository allow (`gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed,deleteBranchOnMerge`)?
   - Which local git hooks exist (`.pre-commit-config.yaml`, `.husky/`, `lefthook.yml`, `core.hooksPath`), and what does each run on commit and on push?
   - Which PR templates exist, with which sections? Which CI steps or actions read the PR title, the PR body, or the commit subjects?
   - Which labels, open issues, and milestones exist?
   - Which rulesets or branch protection rules apply to the main branch (required checks, required approvals, signed commits)?
7. **loom requirements.** For each item, does it exist today, and where:
   - one root command that runs lint, typecheck, and unit tests; separate commands for each;
   - a CI job that runs that command on pull requests and on pushes to the main branch;
   - a document in each of the docs roles `vision` (what the product is, for whom, non-goals), `overview` (components and data flow), `decisions` (decision records), `conventions` (code style, testing rules, module layout), and `tasks` (notes on past work);
   - tests, and the result of the latest CI run on the main branch;
   - `.claude/settings.json`, and its keys;
   - a git ignore rule that covers `.claude/`, `CLAUDE.md`, or a document of a docs role (`git check-ignore -v`).
"""

ONBOARDING_RESEARCH_BODY = """\
# Research

## Summary

The repository is a Python standard library package, `shop/`, with `unittest` tests in `tests/`. A `Makefile` runs every check: `make check` runs `lint`, `typecheck`, and `test` (`Makefile:15`), and it passed in 0.4 seconds on this branch. One GitHub Actions workflow has one job, `test`, which runs `make test` only (`.github/workflows/ci.yml:12-19`). The only document is `README.md`. `AGENTS.md` at the git top level holds the agent rules; no `CLAUDE.md` exists, so Claude Code loads `AGENTS.md` at the start.

## Findings

### 1. One Makefile runs lint, typecheck, and tests, and `make check` passes in 0.4 seconds

Question: Stacks and check commands.

The repository uses Python with the standard library only: no `pyproject.toml`, no lock file, no dependencies. `shop/` holds the package (`shop/__init__.py:1`), `tests/` the tests (`tests/test_cart.py:1-3`).

The `Makefile` defines four targets (`Makefile:4`):

| Target | Command | Lines |
|---|---|---|
| `lint` | parses every `shop/*.py` and `tests/*.py` file with `ast` | `Makefile:6-7` |
| `typecheck` | prints a message; no type checker runs | `Makefile:9-10` |
| `test` | `python3 -B -m unittest discover -s tests -t .` | `Makefile:12-13` |
| `check` | runs `lint`, `typecheck`, and `test` | `Makefile:15` |

No command needs a service, a secret, or network access. `README.md:5` names `make check` as the way to run the checks.

Check runs on this branch:

| Command | Exit status | Run time | Result |
|---|---|---|---|
| `make check` | 0 | 0.4 s | passes: 7 tests |

`git status --porcelain` was empty after the run.

#### Testing patterns

`tests/test_cart.py:6-22` and `tests/test_pricing.py:8-26` hold stdlib `unittest` test cases with literal carts; no fixtures or mocks.

### 2. One workflow runs `make test` in a job named `test` on pull requests and pushes to main

Question: CI.

`.github/workflows/ci.yml` runs on `pull_request` and on `push` to `main` (`.github/workflows/ci.yml:3-6`), with `contents: read` (`.github/workflows/ci.yml:8-9`). Its one job is `test` (`.github/workflows/ci.yml:12`); GitHub reports the check name `test`. The job runs on `ubuntu-24.04`, sets up Python 3.12, and runs `make test` (`.github/workflows/ci.yml:13-19`). It does not run `make lint`, `make typecheck`, or `make check`. Actions are pinned to major tags: `actions/checkout@v4`, `actions/setup-python@v5` (`.github/workflows/ci.yml:15-16`).

The latest run on `main` passed; the job `test` ran for 24 seconds (`gh run list`, `gh run view`).

#### Testing patterns

CI runs the same unit tests as `make test` (`.github/workflows/ci.yml:19`).

### 3. The README is the only document

Question: Documentation.

`README.md:1-5` names the project, describes it in one sentence, and names `make check`. No `docs/` or `doc/` directory, no decision records, no changelog, and no task notes exist.

#### Testing patterns

No tests cover the docs.

### 4. `AGENTS.md` is loaded at the start and allows push and PRs without confirmation

Question: Agent instruction files and Claude Code configuration.

| File | Loaded by Claude Code | Why |
|---|---|---|
| `AGENTS.md` | at the start (since Claude Code 2.1.277) | no `CLAUDE.md`, `.claude/CLAUDE.md`, or `CLAUDE.local.md` at the git top level |

No other instruction file exists: no `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/`, `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`, or `GEMINI.md`.

Rules of `AGENTS.md`:

- "Run `make check` before you finish a change." (`AGENTS.md:3`)
- "Work on a branch named `feature/<short-name>`." (`AGENTS.md:4`)
- "Push and open pull requests without asking for confirmation." (`AGENTS.md:5`)
- "Keep commit subjects short and in the imperative mood." (`AGENTS.md:6`)

`.claude/` holds only `loom.json` and `settings.json` of the kickoff commit: no `commands/`, `skills/`, `agents/`, or hooks. The only enabled plugin is `loom@loom`, from the `loom` marketplace on GitHub (`.claude/settings.json:3-13`).

#### Testing patterns

No tests cover the instruction files.

### 5. Modules start with a docstring; tests use one `unittest` file per module

Question: Conventions.

No linter, formatter, or type checker configuration exists. Modules start with a one-line docstring and `from __future__ import annotations` (`shop/pricing.py:1-2`). Tests live in `tests/`, one `test_<module>.py` file per module, one `unittest.TestCase` class per file (`tests/test_cart.py:6`).

#### Testing patterns

`tests/__init__.py` is empty; `make test` discovers the tests from the top level (`Makefile:13`).

### 6. The main branch has one commit; squash merges are allowed and nothing protects the branch

Question: Git process.

- The default branch is `main` (`gh repo view`). The history has one commit, `chore: initial shop library`; this branch adds the kickoff commit `chore(loom): start loom setup (#1)` (`git log`).
- The repository allows squash merges, merge commits, and rebase merges, and does not delete branches on merge (`gh repo view`).
- No local git hooks exist: no `.pre-commit-config.yaml`, `.husky/`, or `lefthook.yml`, and `core.hooksPath` is not set (`git config --get core.hooksPath`).
- No PR template exists, and no CI step reads the PR title, the PR body, or the commit subjects.
- The labels are the GitHub defaults plus `type:chore`, `size:M`, and `mode:full` (`gh label list`). The only open issue is #1 "Set up loom" (`gh issue list`). No milestones exist (`gh api`).
- No ruleset and no classic branch protection apply to `main` (`gh api`: an empty rule list, and 404 for the protection).

#### Testing patterns

Not applicable.

### 7. loom requirements

Question: loom requirements.

| Item | Exists | Where |
|---|---|---|
| One root command for lint, typecheck, and unit tests | exists | `make check` (`Makefile:15`) |
| Separate commands for each | exists | `make lint`, `make typecheck`, `make test` (`Makefile:6-13`) |
| A CI job that runs the root command on pull requests and pushes to main | does not exist | the job `test` runs `make test` (`.github/workflows/ci.yml:19`) |
| `vision` document | exists | `README.md:3` (one sentence) |
| `overview` document | does not exist | — |
| `decisions` document | does not exist | — |
| `conventions` document | does not exist | — |
| `tasks` document | does not exist | — |
| Tests | exists | `tests/`, 7 tests; the latest CI run on `main` passed |
| `.claude/settings.json` | exists | the kickoff settings: `$schema`, `extraKnownMarketplaces`, `enabledPlugins`, and `permissions` (`.claude/settings.json:2-14`); the whole file has no `Bash(make *)` rule and no `statusLine` (`.claude/settings.json:1-57`) |
| An ignore rule for `.claude/`, `CLAUDE.md`, or a document of a docs role | does not exist | `git check-ignore -v` matched none |

#### Testing patterns

Not applicable.

## Patterns & Conventions

- Modules start with a one-line docstring and `from __future__ import annotations` (`shop/pricing.py:1-2`).
- Money values are floats, rounded only in `order_total` (`shop/pricing.py:26`).

## External Sources

None.

## Not Found / Unclear

- The run time of the job `test` in runs before the latest one was not read.
"""


def onboarding_artifact(name: str, phase: str, based_on: str, body: str, **extra: str) -> None:
    fields = {"task": SETUP_TASK, "phase": phase, "status": "approved", "based_on": based_on}
    fields.update(extra)
    fields["updated"] = UPDATED
    write(os.path.join(SETUP_TASK_DIR, name), frontmatter(fields) + "\n" + body)


def scenario_design_onboarding() -> None:
    """An onboarding task in full mode after the kickoff and an approved research.

    The main branch has code, an AGENTS.md (no CLAUDE.md), and a CI job named `test`, and
    no `.claude/loom.json`. The branch chore/1-loom-setup has the kickoff commit with the
    minimal loom.json, the kickoff settings.json, and the `.loom/` line of .gitignore.
    """
    build_repo(loom_json=False, gitignore=ONBOARDING_GITIGNORE,
               extra={"AGENTS.md": AGENTS_MD, ".github/workflows/ci.yml": CI_YML})
    # The kickoff needs `origin`, and the research reads GitHub facts. The remote is never fetched:
    # no remote-tracking ref exists, so loom-state and --setup-path read the local main branch.
    git("remote", "add", "origin", "https://github.com/example/shop.git")
    git("switch", "-q", "-c", SETUP_BRANCH)
    write(".gitignore", ONBOARDING_GITIGNORE + ".loom/\n")
    write(".claude/loom.json", json.dumps(KICKOFF_LOOM_JSON, indent=2) + "\n")
    write(".claude/settings.json", json.dumps(KICKOFF_SETTINGS, indent=2) + "\n")
    fields = {"task": SETUP_TASK, "phase": "ticket", "mode": "full", "size": "M", "issue": str(SETUP_ISSUE),
              "url": SETUP_ISSUE_URL}
    write(os.path.join(SETUP_TASK_DIR, "00-ticket.md"), frontmatter(fields) + (
        "# Set up loom\n\nLabels: type:chore, size:M, mode:full\nURL: %s\n\n" % SETUP_ISSUE_URL) + SETUP_ISSUE_BODY)
    git("add", "--", ".gitignore", ".claude/loom.json", ".claude/settings.json")
    git("commit", "-q", "-m", "chore(loom): start loom setup (#%d)" % SETUP_ISSUE, date="2026-11-09T09:00:00+00:00")
    onboarding_artifact("01-research-questions.md", "research-questions", "[]", ONBOARDING_QUESTIONS_BODY)
    onboarding_artifact("02-research.md", "research", "[01-research-questions.md]", ONBOARDING_RESEARCH_BODY,
                        git_commit=git("rev-parse", "--short", "HEAD"))


# ---------------------------------------------------------------------------
# screens-local: a screens task before its stages 3 and 4 (LOOM_SPEC.md 9.14.6, 9.14.9)
# ---------------------------------------------------------------------------

SCREENS_ISSUE = 12
SCREENS_TASK = "%d-loom-screens" % SCREENS_ISSUE
SCREENS_BRANCH = "docs/" + SCREENS_TASK
SCREENS_TASK_DIR = os.path.join(".loom", "tasks", SCREENS_TASK)
SCREENS_ISSUE_URL = "https://github.com/example/shop/issues/%d" % SCREENS_ISSUE
# The one screen of the scope, in two states: the default state and `empty` (LOOM_SPEC.md 9.14.3).
SCREEN_ID = "order-summary"

# The issue of the screens task as the kickoff creates it (LOOM_SPEC.md 9.14.6 step 5): one acceptance
# criterion per screen and state, no `## Screens` section.
SCREENS_ISSUE_BODY = """\
## Context

Issue #7 adds bulk discount tiers to the receipt. The order summary of the shop has no screen yet, so the
look of the discount line and of an empty cart is open. This task draws the screen and lands the style guide.

## Acceptance Criteria

- [ ] order-summary: the items, the bulk discount line, and the total of a cart with 52 items
- [ ] order-summary--empty: a cart without items
"""

# The brief after stages 1 and 2 (LOOM_SPEC.md 9.14.6): Scope, Audience, References `none`, and a chosen
# direction. The project has no style guide, so stage 3 drafts one and stage 4 draws the screen.
SCREENS_BRIEF = """\
## Scope

- `order-summary`: default, empty; serves #7 (bulk discount tiers on the receipt)

## Audience

Wholesale customers who buy notebooks and pens in large quantities. The order summary must first show
what the bulk discount saves, then the total.

## References

none

## Direction

Plain ledger: calm and quiet, like a printed paper slip; numbers line up in one column.

## Decisions

- 2026-11-12: References none; the user gave no site, screenshot, or brand asset.
- 2026-11-12: Direction "Plain ledger", chosen by the user from three directions.

## Screens

| Screen ID | Status |
|---|---|
| order-summary | planned |
| order-summary--empty | planned |
"""


def scenario_screens_local() -> None:
    """A screens task on docs/12-loom-screens whose brief holds the results of stages 1 and 2.

    The branch is cut from main and has no commit; the repository has no style guide and no screen.
    So /loom:screens --local runs stages 3 and 4 without a question and stops before the landing.
    """
    build_repo()
    git("switch", "-q", "-c", SCREENS_BRANCH)
    fields = {"task": SCREENS_TASK, "phase": "ticket", "mode": "oneshot", "size": "S",
              "issue": str(SCREENS_ISSUE), "url": SCREENS_ISSUE_URL}
    write(os.path.join(SCREENS_TASK_DIR, "00-ticket.md"), frontmatter(fields) + (
        "# Design screens: order summary\n\nLabels: type:docs, size:S, mode:oneshot\nURL: %s\n\n"
        % SCREENS_ISSUE_URL) + SCREENS_ISSUE_BODY)
    write(os.path.join(SCREENS_TASK_DIR, "screens-brief.md"),
          frontmatter({"task": SCREENS_TASK, "updated": "2026-11-12", "drawing": "local"}) + SCREENS_BRIEF)


SCENARIOS = {
    "research-full": scenario_research_full,
    "design-full": scenario_design_full,
    "implement-manual": scenario_implement_manual,
    "guard-main": scenario_guard_main,
    "describe-pr-quick": scenario_describe_pr_quick,
    "design-onboarding": scenario_design_onboarding,
    "screens-local": scenario_screens_local,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        sys.exit("usage: build.py {%s}" % "|".join(sorted(SCENARIOS)))
    if os.listdir("."):
        sys.exit("build.py: the working directory must be empty")
    SCENARIOS[sys.argv[1]]()


if __name__ == "__main__":
    main()
