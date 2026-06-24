"""
Scrape the Flockhart P450 Drug Interaction Table using a headless browser.
URL: https://drug-interactions.medicine.iu.edu/main-table

The Blazor app pre-renders all drug dialogs in the DOM (764 total), but the
main table uses virtual scrolling so only some trigger links are visible.

Strategy — two-pass parse of the rendered HTML:
  Pass 1 (dialogs): extract all 764 drug-enzyme-relationship entries from
      <div data-rvt-dialog="{id} {Substrate|Inhibitor|Inducer} {enzyme}">
      <h3 class="rvt-dialog__title">{drug} ({Substrate|Inhibitor|Inducer}-{enzyme})</h3>
  Pass 2 (triggers): extract strength (S/M/W/I) from visible trigger links
      <a data-rvt-dialog-trigger="{id} {rel} {enzyme}">{drug}</a>
      <img alt="S|M|W|I">
  Merge by dialog id.

Strength encoding (Flockhart — same for all relationship types):
  S = Strong  (sensitive substrate / strong inhibitor/inducer)
  M = Moderate
  W = Weak
  I = Investigational → stored as ""

Output: knowledge_base/sources/dataset/flockhart_cyp_table.csv
  columns: drug, enzyme, relationship, strength
"""

import asyncio
import csv
import os
import re
from playwright.async_api import async_playwright

BASE   = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, "../sources/dataset/flockhart_cyp_table.csv")
URL    = "https://drug-interactions.medicine.iu.edu/main-table"

STRENGTH_FROM_ALT = {"S": "strong", "M": "moderate", "W": "weak", "I": ""}

# Matches the dialog container attribute
DIALOG_ATTR_RE = re.compile(
    r'data-rvt-dialog="(\d+)\s+(Substrate|Inhibitor|Inducer)\s+([^"]+)"'
)
# Matches the title inside the dialog
DIALOG_TITLE_RE = re.compile(
    r'<h3 class="rvt-dialog__title">(.*?)</h3>'
)
# Matches trigger links (main table cells) + their strength image
TRIGGER_RE = re.compile(
    r'data-rvt-dialog-trigger="(\d+)\s+(?:Substrate|Inhibitor|Inducer)\s+[^"]+?"'
    r'>.*?</a>\s*<!--.*?-->\s*<img[^>]+alt="([SMWI])"',
    re.DOTALL,
)


def clean_drug_name(raw: str) -> str:
    """Strip relationship suffix and inline alias notes from a dialog title."""
    # Remove trailing relationship group: ' (Substrate-3A4/5)' etc.
    name = re.sub(
        r'\s*\((?:Substrate|Inhibitor|Inducer)-[^)]+\)\s*$', "", raw.strip()
    )
    # Remove common inline aliases in parens, e.g. '(fk506)', '(formerly X)'
    name = re.sub(r"\s*\([^)]{1,25}\)\s*$", "", name)
    # Remove footnote markers
    name = re.sub(r"[*†‡§]", "", name)
    return name.strip().lower()


def normalize_enzyme(raw: str) -> str:
    e = raw.strip().upper().replace(" ", "")
    if "3A4" in e or "3A5" in e:
        return "CYP3A4"
    return e if e.startswith("CYP") else "CYP" + e


def parse_dialogs(html: str) -> dict[str, dict]:
    """
    Pair each dialog attribute sequentially with the next dialog title.
    Returns {dialog_id: {drug, enzyme, relationship, strength=""}}
    """
    attrs  = [(m.start(), m.group(1), m.group(2), m.group(3))
              for m in DIALOG_ATTR_RE.finditer(html)]
    titles = [(m.start(), m.group(1))
              for m in DIALOG_TITLE_RE.finditer(html)]

    entries: dict[str, dict] = {}
    title_idx = 0

    for attr_pos, dialog_id, rel_raw, enzyme_raw in attrs:
        # Advance to first title that comes AFTER this dialog attribute
        while title_idx < len(titles) and titles[title_idx][0] <= attr_pos:
            title_idx += 1
        if title_idx >= len(titles):
            break

        drug = clean_drug_name(titles[title_idx][1])
        if not drug or len(drug) < 2:
            continue

        entries[dialog_id] = {
            "drug":         drug,
            "enzyme":       normalize_enzyme(enzyme_raw),
            "relationship": rel_raw.upper(),
            "strength":     "",
        }

    return entries


def parse_trigger_strengths(html: str) -> dict[str, str]:
    """Returns {dialog_id: strength} from visible trigger links."""
    return {
        m.group(1): STRENGTH_FROM_ALT.get(m.group(2), "")
        for m in TRIGGER_RE.finditer(html)
    }


async def scrape() -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Tall viewport encourages virtual-scroll pre-render of more rows
        page = await browser.new_page(viewport={"width": 1280, "height": 15000})

        print(f"Loading {URL} ...")
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("table", timeout=30000)
        await asyncio.sleep(5)

        # Slow scroll to trigger any remaining lazy-loaded content
        await page.evaluate("""
            async () => {
                const delay = ms => new Promise(r => setTimeout(r, ms));
                for (let y = 0; y < document.body.scrollHeight; y += 600) {
                    window.scrollTo(0, y);
                    await delay(60);
                }
                window.scrollTo(0, 0);
            }
        """)
        await asyncio.sleep(4)

        html = await page.content()
        await browser.close()

    # Save for debugging
    with open(os.path.join(os.getcwd(), "flockhart_raw.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # Pass 1: extract all entries from pre-rendered dialogs
    entries = parse_dialogs(html)
    print(f"  Dialogs parsed:          {len(entries)}")

    # Pass 2: add strength from visible trigger links
    strengths = parse_trigger_strengths(html)
    print(f"  Trigger strengths found: {len(strengths)}")

    for dialog_id, strength in strengths.items():
        if dialog_id in entries and strength:
            entries[dialog_id]["strength"] = strength

    # Deduplicate: if same (drug, enzyme, relationship) appears twice,
    # keep the one with strength (more informative)
    seen: dict[tuple, dict] = {}
    for row in entries.values():
        key = (row["drug"], row["enzyme"], row["relationship"])
        existing = seen.get(key)
        if existing is None or (not existing["strength"] and row["strength"]):
            seen[key] = row

    rows = sorted(seen.values(), key=lambda r: (r["enzyme"], r["relationship"], r["drug"]))
    return rows


def write_csv(rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["drug", "enzyme", "relationship", "strength"])
        writer.writeheader()
        writer.writerows(rows)

    from collections import Counter
    by_rel    = Counter(r["relationship"] for r in rows)
    by_enzyme = Counter(r["enzyme"] for r in rows)
    with_strength = sum(1 for r in rows if r["strength"])
    print(f"\nWritten: {OUTPUT}")
    print(f"By relationship: {dict(sorted(by_rel.items()))}")
    print(f"By enzyme:       {dict(sorted(by_enzyme.items()))}")
    print(f"Entries with strength: {with_strength}/{len(rows)}")
    print(f"Total unique entries:  {len(rows)}")


if __name__ == "__main__":
    rows = asyncio.run(scrape())
    if rows:
        write_csv(rows)
    else:
        print("ERROR: no data extracted.")
