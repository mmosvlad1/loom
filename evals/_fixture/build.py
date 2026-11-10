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
  research-full     full mode, branch feat/7-..., 01-research-questions.md approved
  design-full       full mode, research approved
  implement-manual  quick mode, plan approved; implementation phase 1 has a Manual line
  guard-main        on main with a staged change and no task
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Dict

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


def git(*args: str) -> str:
    env = dict(os.environ)
    env.update(GIT_ENV)
    proc = subprocess.run(["git"] + list(args), env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    if proc.returncode != 0:
        sys.exit("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout.strip()


def build_repo() -> None:
    """Project files, one commit on main, and local git identity for later commits."""
    write("shop/__init__.py", '"""A tiny shop library."""\n')
    write("shop/cart.py", CART_PY)
    write("shop/pricing.py", PRICING_PY)
    write("shop/receipt.py", RECEIPT_PY)
    write("tests/__init__.py", "")
    write("tests/test_cart.py", TEST_CART_PY)
    write("tests/test_pricing.py", TEST_PRICING_PY)
    write("Makefile", MAKEFILE)
    write("README.md", README_MD)
    write(".gitignore", GITIGNORE)
    write(".claude/loom.json", json.dumps(LOOM_JSON, indent=2) + "\n")
    git("init", "-q", "-b", "main")
    # Later commits (implement, the guard scenario) run without global config.
    git("config", "user.name", "Shop Dev")
    git("config", "user.email", "dev@example.com")
    git("config", "commit.gpgsign", "false")
    git("add", "-A")
    git("commit", "-q", "-m", "chore: initial shop library")


def ticket(mode: str) -> None:
    fields = {"task": TASK, "phase": "ticket", "mode": mode, "size": "M", "issue": "7", "url": ISSUE_URL}
    write(os.path.join(TASK_DIR, "00-ticket.md"),
          frontmatter(fields) + TICKET_BODY.format(mode=mode, url=ISSUE_URL))


def artifact(name: str, phase: str, based_on: str, body: str, **extra: str) -> None:
    fields = {"task": TASK, "phase": phase, "status": "approved", "based_on": based_on}
    fields.update(extra)
    fields["updated"] = UPDATED
    write(os.path.join(TASK_DIR, name), frontmatter(fields) + "\n" + body)


def research(based_on: str) -> None:
    artifact("02-research.md", "research", based_on, RESEARCH_BODY,
             git_commit=git("rev-parse", "--short", "HEAD"))


def scenario_research_full() -> None:
    build_repo()
    git("switch", "-q", "-c", BRANCH)
    ticket("full")
    artifact("01-research-questions.md", "research-questions", "[00-ticket.md]", RESEARCH_QUESTIONS_BODY)


def scenario_design_full() -> None:
    scenario_research_full()
    research("[01-research-questions.md]")


def scenario_implement_manual() -> None:
    build_repo()
    git("switch", "-q", "-c", BRANCH)
    ticket("quick")
    research("[00-ticket.md]")
    artifact("04-plan.md", "plan", "[00-ticket.md, 02-research.md]", PLAN_BODY)


def scenario_guard_main() -> None:
    build_repo()
    with open("README.md", "a", encoding="utf-8") as fh:
        fh.write("\nDiscount codes: WELCOME10, VIP20.\n")
    git("add", "README.md")


SCENARIOS = {
    "research-full": scenario_research_full,
    "design-full": scenario_design_full,
    "implement-manual": scenario_implement_manual,
    "guard-main": scenario_guard_main,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        sys.exit("usage: build.py {%s}" % "|".join(sorted(SCENARIOS)))
    if os.listdir("."):
        sys.exit("build.py: the working directory must be empty")
    SCENARIOS[sys.argv[1]]()


if __name__ == "__main__":
    main()
