import os
import re
import shutil
import subprocess

def setup_poppler():
    """Automatically find Poppler bin path on macOS/Linux/Windows."""
    poppler_bin = shutil.which("pdftotext")
    if poppler_bin:
        bin_path = os.path.dirname(poppler_bin)
        os.environ["PATH"] += os.pathsep + bin_path
        return True
    return False

def extract_dynamic_heuristics(text):
    data = {"invoice_number": None, "date": None, "total_amount": None, "items": []}
    lines = [line.rstrip() for line in text.split('\n')]
    
    # --- Metadata Extraction ---
    # Patterns for each field (label patterns)
    field_patterns = {
        "invoice_number": [
            r"invoice\s*(?:no|number|#|id)\s*[:\.]?\s*",
            r"inv\s*(?:no|#)\s*[:\.]?\s*",
            r"document\s*no\s*[:\.]?\s*",
            r"bill\s*no\s*[:\.]?\s*",
            r"order\s*no\s*[:\.]?\s*",
            r"purchase\s*order\s*no\s*[:\.]?\s*"
        ],
        "date": [
            r"date\s*[:\.]?\s*",
            r"issued\s*on\s*[:\.]?\s*",
            r"billing\s*date\s*[:\.]?\s*",
            r"invoice\s*date\s*[:\.]?\s*",
            r"date\s*of\s*issue\s*[:\.]?\s*",
            r"delivery\s*date\s*[:\.]?\s*"
        ],
        "total_amount": [
            r"total\s*(?:amount|due|payable)\s*[:\.]?\s*",
            r"grand\s*total\s*[:\.]?\s*",
            r"amount\s*due\s*[:\.]?\s*",
            r"total\s*balance\s*[:\.]?\s*",
            r"net\s*amount\s*[:\.]?\s*",
            r"total\s*price\s*[:\.]?\s*",
            r"amount\s*to\s*pay\s*[:\.]?\s*",
            r"total\s*due\s*[:\.]?\s*",
            r"balance\s*due\s*[:\.]?\s*"
        ]
    }
    
    # Helper to check if a line looks like a field label (for any field)
    def looks_like_label(line):
        line_lower = line.lower()
        for patterns in field_patterns.values():
            for p in patterns:
                if re.search(p, line_lower):
                    return True
        return False
    
    # Extract each field
    for field, patterns in field_patterns.items():
        if data[field] is not None:
            continue
        found = False
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            for pattern in patterns:
                # Try to match the pattern at the beginning of the line (after stripping)
                match = re.match(pattern, line_stripped, re.IGNORECASE)
                if match:
                    # Extract the rest of the line after the pattern
                    value = line_stripped[match.end():].strip()
                    if value:
                        data[field] = value
                        found = True
                        break
                    # If no value on same line, look ahead
                    if not found:
                        for j in range(i+1, min(i+4, len(lines))):
                            candidate = lines[j].strip()
                            if candidate and not looks_like_label(candidate):
                                data[field] = candidate
                                found = True
                                break
                    if found:
                        break
            if found:
                break
        # Fallback for date and total_amount
        if not data[field]:
            if field == "date":
                # Fallback: look for a date pattern in the text
                date_patterns = [
                    r"(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})",
                    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
                    r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})"
                ]
                for dp in date_patterns:
                    match = re.search(dp, text, re.IGNORECASE)
                    if match:
                        data[field] = match.group(0).strip()
                        break
            elif field == "total_amount":
                # Fallback: look for a number with two decimal places
                money_matches = re.findall(r"[\$£€]?\s*([\d,]+(?:\.\d{2}))", text)
                if money_matches:
                    # Take the last one that looks like a total (often the largest number)
                    try:
                        amounts = [float(m.replace(',', '')) for m in money_matches]
                        if amounts:
                            idx = amounts.index(max(amounts))
                            data[field] = money_matches[idx].replace(',', '')
                    except ValueError:
                        data[field] = money_matches[-1].replace(',', '')
    
    # --- Line Item Extraction (Row-wise tables) ---
    # Look for a header line that contains at least two item-related keywords
    item_keywords = ["description", "item", "qty", "quantity", "unit price", "price", "amount", "line total"]
    header_index = -1
    for i, line in enumerate(lines):
        line_lower = line.lower()
        # Count how many item keywords are in this line
        count = sum(1 for kw in item_keywords if kw in line_lower)
        if count >= 2:
            header_index = i
            break
    
    if header_index != -1:
        header_line = lines[header_index]
        # Split header by 2 or more spaces or tabs
        header_fields = [field.strip() for field in re.split(r'\s{2,}|\t', header_line) if field.strip()]
        
        # Collect data lines until we hit a total/subtotal keyword or empty line
        data_lines = []
        for i in range(header_index + 1, len(lines)):
            line = lines[i].strip()
            if not line:
                break
            line_lower = line.lower()
            if any(kw in line_lower for kw in ["subtotal", "tax", "total", "balance", "grand total", "amount due"]):
                break
            data_lines.append(line)
        
        # Process each data line
        for data_line in data_lines:
            # Split by 2 or more spaces or tabs
            data_fields = [field.strip() for field in re.split(r'\s{2,}|\t', data_line) if field.strip()]
            if len(data_fields) == len(header_fields):
                item = {}
                for h, d in zip(header_fields, data_fields):
                    # Normalize header to a key
                    key = h.lower().replace(' ', '_').replace('-', '_')
                    item[key] = d
                # Map to standard fields
                std_item = {
                    "description": "",
                    "qty": "",
                    "unit_price": "",
                    "line_total": ""
                }
                for key, value in item.items():
                    if 'description' in key or 'item' in key:
                        std_item["description"] = value
                    elif 'qty' in key or 'quantity' in key:
                        std_item["qty"] = value
                    elif 'unit' in key and 'price' in key:
                        std_item["unit_price"] = value
                    elif 'price' in key and 'unit' not in key:  # fallback for price
                        if not std_item["unit_price"]:
                            std_item["unit_price"] = value
                    elif ('line' in key and 'total' in key) or key == 'amount' or key == 'total':
                        std_item["line_total"] = value
                # Only add if we have at least description and one other field
                if std_item["description"] and (std_item["qty"] or std_item["unit_price"] or std_item["line_total"]):
                    data["items"].append(std_item)
    
    # Fallback: if no items found, try to find lines that look like they contain item data (description followed by numbers)
    if not data["items"]:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip lines that are clearly headers or totals
            line_lower = line.lower()
            if any(kw in line_lower for kw in ["description", "item", "qty", "quantity", "unit", "price", "amount", "subtotal", "total", "balance"]):
                continue
            # Look for a pattern: text followed by at least two numbers
            # We'll split by spaces and see if we have at least 3 tokens where the last two are numbers
            tokens = re.split(r'\s+', line)
            if len(tokens) >= 3:
                # Check if the last two tokens are numbers (with possible decimal/comma)
                last_two = tokens[-2:]
                if all(re.match(r'^[\d,.]+$', t) for t in last_two):
                    # Assume the first token(s) is the description, and we have at least qty and unit_price or line_total
                    description = ' '.join(tokens[:-2])
                    # We have two numbers: let's assume they are qty and unit_price, and we don't have line_total
                    # Or if we have three numbers, then qty, unit_price, line_total
                    if len(tokens) == 3:
                        std_item = {
                            "description": description,
                            "qty": tokens[-2],
                            "unit_price": tokens[-1],
                            "line_total": ""  # we don't have line_total
                        }
                    elif len(tokens) >= 4:
                        # Check if the third last is also a number
                        if re.match(r'^[\d,.]+$', tokens[-3]):
                            std_item = {
                                "description": ' '.join(tokens[:-3]),
                                "qty": tokens[-3],
                                "unit_price": tokens[-2],
                                "line_total": tokens[-1]
                            }
                        else:
                            # Only two numbers at the end
                            std_item = {
                                "description": ' '.join(tokens[:-2]),
                                "qty": tokens[-2],
                                "unit_price": tokens[-1],
                                "line_total": ""
                            }
                    else:
                        continue
                    if std_item["description"] and (std_item["qty"] or std_item["unit_price"]):
                        data["items"].append(std_item)
                        # Break after a few to avoid too many false positives
                        if len(data["items"]) >= 5:
                            break
    
    return data

def main():
    if not setup_poppler():
        print("Error: Poppler not found. Run 'brew install poppler'")
        return

    # Process all PDFs in the file directory
    pdf_dir = "/Users/ap/ocr-dynamic-gem-main/file"
    if not os.path.exists(pdf_dir):
        print(f"Error: Directory not found at {pdf_dir}")
        return

    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("No PDF files found in the directory.")
        return

    for pdf_file in pdf_files:
        pdf_path = os.path.join(pdf_dir, pdf_file)
        print(f"\n{'='*50}")
        print(f"Processing: {pdf_file}")
        print('='*50)

        try:
            print(f"Extracting text...")
            result = subprocess.run(["pdftotext", pdf_path, "-"], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Error running pdftotext: {result.stderr}")
                continue
            raw_text = result.stdout
            
            extracted_data = extract_dynamic_heuristics(raw_text)

            print("\n--- METADATA ---")
            print(f"Invoice #: {extracted_data['invoice_number'] or 'Not found'}")
            print(f"Date     : {extracted_data['date'] or 'Not found'}")
            print(f"Total    : {extracted_data['total_amount'] or 'Not found'}")

            print("\n--- LINE ITEMS ---")
            if not extracted_data["items"]:
                print("No items detected.")
            else:
                for i, item in enumerate(extracted_data["items"], 1):
                    desc = item.get('description', 'N/A')
                    qty = item.get('qty', 'N/A')
                    unit = item.get('unit_price', 'N/A')
                    total = item.get('line_total', 'N/A')
                    print(f"{i}. {desc} | Qty: {qty} | Unit: {unit} | Total: {total}")

        except Exception as e:
            print(f"Critical Error: {e}")

if __name__ == "__main__":
    main()