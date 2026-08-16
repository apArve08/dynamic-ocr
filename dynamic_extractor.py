import argparse
import json
import os
import sys

import requests
from invoice2data.input import pdftotext

# Reuse the heuristic module's Poppler setup and normalizers so both extraction
# paths emit the same shapes (ISO dates, Decimal amounts).
from dynamic_parsing import parse_date, parse_money, setup_poppler

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "glm-ocr:q8_0"
DEFAULT_TIMEOUT = 120

# Passed to Ollama's `format` field. A real schema (rather than the string
# "json") constrains decoding, so the model cannot invent or rename keys.
INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "issuer": {"type": ["string", "null"]},
        "invoice_number": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"]},
        "total_amount": {"type": ["string", "null"]},
        "tax_amount": {"type": ["string", "null"]},
    },
    "required": ["issuer", "invoice_number", "date", "total_amount", "tax_amount"],
}

PROMPT_TEMPLATE = """You are a data extraction AI. Extract the core billing details from the invoice text below.
Return ONLY a valid JSON object using exactly these keys:
- "issuer" (Company name providing the invoice)
- "invoice_number"
- "date" (Format as YYYY-MM-DD if possible)
- "total_amount" (Number only, with decimal points, no currency symbols)
- "tax_amount" (Number only. In Malaysia this is labelled SST or GST. If not present, return null)

If a field cannot be found, set its value to null. Do not include markdown or explanations.

Invoice Text:
---
{raw_text}
---
"""


def extract_with_llm(raw_text, model=DEFAULT_MODEL, timeout=DEFAULT_TIMEOUT):
    """Ask a local Ollama model for the billing fields. Raises on transport failure."""
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": PROMPT_TEMPLATE.format(raw_text=raw_text),
            "format": INVOICE_SCHEMA,
            "stream": False,
            # Extraction should be reproducible run to run.
            "options": {"temperature": 0},
        },
        timeout=timeout,
    )
    response.raise_for_status()

    payload = response.json()
    if "response" not in payload:
        raise ValueError(f"Ollama returned no 'response' field: {payload}")
    return json.loads(payload["response"])


def normalize(extracted):
    """Coerce the model's strings into the same types the heuristic path returns."""
    return {
        "issuer": extracted.get("issuer") or None,
        "invoice_number": extracted.get("invoice_number") or None,
        "date": parse_date(extracted.get("date")),
        "date_raw": extracted.get("date") or None,
        "total_amount": parse_money(extracted.get("total_amount")),
        "total_amount_raw": extracted.get("total_amount") or None,
        "tax_amount": parse_money(extracted.get("tax_amount")),
        "tax_amount_raw": extracted.get("tax_amount") or None,
    }


def main():
    parser = argparse.ArgumentParser(description="Extract invoice fields with a local LLM.")
    parser.add_argument("pdf", nargs="?", default="file/notax1.pdf", help="Path to the PDF invoice")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Seconds to wait for Ollama")
    args = parser.parse_args()

    if not setup_poppler():
        print("Error: Poppler not found. Run 'brew install poppler'", file=sys.stderr)
        return 1

    if not os.path.exists(args.pdf):
        print(f"Error: File not found at {args.pdf}", file=sys.stderr)
        return 1

    # Each failure mode reports what actually went wrong rather than collapsing
    # into one indistinguishable message.
    try:
        print(f"Extracting text from {os.path.basename(args.pdf)}...")
        raw_text = pdftotext.to_text(args.pdf)
    except (OSError, FileNotFoundError) as e:
        print(f"PDF text extraction failed: {e}", file=sys.stderr)
        return 1

    try:
        print(f"Sending text to {args.model} for dynamic parsing...")
        extracted = extract_with_llm(raw_text, model=args.model, timeout=args.timeout)
    except requests.exceptions.ConnectionError:
        print(f"Cannot reach Ollama at {OLLAMA_URL}. Is 'ollama serve' running?", file=sys.stderr)
        return 1
    except requests.exceptions.Timeout:
        print(f"Ollama did not respond within {args.timeout}s.", file=sys.stderr)
        return 1
    except requests.exceptions.HTTPError as e:
        print(f"Ollama returned an error: {e}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Could not parse the model's JSON output: {e}", file=sys.stderr)
        return 1

    data = normalize(extracted)
    print("\n--- DYNAMICALLY EXTRACTED DATA ---")
    print(f"Issuer     : {data['issuer']}")
    print(f"Invoice #  : {data['invoice_number']}")
    print(f"Date       : {data['date']}  (raw: {data['date_raw']})")
    print(f"Total      : {data['total_amount']}  (raw: {data['total_amount_raw']})")
    print(f"Tax        : {data['tax_amount']}  (raw: {data['tax_amount_raw']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
