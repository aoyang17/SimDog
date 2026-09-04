from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class _References(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.references.append(values["href"] or "")
        if tag in {"img", "link"}:
            reference = values.get("src") or values.get("href")
            if reference:
                self.references.append(reference)


class DocumentationSiteTests(unittest.TestCase):
    def test_case_pages_and_local_references_are_complete(self) -> None:
        pages = [
            DOCS / "index.html",
            DOCS / "cases" / "kobayashi-1993.html",
            DOCS / "cases" / "laghmach-2015.html",
            DOCS / "cases" / "soc-ocv-correction.html",
        ]
        for page in pages:
            self.assertTrue(page.is_file(), page)
            parser = _References()
            parser.feed(page.read_text(encoding="utf-8"))
            for reference in parser.references:
                parsed = urlsplit(reference)
                if parsed.scheme or reference.startswith("#"):
                    continue
                target = (page.parent / parsed.path).resolve()
                self.assertTrue(target.is_file(), f"{page}: missing {reference}")

    def test_public_case_claims_keep_evidence_status(self) -> None:
        index = (DOCS / "index.html").read_text(encoding="utf-8")
        laghmach = (DOCS / "cases" / "laghmach-2015.html").read_text(encoding="utf-8")
        soc_ocv = (DOCS / "cases" / "soc-ocv-correction.html").read_text(encoding="utf-8")
        self.assertIn("Kobayashi 1993", index)
        self.assertIn("17 / 22", laghmach)
        self.assertIn("阶段性复现，不是完整成功", laghmach)
        self.assertIn("不是针对某个实测电芯完成的参数反演", soc_ocv)
        self.assertIn("1200 s", soc_ocv)
        self.assertIn("明确拒绝", soc_ocv)


if __name__ == "__main__":
    unittest.main()
