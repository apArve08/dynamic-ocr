
dynamic_extractor - use llm 

dynamic_parsing - use Heuristic Parsing (Smart Rules)




Based on the analysis of dynamic_parsing.py and dynamic_extractor.py, here are the requirements to run this project:
    
    1. Python Libraries
    You need to install the following packages via pip:
    
    bash
    pip install invoice2data requests
    
    
    *   invoice2data: Used for PDF text extraction (pdftotext).
    *   requests: Used in dynamic_extractor.py to communicate with the local LLM API.
    *   Note: os, re, and json are part of the Python Standard Library and do not need installation.
    
    2. System Dependencies (Critical)
    Both scripts rely on Poppler to extract text from PDFs. 
    *   Installation: You must install Poppler on your system.
    *   Configuration: The scripts contain a hardcoded path to Poppler:
        C:\Users\804748\poppler\poppler-26.02.0\Library\bin
        You must update this path in both .py files to point to where Poppler is installed on your actual machine.
    
    3. Local LLM Setup (for dynamic_extractor.py)
    The dynamic_extractor.py script is designed to work with Ollama:
    *   Ollama: Must be installed and running on http://localhost:11434.
    *   Model: You need to pull the specific model mentioned in the code:
        bash
        ollama pull granite4.1:3b
        
        (Note: The code comment mentions glm-ocr:q8_0, but the actual request uses granite4.1:3b. Ensure you have the model specified in the json payload.)
    