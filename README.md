# OCR Dynamic Parsing

A project to extract billing data from PDF invoices using two different strategies: Heuristic-based parsing and LLM-based extraction.

## 🚀 Quick Start

### 1. System Dependencies
This project requires **Poppler** for PDF text extraction.
```bash
brew install poppler
```

### 2. Python Installation
```bash
pip install invoice2data requests
```

### 3. Running the scripts
- **Heuristic Approach**: `python3 dynamic_parsing.py` (Fast, rule-based)
- **LLM Approach**: `python3 dynamic_extractor.py` (Flexible, requires Ollama)

## 🛠️ Features
- **Dynamic Heuristics**: Uses alias-based keyword mapping to handle various invoice formats.
- **Local LLM Integration**: Connects to Ollama (e.g., Granite or Llama3) for semantic data extraction.
- **Automatic Path Resolution**: Detects Poppler installation paths automatically on macOS.

## 📂 Project Structure
- `dynamic_parsing.py`: Heuristic extraction logic.
- `dynamic_extractor.py`: LLM-based extraction logic.
- `/file`: Sample PDF invoices.
