# Summary of improvements to dynamic_parsing.py:
#
# 1. Enhanced block-based item extraction (_extract_items_block_based):
#    - Handles both embedded header/data format (e.g., ['DESCRIPTION', 'value1', 'value2'])
#      and separate header/data format (e.g., ['DESCRIPTION'], ['value1'], ['value2']).
#    - Filters out ignore blocks (addresses, contact info) to reduce noise.
#    - Finds the longest consecutive sequence of header blocks to identify the table header.
#    - For each header block, extracts the header term and collects all data lines in that block.
#    - Pads columns to equal length and transposes to form rows.
#
# 2. Kept the line-based fallback (_extract_items_line_based) for row-major tables.
#
# 3. Improved robustness by adding ignore block detection and better header/data splitting.
#
# 4. The script now successfully extracts line items from notax2.pdf (which has a column-major table)
#    while still processing other PDFs without errors.
#
# 5. Metadata extraction (invoice number, date, total) remains unchanged and works for several PDFs.
#
# Tested on the four sample PDFs in the ./file directory:
#   - invoiceClaude.pdf: metadata extracted, no items detected (no clear item table found)
#   - purchase-order-1.pdf: metadata extracted, no items detected
#   - notax1.pdf: metadata extracted, no items detected
#   - notax2.pdf: metadata extracted and 5 line items detected correctly.
#
# The script is now better equipped to handle dynamic invoice formats with varying layouts.