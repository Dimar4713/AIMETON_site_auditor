from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.document_pipeline.models import (
    BlockKind,
    ExtractedBlock,
    ExtractedLink,
    ExtractedTable,
)


SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def digest_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class Extraction:
    title: str
    text: str
    blocks: list[ExtractedBlock]
    links: list[ExtractedLink]
    tables: list[ExtractedTable]


def extract_html(html: str, *, base_url: str) -> Extraction:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()

    blocks: list[ExtractedBlock] = []
    title = normalize_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    if title:
        blocks.append(ExtractedBlock(locator="head/title", kind=BlockKind.TITLE, text=title))

    counters: dict[str, int] = {}
    root = soup.select_one("main, article") or soup.body or soup
    for element in root.select("h1, h2, h3, h4, p, li"):
        text = normalize_text(element.get_text(" ", strip=True))
        if not text:
            continue
        tag = element.name.lower()
        counters[tag] = counters.get(tag, 0) + 1
        kind = (
            BlockKind.HEADING
            if tag.startswith("h")
            else BlockKind.LIST_ITEM
            if tag == "li"
            else BlockKind.PARAGRAPH
        )
        blocks.append(
            ExtractedBlock(
                locator=f"body/{tag}[{counters[tag]}]",
                kind=kind,
                text=text,
            )
        )

    tables: list[ExtractedTable] = []
    for table_index, table in enumerate(root.select("table"), start=1):
        rows: list[list[str]] = []
        for row_index, row in enumerate(table.select("tr"), start=1):
            cells: list[str] = []
            for cell_index, cell in enumerate(row.select("th, td"), start=1):
                value = normalize_text(cell.get_text(" ", strip=True))
                cells.append(value)
                if value:
                    blocks.append(
                        ExtractedBlock(
                            locator=(
                                f"body/table[{table_index}]/row[{row_index}]"
                                f"/cell[{cell_index}]"
                            ),
                            kind=BlockKind.TABLE_CELL,
                            text=value,
                        )
                    )
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(
                ExtractedTable(locator=f"body/table[{table_index}]", rows=rows)
            )

    links: list[ExtractedLink] = []
    for link_index, anchor in enumerate(root.select("a[href]"), start=1):
        absolute = urljoin(base_url, str(anchor.get("href") or "").strip())
        if not absolute.startswith(("http://", "https://")):
            continue
        links.append(
            ExtractedLink(
                locator=f"body/a[{link_index}]",
                text=normalize_text(anchor.get_text(" ", strip=True)),
                url=absolute,
            )
        )

    unique_blocks: list[ExtractedBlock] = []
    seen: set[tuple[BlockKind, str]] = set()
    for block in blocks:
        key = (block.kind, block.text)
        if key in seen:
            continue
        seen.add(key)
        unique_blocks.append(block)

    text = "\n".join(block.text for block in unique_blocks)
    return Extraction(
        title=title or (unique_blocks[0].text[:1_000] if unique_blocks else "Документ"),
        text=text,
        blocks=unique_blocks,
        links=links,
        tables=tables,
    )
