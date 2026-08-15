import os
import re
import shutil
from decimal import Decimal, InvalidOperation

from dateutil import parser as date_parser
from invoice2data.input import pdftotext

# A currency amount: optional thousands groups, always exactly two decimals.
# The lookarounds are load-bearing -- without them the regex backtracks into the
# middle of a longer number and silently returns "345.67" for "12345.67".
MONEY = r"(?<![\d.,])\d+(?:[,.]\d{3})*[.,]\d{2}(?![\d])"

NUMERIC_DATE = r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}"
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
ALPHA_DATE = rf"(?:{MONTH}\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+{MONTH}\s+\d{{4}})"
DATE = rf"(?:{NUMERIC_DATE}|{ALPHA_DATE})"

# Labels that mean "this is not the invoice date" / "this is not the grand total".
DATE_BLOCKERS = r"due|delivery|deliver|sched|ship|shipped|shipping|order|received|paid|expir\w*"
TOTAL_BLOCKERS = r"excluding|exclusive|before\s+tax"


def setup_poppler():
    """Automatically find Poppler bin path on macOS/Linux/Windows."""
    poppler_bin = shutil.which("pdftotext")
    if poppler_bin:
        bin_path = os.path.dirname(poppler_bin)
        os.environ["PATH"] += os.pathsep + bin_path
        return True
    return False


def parse_money(raw):
    """Turn a matched amount into a Decimal, handling 1,072.83 and 1.072,83 alike."""
    if raw is None:
        return None
    digits = re.sub(r"[^\d.,]", "", raw)
    # The last separator is the decimal point; everything before it is grouping.
    split_at = max(digits.rfind(","), digits.rfind("."))
    if split_at == -1:
        whole, frac = digits, ""
    else:
        whole, frac = digits[:split_at], digits[split_at + 1:]
    whole = re.sub(r"[.,]", "", whole)
    try:
        return Decimal(f"{whole or '0'}.{frac or '0'}")
    except InvalidOperation:
        return None


def parse_date(raw, dayfirst=False):
    """Normalize a matched date to an ISO YYYY-MM-DD string."""
    if raw is None:
        return None
    try:
        return date_parser.parse(raw, dayfirst=dayfirst).date().isoformat()
    except (ValueError, OverflowError):
        return None


def find_labeled_values(text, alias_tiers, value_regex, gap=r"[:\s.\-]*", blockers=None):
    """Collect every (tier, position, value) where a ranked label precedes a value.

    `alias_tiers` is a list of alias lists ordered most-specific-first; a tier's
    index is its rank. Unlike a break-on-first-match loop this gathers *all*
    candidates so the caller can choose by rank and position rather than by the
    accident of alias ordering.
    """
    candidates = []
    for tier, aliases in enumerate(alias_tiers):
        for alias in aliases:
            for m in re.finditer(rf"({alias}){gap}({value_regex})", text, re.IGNORECASE):
                if blockers:
                    before = text[max(0, m.start() - 15):m.start()]
                    between = m.group(0)[len(m.group(1)):-len(m.group(2))]
                    if re.search(rf"\b(?:{blockers})\W*$", before, re.IGNORECASE):
                        continue
                    if re.search(rf"\b(?:{blockers})\b", between, re.IGNORECASE):
                        continue
                candidates.append((tier, m.start(), m.group(2).strip()))
    return candidates


def pick(candidates, prefer="first"):
    """Choose the best candidate: highest rank first, then position."""
    if not candidates:
        return None
    best_tier = min(c[0] for c in candidates)
    tier = [c for c in candidates if c[0] == best_tier]
    chosen = min(tier, key=lambda c: c[1]) if prefer == "first" else max(tier, key=lambda c: c[1])
    return chosen[2]


def first_in_best_tier(text, keyword_tiers, use_end):
    """Earliest match within the most specific tier that matched at all.

    Returns the match's end offset when `use_end` is set (table start), otherwise
    its start offset (table terminator). None if nothing matched.
    """
    for tier in keyword_tiers:
        hits = [m for m in (re.search(kw, text, re.IGNORECASE) for kw in tier) if m]
        if hits:
            best = min(hits, key=lambda m: m.start())
            return best.end() if use_end else best.start()
    return None


def extract_dynamic_heuristics(text, dayfirst=False):
    # Normalize text for metadata, but keep original text for table extraction
    normalized_text = re.sub(r"\s+", " ", text)

    # --- CONFIGURATION: ALIASES (ordered by tier, most specific first) ---
    KEYWORDS = {
        "invoice_number": [
            [r"invoice\s*(?:no|number|#|id)", r"inv\s*(?:no|#)", r"bill\s*no"],
            [r"(?:purchase\s*)?order\s*(?:no|number|#)", r"document\s*no"],
        ],
        "date": [
            [
                r"invoice\s*date",
                r"date\s*of\s*issue",
                r"issue\s*date",
                r"issued\s*on",
                r"billing\s*date",
                r"bill\s*date",
                r"dated",
            ],
            [r"\bdate\b"],
        ],
        "total_amount": [
            [
                r"grand\s*total",
                r"total\s*(?:amount\s*)?(?:due|payable)",
                r"amount\s*due",
                r"amount\s*to\s*pay",
                r"balance\s*due",
            ],
            [r"total\s*amount", r"total\s*balance", r"net\s*amount", r"total\s*price"],
            [r"\btotal\b"],
        ],
    }

    data = {
        "invoice_number": None,
        "date": None,
        "date_raw": None,
        "total_amount": None,
        "total_amount_raw": None,
        "items": [],
    }

    # 1. Invoice Number -- earliest match in the most specific tier that hit.
    data["invoice_number"] = pick(
        find_labeled_values(normalized_text, KEYWORDS["invoice_number"], r"[A-Z0-9\-\/]+"),
        prefer="first",
    )

    # 2. Date -- reject due/delivery/shipping dates, then normalize to ISO.
    raw_date = pick(
        find_labeled_values(normalized_text, KEYWORDS["date"], DATE, blockers=DATE_BLOCKERS),
        prefer="first",
    )
    if not raw_date:
        fallback = re.search(DATE, normalized_text, re.IGNORECASE)
        if fallback:
            raw_date = fallback.group(0).strip()
    data["date_raw"] = raw_date
    data["date"] = parse_date(raw_date, dayfirst=dayfirst)

    # 3. Total Amount -- totals sit at the bottom of a document, so on a tie
    # take the *last* occurrence rather than the first.
    raw_total = pick(
        find_labeled_values(
            normalized_text,
            KEYWORDS["total_amount"],
            MONEY,
            gap=r"[^\d]{0,25}?",
            blockers=TOTAL_BLOCKERS,
        ),
        prefer="last",
    )
    data["total_amount_raw"] = raw_total
    data["total_amount"] = parse_money(raw_total)

    # 4. Line Items (Advanced Table Splitting)
    # Tiers again: a bare "total" is ambiguous because "LINE TOTAL" appears in the
    # header row itself, so only fall back to it when no "subtotal" is present.
    table_start_keywords = [[r"description"], [r"item", r"qty", r"unit\s*price", r"amount"]]
    table_end_keywords = [[r"subtotal", r"grand\s*total"], [r"total", r"tax", r"balance"]]

    start_index = first_in_best_tier(text, table_start_keywords, use_end=True)

    if start_index is not None:
        # Within the best tier, take the *earliest* terminator rather than
        # whichever keyword happened to be listed first.
        rest = text[start_index:]
        end_offset = first_in_best_tier(rest, table_end_keywords, use_end=False)
        end_index = start_index + end_offset if end_offset is not None else len(text)

        table_content = text[start_index:end_index].strip()

        for line in table_content.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Money first so a full amount is never split into two bare integers.
            numbers = re.findall(rf"{MONEY}|(?<![\d.,])\d+(?![\d.,])", line)

            if len(numbers) >= 2:
                first_num_pos = line.find(numbers[0])
                description = line[:first_num_pos].strip()
                if not description:
                    description = line[:line.find(numbers[-2])].strip()

                data["items"].append({
                    "description": description,
                    "qty": numbers[0],
                    "unit_price": parse_money(numbers[-2]),
                    "line_total": parse_money(numbers[-1]),
                })

    return data


def main():
    if not setup_poppler():
        print("Error: Poppler not found. Run 'brew install poppler'")
        return

    # Target PDF for the current test
    pdf_path = "/Users/ap/ocr-dynamic-gem-main/file/invoiceClaude.pdf"

    if not os.path.exists(pdf_path):
        print(f"Error: File not found at {pdf_path}")
        return

    try:
        print(f"Processing: {os.path.basename(pdf_path)}...")
        raw_text = pdftotext.to_text(pdf_path)
        extracted_data = extract_dynamic_heuristics(raw_text)

        print("\n--- METADATA ---")
        print(f"Invoice #: {extracted_data['invoice_number']}")
        print(f"Date     : {extracted_data['date']}  (raw: {extracted_data['date_raw']})")
        print(f"Total    : {extracted_data['total_amount']}  (raw: {extracted_data['total_amount_raw']})")

        print("\n--- LINE ITEMS ---")
        if not extracted_data["items"]:
            print("No items detected.")
        else:
            for i, item in enumerate(extracted_data["items"], 1):
                print(f"{i}. {item['description']} | Qty: {item['qty']} | Unit: {item['unit_price']} | Total: {item['line_total']}")

    except Exception as e:
        print(f"Critical Error: {e}")


if __name__ == "__main__":
    main()
