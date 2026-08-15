import os
import re
import shutil
from invoice2data.input import pdftotext

def setup_poppler():
    """Automatically find Poppler bin path on macOS/Linux/Windows."""
    poppler_bin = shutil.which("pdftotext")
    if poppler_bin:
        bin_path = os.path.dirname(poppler_bin)
        os.environ["PATH"] += os.pathsep + bin_path
        return True
    return False

def extract_dynamic_heuristics(text):
    # --- CONFIGURATION: ALIASES ---
    # Adding more variations helps catch different invoice styles
    KEYWORDS = {
        "invoice_number": [
            r"invoice\s*(?:no|number|#|id)", 
            r"inv\s*(?:no|#)", 
            r"document\s*no", 
            r"bill\s*no"
        ],
        "date": [
            r"date", 
            r"issued\s*on", 
            r"billing\s*date"
        ],
        "total_amount": [
            r"total\s*(?:amount|due|payable)", 
            r"grand\s*total", 
            r"amount\s*due", 
            r"total\s*balance", 
            r"net\s*amount"
        ]
    }

    data = {"invoice_number": None, "date": None, "total_amount": None}

    # 1. Extract Invoice Number
    for pattern in KEYWORDS["invoice_number"]:
        match = re.search(f"{pattern}[:\s\.\-]*([A-Z0-9\-\/]+)", text, re.IGNORECASE)
        if match:
            data["invoice_number"] = match.group(1).strip()
            break

    # 2. Extract Date
    date_regex = r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"
    for pattern in KEYWORDS["date"]:
        match = re.search(f"{pattern}[:\s\.\-]*{date_regex}", text, re.IGNORECASE)
        if match:
            data["date"] = match.group(1).strip()
            break
    
    if not data["date"]:
        fallback_date = re.search(date_regex, text)
        if fallback_date:
            data["date"] = fallback_date.group(1)

    # 3. Extract Total Amount
    amount_regex = r"([$\s]*\d{1,3}(?:[.,]\d{3})*[.,]\d{2})"
    all_totals = []
    for pattern in KEYWORDS["total_amount"]:
        matches = re.finditer(f"{pattern}[:\s\.\-\$]*{amount_regex}", text, re.IGNORECASE)
        for m in matches:
            all_totals.append(m.group(1))
    
    if all_totals:
        raw_total = all_totals[-1] 
        data["total_amount"] = re.sub(r"[^\d.,]", "", raw_total)

    return data

def main():
    if not setup_poppler():
        print("Error: Poppler (pdftotext) not found. Install it via 'brew install poppler'")
        return

    # Adjusted for your Mac path
    pdf_path = "/Users/ap/ocr-dynamic-gem-main/file/invoiceClaude.pdf"

    if not os.path.exists(pdf_path):
        print(f"Error: File not found at {pdf_path}")
        return

    try:
        print(f"Processing: {os.path.basename(pdf_path)}...")
        raw_text = pdftotext.to_text(pdf_path)
        
        extracted_data = extract_dynamic_heuristics(raw_text)
        
        print("\n--- DYNAMICALLY EXTRACTED DATA ---")
        for key, value in extracted_data.items():
            print(f"{key:15}: {value}")

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    main()
