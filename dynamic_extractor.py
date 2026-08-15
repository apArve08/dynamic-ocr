import os
import requests
import json
from invoice2data.input import pdftotext

# 1. Setup Poppler for pdftotext
poppler_bin_path = r"/opt/homebrew/bin/pdftotext" # Adjust to your actual path
os.environ["PATH"] += os.pathsep + poppler_bin_path
pdf_path = r"/Users/ap/ocr-dynamic-gem-main/file/notax1.pdf"
# /Users/ap/ocr-dynamic-gem-main/file/demo-invoice-no-tax-2.pdf
try:
    # 2. Extract Raw Text using pdftotext
    print("Extracting text from PDF...")
    raw_text = pdftotext.to_text(pdf_path)

    # 3. Create a dynamic prompt for the LLM
    # We enforce JSON output so it can be used programmatically
    prompt = f"""
    You are a data extraction AI. Extract the core billing details from the invoice text below.
    Return ONLY a valid JSON object using exactly these keys:
    - "issuer" (Company name providing the invoice)
    - "invoice_number"
    - "date" (Format as YYYY-MM-DD if possible)
    - "total_amount or total" (Number only,with decimal points, no currency symbols)
    - "tax_amount" (If not present, return null) normally in Malaysia, it is called SST or GST

    If a field cannot be found, set its value to null. Do not include markdown or explanations.

    Invoice Text:
    ---
    {raw_text}
    ---
    """

    # 4. Send to Local Ollama instance (e.g., Llama 3)
    print("Sending text to local LLM for dynamic parsing...")
    response = requests.post('http://localhost:11434/api/generate', json={
        "model": "glm-ocr:q8_0",  # Ensure you have pulled this model via Ollama glm-ocr:q8_0
        "prompt": prompt,
        "format": "json",   # Forces the LLM to output valid JSON
        "stream": False
    })

    if response.status_code == 200:
        # 5. Parse the dynamic JSON response
        extracted_data = json.loads(response.json()['response'])
        print("\n--- DYNAMICALLY EXTRACTED DATA ---")
        for key, value in extracted_data.items():
            print(f"{key}: {value}")
    else:
        print(f"Error from LLM: {response.status_code}")

except Exception as e:
    print(f"Extraction Pipeline Failed: {e}")