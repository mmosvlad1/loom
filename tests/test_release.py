"""Release files: plugin.json version, CHANGELOG.md, and the spec header agree (LOOM_SPEC.md §21)."""
from __future__ import annotations

import json
import os
import re
import unittest

from loomtest import ROOT


def read(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


class ReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.version = json.loads(read(".claude-plugin/plugin.json"))["version"]
        self.changelog = read("CHANGELOG.md")

    def test_version_is_semver(self):
        self.assertRegex(self.version, r"^\d+\.\d+\.\d+$")

    def test_version_only_in_plugin_json(self):
        self.assertNotIn("version", json.loads(read(".claude-plugin/marketplace.json")))
        for plugin in json.loads(read(".claude-plugin/marketplace.json"))["plugins"]:
            self.assertNotIn("version", plugin)

    def test_changelog_top_entry_is_the_plugin_version(self):
        headings = re.findall(r"^## (.+)$", self.changelog, re.M)
        if headings and headings[0] == "[Unreleased]":
            headings = headings[1:]  # a standard Unreleased section may sit above the top version
        entries = [re.fullmatch(r"\[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})", h) for h in headings]
        self.assertTrue(all(entries), headings)
        entries = [m.groups() for m in entries]
        self.assertGreaterEqual(len(entries), 2)
        self.assertEqual(entries[0][0], self.version)
        versions = [tuple(int(x) for x in v.split(".")) for v, _ in entries]
        self.assertEqual(versions, sorted(versions, reverse=True))
        dates = [d for _, d in entries]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_changelog_sections(self):
        for heading in re.findall(r"^### (.+)$", self.changelog, re.M):
            with self.subTest(heading=heading):
                self.assertIn(heading, {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"})
        self.assertIn("never tagged", self.changelog.split("## [1.0.0]", 1)[1])

    def test_spec_and_readme_name_the_version(self):
        self.assertIn("Describes plugin release **%s**" % self.version, read("LOOM_SPEC.md"))
        self.assertIn("[CHANGELOG.md](CHANGELOG.md)", read("README.md"))


if __name__ == "__main__":
    unittest.main()
