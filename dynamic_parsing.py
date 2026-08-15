
import os
import re
from invoice2data.input import pdftotext

# 1. Setup Poppler Path
poppler_bin_path = r"/opt/homebrew/bin/pdftotext" # Adjust to your actual path
os.environ["PATH"] += os.pathsep + poppler_bin_path
pdf_path = r"/Users/ap/ocr-dynamic-gem-main/file/invoiceClaude.pdf"
# /Users/ap/ocr-dynamic-gem-main/file/demo-invoice-no-tax-2.pdf
def extract_dynamic_heuristics(text):
    data = {
        "invoice_number": None,
        "date": None,
        "total_amount": None
    }    

    # RULE 1: Find the Invoice Number
    # Looks for "Invoice No:", "Inv #", "Invoice Number", etc., followed by letters/numbers
    inv_pattern = r'(?:invoice\s*no|inv\s*#|invoice\s*number|invoice\s*id)[\s:\.\-]*([A-Z0-9\-]+)'
    inv_matches = re.findall(inv_pattern, text, re.IGNORECASE)
    if inv_matches:
        data["invoice_number"] = inv_matches[0]

    # RULE 2: Find the Date
    # Matches common formats: YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY
    date_pattern = r'\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\b'
    date_matches = re.findall(date_pattern, text)
    if date_matches:
        data["date"] = date_matches[0] # Usually the first date is the invoice date

    # RULE 3: Find the Total Amount
    # Looks for "Total", "Amount Due", or "Balance", allows some spaces/symbols, then captures the money format
    # Example: "Total Due: $1,234.56" -> extracts "1,234.56"
    amount_pattern = r'(?:total|amount due|balance|total amount)[\s:\.\-\$]*([\d,]+\.\d{2})'
    amount_matches = re.findall(amount_pattern, text, re.IGNORECASE)
    
    if amount_matches:
        # We take the LAST match, because invoices often have "Subtotal" first, and the grand "Total" at the bottom
        data["total_amount"] = amount_matches[-1]

    return data

try:
    # Extract raw text
    raw_text = pdftotext.to_text(pdf_path)
    
    # Run our dynamic rules
    extracted_data = extract_dynamic_heuristics(raw_text)
    
    print("--- DYNAMICALLY EXTRACTED DATA (NO LLM) ---")
    for key, value in extracted_data.items():
        print(f"{key}: {value}")

except Exception as e:
    print(f"Error: {e}")