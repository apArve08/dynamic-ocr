import os
import requests
import json
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

def extract_with_llm(text):
    """Sends raw PDF text to a local Ollama instance for semantic extraction."""
    
    # Advanced Prompt to handle the "flattened" text issue
    prompt = f"""
    You are a professional invoice parsing AI. I will provide you with raw text extracted from a PDF invoice.
    The text may be messy because the table columns were flattened.
    
    Your task is to extract the following fields into a valid JSON object:
    1. "invoice_number": The unique ID of the invoice.
    2. "date": The invoice date (format as YYYY-MM-DD).
    3. "total_amount": The final grand total amount (number only, no currency symbols).
    4. "items": A list of objects, each containing:
       - "description": The name/details of the item.
       - "quantity": The number of units.
       - "unit_price": Price per unit.
       - "line_total": Total price for that line.

    Constraints:
    - If a field is not found, set it to null.
    - Do NOT invent data.
    - Return ONLY a valid JSON object. No markdown, no explanations.

    Invoice Text:
    ---
    {text}
    ---
    """

    try:
        # Using Ollama API
        response = requests.post('http://localhost:11434/api/generate', json={
            "model": "llama3.2:3b",  # You can change this to "llama3.1" or "mistral" for higher accuracy
            "prompt": prompt,
            "format": "json", 
            "stream": False
        }, timeout=60)

        if response.status_code == 200:
            return json.loads(response.json()['response'])
        else:
            print(f"LLM API Error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

def main():
    if not setup_poppler():
        print("Error: Poppler not found. Please run 'brew install poppler'")
        return

    # List of files to process for testing
    test_files = [
        "/Users/ap/ocr-dynamic-gem-main/file/invoiceClaude.pdf",
        "/Users/ap/ocr-dynamic-gem-main/file/purchase-order-1.pdf",
        "/Users/ap/ocr-dynamic-gem-main/file/notax1.pdf",
        "/Users/ap/ocr-dynamic-gem-main/file/notax2.pdf"
    ]

    for pdf_path in test_files:
        if not os.path.exists(pdf_path):
            print(f"\nSkipping {os.path.basename(pdf_path)} (File not found)")
            continue

        try:
            print(f"\n{'='*50}")
            print(f"Processing: {os.path.basename(pdf_path)}")
            print(f"{'='*50}")
            
            # 1. Extract Raw Text
            raw_text = pdftotext.to_text(pdf_path)
            
            # 2. Parse with LLM
            result = extract_with_llm(raw_text)
            
            if result:
                print("\n--- METADATA ---")
                print(f"Invoice #: {result.get('invoice_number')}")
                print(f"Date     : {result.get('date')}")
                print(f"Total    : {result.get('total_amount')}")
                
                print("\n--- LINE ITEMS ---")
                items = result.get('items', [])
                if not items:
                    print("No items detected.")
                else:
                    for i, item in enumerate(items, 1):
                        desc = item.get('description', 'N/A')
                        qty = item.get('quantity', 'N/A')
                        up = item.get('unit_price', 'N/A')
                        lt = item.get('line_total', 'N/A')
                        print(f"{i}. {desc} | Qty: {qty} | Unit: {up} | Total: {lt}")
            else:
                print("Failed to extract data using LLM.")

        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")

if __name__ == "__main__":
    main()
