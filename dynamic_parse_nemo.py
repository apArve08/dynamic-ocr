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
            r"invoice\s*(?:no|number|#|id)",
            r"inv\s*(?:no|#)",
            r"document\s*no",
            r"bill\s*no",
            r"order\s*no",
            r"purchase\s*order\s*no",
            r"ocr\s*nr"  # sometimes invoice number is labeled as OCR-nr
        ],
        "date": [
            r"date",
            r"issued\s*on",
            r"billing\s*date",
            r"invoice\s*date",
            r"date\s*of\s*issue",
            r"delivery\s*date",
            r"due\s*date"
        ],
        "total_amount": [
            r"total\s*(?:amount|due|payable)",
            r"grand\s*total",
            r"amount\s*due",
            r"total\s*balance",
            r"net\s*amount",
            r"total\s*price",
            r"amount\s*to\s*pay",
            r"total\s*due",
            r"balance\s*due",
            r"amount"  # sometimes just "Amount"
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
            line_lower = line_stripped.lower()
            for pattern in patterns:
                # Try to match the pattern in the line (could be at start or middle)
                match = re.search(pattern, line_lower)
                if match:
                    # We found a label, now try to extract the value
                    # Option 1: value on same line after the label
                    value_same_line = line_stripped[match.end():].strip()
                    if value_same_line:
                        data[field] = value_same_line
                        found = True
                        break
                    # Option 2: value on next non-empty line(s) that doesn't look like a label
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
    
    # --- Line Item Extraction: Block-based Method ---
    # Define what constitutes a header line for the item table
    item_header_keywords = set([
        'description', 'item', 'qty', 'quantity', 'unit price', 'price', 
        'amount', 'line total', 'rebate', 'tax', 'unit', 'line', 'item #', '#'
    ])
    # Define keywords that indicate the end of the item table (total lines)
    total_keywords = set([
        'subtotal', 'tax', 'total', 'balance', 'grand total', 'amount due'
    ])
    
    # Helper to check if a block is a header block (not empty, contains an item header keyword, and is not a total block)
    def is_header_block(block):
        if not block:
            return False
        combined = ' '.join(block).lower()
        # Skip if it's a total block
        if any(tk in combined for tk in total_keywords):
            return False
        # Check if it contains any item header keyword
        return any(hk in combined for hk in item_header_keywords)
    
    # Helper to check if a block is a data block (not empty, not a header block, and not a total block)
    def is_data_block(block):
        if not block:
            return False
        combined = ' '.join(block).lower()
        # Skip if it's a total block
        if any(tk in combined for tk in total_keywords):
            return False
        # Skip if it's a header block
        if is_header_block(block):
            return False
        return True
    
    # Step 1: Split the text into blocks of consecutive non-empty lines (separated by one or more empty lines).
    blocks = []
    current_block = []
    for line in lines:
        if line.strip() == '':
            if current_block:
                blocks.append(current_block)
                current_block = []
        else:
            current_block.append(line.strip())
    if current_block:
        blocks.append(current_block)
    
    # Step 2: Find the first header block index.
    header_start = -1
    for i, block in enumerate(blocks):
        if is_header_block(block):
            header_start = i
            break
    
    if header_start != -1:
        # Step 3: Collect consecutive header blocks starting from header_start
        header_blocks = []
        i = header_start
        while i < len(blocks) and is_header_block(blocks[i]):
            header_blocks.append(blocks[i])
            i += 1
        
        # Step 4: After the header sequence, collect all consecutive non-header blocks (candidate data blocks)
        data_blocks = []
        while i < len(blocks) and is_data_block(blocks[i]):
            data_blocks.append(blocks[i])
            i += 1
        
        # Now we have header_blocks and data_blocks.
        # We expect the number of data blocks to be at least the number of header blocks.
        # If we have more data blocks than header blocks, we take the first len(header_blocks) data blocks.
        # If we have fewer, we pad with empty blocks.
        if len(data_blocks) < len(header_blocks):
            # Pad data_blocks with empty blocks
            data_blocks.extend([[]] * (len(header_blocks) - len(data_blocks)))
        else:
            # Truncate data_blocks to the first len(header_blocks) blocks
            data_blocks = data_blocks[:len(header_blocks)]
        
        # Step 5: If we still have more header blocks than data blocks (shouldn't happen after above, but just in case),
        # we try to merge consecutive header blocks from the end backwards until the counts match.
        while len(header_blocks) > len(data_blocks) and len(header_blocks) > 1:
            # Merge the last two header blocks: combine their lines into one block.
            merged_block = header_blocks[-2] + header_blocks[-1]
            header_blocks = header_blocks[:-2] + [merged_block]
        # If after merging we still have more header blocks than data blocks, we truncate header_blocks (shouldn't happen)
        if len(header_blocks) > len(data_blocks):
            header_blocks = header_blocks[:len(data_blocks)]
        # If we have fewer header blocks than data blocks, we pad header_blocks with empty blocks
        while len(header_blocks) < len(data_blocks):
            header_blocks.append([])
        
        # Now we have equal numbers of header_blocks and data_blocks.
        # Step 6: Combine lines in each header block to form a header string.
        header_strings = []
        for block in header_blocks:
            header_strings.append(' '.join(block))
        
        # Step 7: Pad each data block to the maximum length of any data block
        max_len = 0
        for block in data_blocks:
            if len(block) > max_len:
                max_len = len(block)
        for idx in range(len(data_blocks)):
            block = data_blocks[idx]
            if len(block) < max_len:
                block.extend([''] * (max_len - len(block)))
        
        # Step 8: Now create items: each row is formed by taking the i-th element from each data block.
        for row_idx in range(max_len):
            item = {}
            for col_idx, header in enumerate(header_strings):
                value = data_blocks[col_idx][row_idx] if row_idx < len(data_blocks[col_idx]) else ''
                item[header] = value
            
            # Map to standard fields
            std_item = {
                "description": "",
                "qty": "",
                "unit_price": "",
                "line_total": ""
            }
            for header, value in item.items():
                header_lower = header.lower()
                if 'description' in header_lower or 'item' in header_lower or 'desc' in header_lower:
                    std_item["description"] = value
                elif 'qty' in header_lower or 'quantity' in header_lower:
                    std_item["qty"] = value
                elif 'unit' in header_lower and 'price' in header_lower:
                    std_item["unit_price"] = value
                elif 'price' in header_lower and 'unit' not in header_lower:  # fallback for price
                    if not std_item["unit_price"]:
                        std_item["unit_price"] = value
                elif ('line' in header_lower and 'total' in header_lower) or header_lower == 'amount' or header_lower == 'total':
                    std_item["line_total"] = value
            # Only add if we have at least description and one other field
            if std_item["description"] and (std_item["qty"] or std_item["unit_price"] or std_item["line_total"]):
                data["items"].append(std_item)
    
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