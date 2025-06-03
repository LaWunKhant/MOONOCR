import sys
import json
import os
import easyocr
from PIL import Image
from pdf2image import convert_from_path
import numpy as np
import re
import math
import time

# Set the path to the Poppler bin directory
# Ensure this path is correct for your Poppler binaries
# For macOS installed via Homebrew, this is typically correct.
POPPLER_PATH = r'/opt/homebrew/opt/poppler/bin'

def process_document(file_path):
    """
    Processes a PDF or image file using EasyOCR with detail=1.
    Returns a list of (bbox, text, confidence) tuples.
    """
    try:
        # Initialize EasyOCR reader for English and Japanese
        # Set gpu=True if you have a compatible GPU
        reader = easyocr.Reader(['en', 'ja'], gpu=True)
        # print("DEBUG: EasyOCR reader initialized.", file=sys.stderr) # DEBUG
    except Exception as e:
        # print(f"Error initializing EasyOCR reader: {e}", file=sys.stderr)
        return None

    base_name = os.path.basename(file_path)
    file_extension = os.path.splitext(file_path)[1].lower()

    images = []
    if file_extension == '.pdf':
        try:
            # Convert PDF to a list of PIL images
            images = convert_from_path(file_path, dpi=300, poppler_path=POPPLER_PATH, thread_count=2)
            # print(f"DEBUG: Successfully converted PDF to {len(images)} images.", file=sys.stderr) # DEBUG
        except Exception as e:
            # print(f"Error converting PDF '{file_path}': {e}", file=sys.stderr)
            return None
    elif file_extension in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        try:
            # Load image file
            images.append(Image.open(file_path))
            # print(f"Loaded image file: {file_path}", file=sys.stderr) # DEBUG
        except Exception as e:
            # print(f"Error loading image '{file_path}': {e}", file=sys.stderr)
            return None
    else:
        # print(f"Unsupported file type: {file_extension}", file=sys.stderr)
        return None

    if not images:
        # print("No images to process after conversion/loading.", file=sys.stderr) # DEBUG
        return None

    all_ocr_results = []
    for i, image in enumerate(images):
        try:
            numpy_image = np.array(image.convert('RGB'))
            results = reader.readtext(numpy_image, detail=1)
            all_ocr_results.extend(results)
            # print(f"DEBUG: Processed page {i+1} with {len(results)} text blocks.", file=sys.stderr) # DEBUG
        except Exception as e:
            # print(f"Error during OCR on page {i+1}: {e}", file=sys.stderr)
            pass # Suppress error for individual page OCR failures

    # Sort all OCR results vertically first - useful for spatial processing
    all_ocr_results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))

    return all_ocr_results # Return list of (bbox, text, confidence)

def extract_invoice_data(ocr_results):
    """
    Extracts structured invoice data from EasyOCR results (with detail=1).
    Uses regex for header/bank details and spatial analysis for line items and total.
    """
    invoice_data = {
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "vendor_name": None,
        "total_amount": None,
        "bank_name": None,
        "branch_name": None,
        "account_type": None,
        "account_number": None,
        "account_holder": None,
        "line_items": []
    }

    # Join all text into a single string for easier header/bank detail extraction (still useful for context)
    full_text = " ".join([text for (bbox, text, confidence) in ocr_results])
    # print(f"DEBUG: Full text snippet: {full_text[:500]}...", file=sys.stderr) # DEBUG

    # --- Header Information Extraction (using regex on joined text) ---
    # Invoice Number (請求書番号)
    inv_match = re.search(r'請求書番号\s*([\w-]+)', full_text)
    if inv_match:
        invoice_data["invoice_number"] = inv_match.group(1).strip()
        # print(f"DEBUG: Found Invoice Number: {invoice_data['invoice_number']}", file=sys.stderr) # DEBUG

    # Invoice Date (請求日) - Added flexibility for separators
    date_match = re.search(r'請求日\s*(\d{4}[/.-]\d{2}[/.-]\d{2})', full_text)
    if date_match:
        # Standardize date format to YYYY/MM/DD
        date_str = date_match.group(1)
        invoice_data["invoice_date"] = re.sub(r'[-.]', '/', date_str)
        # print(f"DEBUG: Found Invoice Date: {invoice_data['invoice_date']}", file=sys.stderr) # DEBUG

    # Payment Due Date (お支払期限) -> Renamed to "due_date"
    payment_due_match = re.search(r'お支払期限\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text) # Allow 1 or 2 digits for month/day
    if payment_due_match:
        invoice_data["due_date"] = payment_due_match.group(1).strip()
        # print(f"DEBUG: Found Due Date: {invoice_data['due_date']}", file=sys.stderr) # DEBUG

    # Vendor Name (Keep your existing vendor name regex, it seemed to work)
    vendor_pattern_1 = re.search(
        r'(?:〒\d{3}-\d{4}\s*|東京都|大阪府|愛知県|神奈川県|北海道|福島県|広島県|福岡県|京都府|千葉県|埼玉県|兵庫県|静岡県|茨城県|滋賀県|奈良県)[^(\n]*?((?:株式会社|有限会社|合同会社|合資会社|個人事業主)\s*[^(\n\d]+?)(?:御中|様)?',
        full_text,
        re.MULTILINE
    )
    if vendor_pattern_1:
        vendor_name_candidate = vendor_pattern_1.group(1).strip()
        vendor_name_candidate = re.sub(r'\s*(御中|様)$', '', vendor_name_candidate)
        invoice_data["vendor_name"] = vendor_name_candidate
        # print(f"DEBUG: Found Vendor Name (Pattern 1 - near address/TEL): {invoice_data['vendor_name']}", file=sys.stderr) # DEBUG
    
    if not invoice_data["vendor_name"]:
        vendor_pattern_2 = re.search(
            r'(\S+?(?:株式会社|有限会社|合同会社|合資会社))\s*(?:TEL|電話|FAX|〒|\d{3}-\d{4}|\d{2,4}-\d{2,4}-\d{4})',
            full_text
        )
        if vendor_pattern_2:
            invoice_data["vendor_name"] = vendor_pattern_2.group(1).strip()
            # print(f"DEBUG: Found Vendor Name (Pattern 2 - near contact detail): {invoice_data['vendor_name']}", file=sys.stderr) # DEBUG
    
    if not invoice_data["vendor_name"]:
        vendor_pattern_3 = re.search(
            r'(\S+?(?:株式会社|有限会社|合同会社|合資会社))',
            full_text
        )
        if vendor_pattern_3:
            invoice_data["vendor_name"] = vendor_pattern_3.group(1).strip()
            # print(f"DEBUG: Found Vendor Name (Pattern 3 - generic company): {invoice_data['vendor_name']}", file=sys.stderr) # DEBUG>

    # --- Total Amount Extraction (Spatial Approach - Prioritize ご請求金額) ---
    total_amount_value = None
    print("DEBUG: Attempting spatial search for total amount (Prioritizing ご請求金額).", file=sys.stderr)

    # Keywords to search near
    primary_total_keyword_labels = ["ご請求金額"]
    secondary_total_keyword_labels = ["合計", "総合計"] # Fallback keywords

    # Find bounding boxes for these keywords with high confidence
    primary_keyword_block = None
    secondary_keyword_block = None
    
    for (bbox, text, confidence) in ocr_results:
         normalized_text = text.strip().lower()
         if any(kw in normalized_text for kw in primary_total_keyword_labels) and confidence > 0.7:
             # Find the best "ご請求金額" block (e.g., highest confidence) if multiple exist
             if primary_keyword_block is None or confidence > primary_keyword_block["confidence"]:
                 primary_keyword_block = {"bbox": bbox, "text": text, "confidence": confidence}
                 print(f"DEBUG: Found primary total keyword '{primary_keyword_block['text']}' at {bbox} with confidence {confidence:.2f}", file=sys.stderr)

         elif any(kw in normalized_text for kw in secondary_total_keyword_labels) and confidence > 0.7:
              # Find the best "合計" block (e.g., highest confidence) if multiple exist
              if secondary_keyword_block is None or (secondary_keyword_block and confidence > secondary_keyword_block["confidence"]):
                 secondary_keyword_block = {"bbox": bbox, "text": text, "confidence": confidence}
                 print(f"DEBUG: Found potential secondary total keyword '{secondary_keyword_block['text']}' at {bbox} with confidence {confidence:.2f}", file=sys.stderr)


    # --- Spatial search near the Primary Keyword ("ご請求金額") ---
    if primary_keyword_block:
        keyword_bbox = primary_keyword_block["bbox"]
        print(f"DEBUG: Searching for amount near primary keyword ('{primary_keyword_block['text']}')...", file=sys.stderr)

        # Define search area relative to the primary keyword block - Tuned for ご請求金額
        # Start searching slightly left of the keyword's right edge, extend far right,
        # and allow some vertical flexibility around the same line.
        search_area_left = keyword_bbox[1][0] - 30 # Start searching slightly left of keyword end
        search_area_right = keyword_bbox[1][0] + 800 # Search up to 800 pixels to the right (large)
        search_area_top = keyword_bbox[0][1] - 30 # Increased vertical buffer upwards
        search_area_bottom = keyword_bbox[2][1] + 50 # Increased vertical buffer downwards

        candidate_amounts = []
        # Look for blocks that contain digits, commas, or dots, optionally with symbols at the start
        # Relaxed the regex slightly to catch variations
        number_content_pattern = re.compile(r'^[¥円半\uffe5\uFF00-\uFFEF\s]*[\d,\.]+$') # Accepts numbers with commas and decimals


        print(f"DEBUG: Search area near primary keyword: Left={search_area_left:.0f}, Right={search_area_right:.0f}, Top={search_area_top:.0f}, Bottom={search_area_bottom:.0f}", file=sys.stderr)

        for (bbox, text, confidence) in ocr_results:
             block_left = bbox[0][0]
             block_right = bbox[1][0]
             block_top = bbox[0][1]
             block_bottom = bbox[2][1]

             # Check spatial overlap with the defined search area
             horizontal_overlap = max(0, min(block_right, search_area_right) - max(block_left, search_area_left))
             vertical_overlap = max(0, min(block_bottom, search_area_bottom) - max(block_top, search_area_top))

             # Consider a block a candidate if it has sufficient horizontal overlap, is vertically within the search area,
             # has reasonable confidence, and matches the number content pattern.
             # Require at least 0.3 confidence for amount candidates
             if horizontal_overlap > (block_right - block_left) * 0.3 and vertical_overlap > 0 and confidence > 0.3 and number_content_pattern.match(text.strip()):
                  candidate_amounts.append({"text": text, "confidence": confidence, "bbox": bbox})
                  print(f"DEBUG:   Found candidate near primary keyword: '{text}' at {bbox} with confidence {confidence:.2f}", file=sys.stderr) # DEBUG

        if candidate_amounts:
             # Sort by confidence and pick the best one near the primary keyword
             candidate_amounts.sort(key=lambda c: c["confidence"], reverse=True)
             total_amount_value = candidate_amounts[0]["text"]
             print(f"DEBUG: Selected amount from primary search: '{total_amount_value}' (Confidence: {candidate_amounts[0]['confidence']:.2f})", file=sys.stderr)


    # --- Spatial search near the Secondary Keyword ("合計") if Primary Search Failed ---
    if total_amount_value is None and secondary_keyword_block:
        keyword_bbox = secondary_keyword_block["bbox"]
        print(f"DEBUG: Primary search failed. Searching for amount near secondary keyword ('{secondary_keyword_block['text']}')...", file=sys.stderr)

        # Define search area relative to the secondary keyword block (Also a relatively large area)
        search_area_left = keyword_bbox[1][0] - 50 # Start slightly left of keyword end
        search_area_right = keyword_bbox[1][0] + 600 # Search up to 600 pixels to the right
        search_area_top = keyword_bbox[0][1] - 30 # Increased vertical buffer upwards
        search_area_bottom = keyword_bbox[2][1] + 50 # Increased vertical buffer downwards


        candidate_amounts = []
        number_content_pattern = re.compile(r'^[¥円\uffe5\uFF00-\uFFEF\s]*[\d,\.]+$')

        # print(f"DEBUG: Search area near secondary keyword: Left={search_area_left:.0f}, Right={search_area_right:.0f}, Top={search_area_top:.0f}, Bottom={search_area_bottom:.0f}", file=sys.stderr) # DEBUG

        for (bbox, text, confidence) in ocr_results:
             block_left = bbox[0][0]
             block_right = bbox[1][0]
             block_top = bbox[0][1]
             block_bottom = bbox[2][1]

             horizontal_overlap = max(0, min(block_right, search_area_right) - max(block_left, search_area_left))
             vertical_overlap = max(0, min(block_bottom, search_area_bottom) - max(block_top, search_area_top))

             if horizontal_overlap > (block_right - block_left) * 0.3 and vertical_overlap > 0 and confidence > 0.1 and number_content_pattern.match(text.strip()):
                  candidate_amounts.append({"text": text, "confidence": confidence, "bbox": bbox})
                  print(f"DEBUG:   Found candidate near secondary keyword: '{text}' at {bbox} with confidence {confidence:.2f}", file=sys.stderr)

        if candidate_amounts:
            candidate_amounts.sort(key=lambda c: c["confidence"], reverse=True)
            total_amount_value = candidate_amounts[0]["text"]
            print(f"DEBUG: Selected amount from secondary search: '{total_amount_value}' (Confidence: {candidate_amounts[0]['confidence']:.2f})", file=sys.stderr)
        # else: print("DEBUG: Spatial search found no amount candidates in the area near '合計'.", file=sys.stderr) # DEBUG

    # else: print("DEBUG: Could not find either total keyword ('ご請求金額' or '合計').", file=sys.stderr) # DEBUG


    # Process the extracted total amount value
    if total_amount_value:
        try:
            # CLEANING: Remove all non-numeric except dot and comma, then remove commas
            cleaned_amount_str = re.sub(r'[^\d.,]', '', total_amount_value).replace(',', '').strip()

            if cleaned_amount_str:
                try:
                    numerical_amount = float(cleaned_amount_str)
                except ValueError:
                    # Try to extract only digits if float conversion fails
                    cleaned_amount_str = re.sub(r'[^\d]', '', cleaned_amount_str)
                    numerical_amount = float(cleaned_amount_str) if cleaned_amount_str else 0

                # Optional: Filter out amounts that are likely too small (heuristic)
                if numerical_amount > 100: # Heuristic threshold (adjust if needed)
                     invoice_data["total_amount"] = "{:,.0f}".format(numerical_amount) # Format as integer with commas
                     print(f"DEBUG: Final Extracted Total Amount (after formatting and filter): {invoice_data['total_amount']}", file=sys.stderr)
                else:
                     print(f"DEBUG: Extracted amount '{total_amount_value}' cleaned to '{cleaned_amount_str}' seems too small ({numerical_amount}). Setting to None.", file=sys.stderr)
                     # invoice_data["total_amount"] remains None
            # else: print(f"DEBUG: Cleaned amount string is empty for: '{total_amount_value}'. Setting to None.", file=sys.stderr) # DEBUG

        except ValueError:
            print(f"DEBUG: Could not convert total amount: '{total_amount_value}' to number after cleaning.", file=sys.stderr)
            # invoice_data["total_amount"] remains None
    # else: print("DEBUG: Total amount value is None after spatial attempt.", file=sys.stderr) # DEBUG


    # --- Bank Transfer Details (using regex on joined text) ---
    bank_details_block_match = re.search(r'振込先\s*(.*?)(?:備考|$)', full_text, re.DOTALL)
    if bank_details_block_match:
        bank_details_block = bank_details_block_match.group(1)
        # print(f"DEBUG: Found bank details block: {bank_details_block.strip()[:200]}...", file=sys.stderr) # DEBUG

        bank_name_match = re.search(r'(りそな銀行|三井住友銀行|三菱UFJ銀行|みずほ銀行|ゆうちょ銀行|.+銀行)', bank_details_block)
        if bank_name_match:
            invoice_data["bank_name"] = bank_name_match.group(1).strip()
            # print(f"DEBUG: Found Bank Name: {invoice_data['bank_name']}", file=sys.stderr) # DEBUG

        branch_name_match = re.search(r'(\S+支店)', bank_details_block)
        if branch_name_match:
            invoice_data["branch_name"] = branch_name_match.group(1).strip()
            # print(f"DEBUG: Found Branch Name: {invoice_data['branch_name']}", file=sys.stderr) # DEBUG

        account_type_match = re.search(r'(普通|当座)', bank_details_block)
        if account_type_match:
            invoice_data["account_type"] = account_type_match.group(1).strip()
            # print(f"DEBUG: Found Account Type: {invoice_data['account_type']}", file=sys.stderr) # DEBUG

        account_number_match = re.search(r'[\s:\-]?(\d{7})[\s:\-.]?', bank_details_block)
        if account_number_match:
            invoice_data["account_number"] = account_number_match.group(1).strip()
            # print(f"DEBUG: Found Account Number: {invoice_data['account_number']}", file=sys.stderr) # DEBUG

        # --- Account Holder Extraction (Refined Regex + Spatial Fallback) ---
        if invoice_data["account_number"]:
            # Attempt refined regex match first
            account_holder_match = re.search(
                re.escape(invoice_data["account_number"]) + r'[\s\-\.．・]*([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\u3400-\u4DBFー・]+)', # Added more separators and CJK Ext A
                bank_details_block
            )
            if account_holder_match:
                invoice_data["account_holder"] = account_holder_match.group(1).strip()
                # print(f"DEBUG: Found Account Holder via Regex: {invoice_data['account_holder']}", file=sys.stderr) # DEBUG
            else:
                 # Fallback to spatial search near account number bbox if regex fails
                 account_number_bbox = None
                 # Find the bbox for the detected account number text
                 for (bbox, text, confidence) in ocr_results:
                     # More robust check for account number text within a block
                     if invoice_data["account_number"] in text.replace(' ','') and confidence > 0.5: # Check after removing potential spaces in the number
                          account_number_bbox = bbox
                          break

                 if account_number_bbox:
                     # Define spatial search area for the account holder name near the account number
                     # Assume name is usually to the right and slightly below or on the same line
                     name_search_left = account_number_bbox[1][0] - 10 # Start searching slightly before the right edge
                     name_search_right = account_number_bbox[1][0] + 200 # Search to the right
                     name_search_top = account_number_bbox[0][1] - 5 # Slight buffer up
                     name_search_bottom = account_number_bbox[2][1] + 20 # Buffer down

                     candidate_names = []
                     # Look for text blocks containing Japanese characters
                     japanese_char_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\u3400-\u4DBF]+')

                     for (bbox, text, confidence) in ocr_results:
                          block_left = bbox[0][0]
                          block_right = bbox[1][0]
                          block_top = bbox[0][1]
                          block_bottom = bbox[2][1]

                          # Check spatial overlap
                          horizontal_overlap = max(0, min(block_right, name_search_right) - max(block_left, name_search_left))
                          vertical_overlap = max(0, min(block_bottom, name_search_bottom) - max(block_top, name_search_top))


                          # Consider candidates that are mostly within the area and contain Japanese characters
                          if horizontal_overlap > (block_right - block_left) * 0.5 and vertical_overlap > 0 and confidence > 0.5 and japanese_char_pattern.search(text):
                               candidate_names.append({"text": text, "confidence": confidence, "bbox": bbox})

                     if candidate_names:
                          # Sort by confidence, then by proximity to the right of the account number bbox
                          candidate_names.sort(key=lambda c: (c["confidence"], abs(c["bbox"][0][0] - account_number_bbox[1][0])), reverse=True) # Sort by confidence descending, then distance ascending

                          best_candidate_name = candidate_names[0]
                          invoice_data["account_holder"] = best_candidate_name["text"].strip()
                          # print(f"DEBUG: Found Account Holder via Spatial Search: {invoice_data['account_holder']} (Confidence: {best_candidate_name['confidence']:.2f})", file=sys.stderr) # DEBUG
                 # else: print("DEBUG: Spatial search found no convincing account holder name candidates.", file=sys.stderr) # DEBUG
             # else: print("DEBUG: Could not find account number bbox for spatial name search.", file=sys.stderr) # DEBUG
        # else: print("DEBUG: Account number not found, skipping account holder extraction.", file=sys.stderr) # DEBUG


    # --- Line Item Extraction (Refined Spatial Analysis) ---
    line_items = []

    header_keywords_map = {
        "DESCRIPTION": ["品目名", "内容"],
        "UNIT PRICE": ["単価", "価格"],
        "QUANTITY": ["数量", "数"],
        "UNIT": ["単位"],
        "AMOUNT": ["金額", "合計"] # '合計' might also appear in total, need to be careful
    }
    header_keywords_list = [kw.lower() for keywords in header_keywords_map.values() for kw in keywords]


    # --- Step 1: Identify the Main Table Header Row ---
    potential_header_rows = []
    y_threshold_header_row = 15

    # Use the already sorted_all_results
    sorted_all_results = sorted(ocr_results, key=lambda r: r[0][0][1]) # Ensure this is used

    current_header_row_blocks = []
    for (bbox, text, confidence) in sorted_all_results: # Iterate over sorted_all_results
        is_header_keyword_candidate = False
        normalized_text = text.strip().lower()
        for keywords in header_keywords_map.values():
             if any(k.lower() in normalized_text for k in keywords):
                 is_header_keyword_candidate = True
                 break

        if is_header_keyword_candidate and confidence > 0.6:
            if not current_header_row_blocks:
                current_header_row_blocks.append((bbox, text, confidence))
            else:
                current_y_mean = (bbox[0][1] + bbox[2][1]) / 2
                # Corrected variable name here
                row_y_mean = sum([(r[0][0][1] + r[0][2][1]) / 2 for r in current_header_row_blocks]) / len(current_header_row_blocks)


                if abs(current_y_mean - row_y_mean) < y_threshold_header_row:
                     current_header_row_blocks.append((bbox, text, confidence))
                else:
                     potential_header_rows.append(current_header_row_blocks)
                     current_header_row_blocks = [(bbox, text, confidence)]

    if current_header_row_blocks:
         potential_header_rows.append(current_header_row_blocks)

    main_header_row = None
    max_header_keywords_found = 0
    main_header_row_bottom_y = -1
    main_header_row_bboxes = {}

    for row_blocks in potential_header_rows:
        found_keywords_in_row = set()
        current_row_bottom_y = -1
        current_row_bboxes = {}

        for (bbox, text, confidence) in row_blocks:
             normalized_text = text.strip().lower()
             current_row_bottom_y = max(current_row_bottom_y, bbox[2][1])

             for col_name, keywords in header_keywords_map.items():
                  if any(k.lower() in normalized_text for k in keywords):
                      found_keywords_in_row.add(col_name)
                      if col_name not in current_row_bboxes:
                          current_row_bboxes[col_name] = {"bbox": bbox, "confidence": confidence}

        if len(found_keywords_in_row) > max_header_keywords_found:
            max_header_keywords_found = len(found_keywords_in_row)
            main_header_row = row_blocks
            main_header_row_bottom_y = current_row_bottom_y
            main_header_row_bboxes = current_row_bboxes

    required_core_headers = ["DESCRIPTION", "AMOUNT"]
    required_core_headers_found = all(h in main_header_row_bboxes for h in required_core_headers)

    if not main_header_row or max_header_keywords_found < 2 or not required_core_headers_found:
        invoice_data["line_items"] = []


    # --- Step 2: Determine Column Anchors ---
    header_column_anchors = {}
    if main_header_row_bboxes:
        sorted_main_header_bboxes = sorted(main_header_row_bboxes.items(), key=lambda item: item[1]["bbox"][0][0])

        for col_name, data in sorted_main_header_bboxes:
            bbox = data["bbox"]
            block_center_x = (bbox[0][0] + bbox[1][0] + bbox[2][0] + bbox[3][0]) / 4
            header_column_anchors[col_name] = block_center_x

        desc_x = header_column_anchors.get("DESCRIPTION")
        amount_x = header_column_anchors.get("AMOUNT")

        if desc_x is not None and amount_x is not None:
             if "UNIT PRICE" not in header_column_anchors:
                  header_column_anchors["UNIT PRICE"] = desc_x + (amount_x - desc_x) * 0.4
             if "QUANTITY" not in header_column_anchors:
                  unit_price_x = header_column_anchors.get("UNIT PRICE", desc_x + (amount_x - desc_x) * 0.4)
                  header_column_anchors["QUANTITY"] = unit_price_x + (amount_x - unit_price_x) * 0.4
             if "UNIT" not in header_column_anchors:
                  quantity_x = header_column_anchors.get("QUANTITY", desc_x + (amount_x - desc_x) * 0.6)
                  header_column_anchors["UNIT"] = quantity_x + (amount_x - quantity_x) * 0.5
        # else: print("Could not define all core column anchors.", file=sys.stderr) # Optional error print


    # --- Step 3: Filter Text Below Main Header Row ---
    text_blocks_below_header = []
    if main_header_row_bottom_y != -1:
        buffer_below_header = 5
        text_blocks_below_header = [(bbox, text, confidence) for (bbox, text, confidence) in ocr_results
                                     if bbox[0][1] > (main_header_row_bottom_y + buffer_below_header)
                                     and confidence > 0.1]

        if not text_blocks_below_header:
            pass # Line items will be empty


    # --- Step 4: Group Text Blocks into Item Rows ---
    rows = []
    if text_blocks_below_header:
        text_blocks_below_header.sort(key=lambda r: r[0][0][1])

        current_row = []
        y_threshold_row = 10

        for (bbox, text, confidence) in text_blocks_below_header:
            if not current_row:
                current_row.append((bbox, text, confidence))
            else:
                current_y_mean = (bbox[0][1] + bbox[2][1]) / 2
                row_y_mean = sum([(r[0][0][1] + r[0][2][1]) / 2 for r in current_row]) / len(current_row)


                if abs(current_y_mean - row_y_mean) < y_threshold_row:
                    current_row.append((bbox, text, confidence))
                else:
                    rows.append(current_row)
                    current_row = [(bbox, text, confidence)]

        if current_row:
             rows.append(current_row)


    # --- Step 5: Process each row and Assign Text to Columns ---

    col_name_to_output_key = {
        "DESCRIPTION": "description",
        "UNIT PRICE": "unit_price",
        "QUANTITY": "quantity",
        "UNIT": "unit",
        "AMOUNT": "amount"
    }

    if header_column_anchors:
        horizontal_assignment_tolerance = 100

        for i, row in enumerate(rows):
            row.sort(key=lambda r: r[0][0][0])

            item = {
                "description": "",
                "unit_price": "",
                "quantity": "",
                "unit": "",
                "amount": ""
            }

            assigned_text_by_column = {key: [] for key in col_name_to_output_key.values()}

            for (bbox, text, confidence) in row:
                block_center_x = (bbox[0][0] + bbox[1][0] + bbox[2][0] + bbox[3][0]) / 4

                assigned_col_name = None
                min_distance = float('inf')

                for col_name, anchor_x in header_column_anchors.items():
                     distance = abs(block_center_x - anchor_x)
                     if distance < min_distance:
                         min_distance = distance
                         assigned_col_name = col_name

                if assigned_col_name and min_distance < horizontal_assignment_tolerance:
                     output_key = col_name_to_output_key.get(assigned_col_name)
                     if output_key:
                         assigned_text_by_column[output_key].append(text.strip())


            item["description"] = " ".join(assigned_text_by_column["description"]).strip()
            item["unit_price"] = " ".join(assigned_text_by_column["unit_price"]).replace(',', '').strip()
            item["quantity"] = " ".join(assigned_text_by_column["quantity"]).replace(',', '').strip()
            item["unit"] = " ".join(assigned_text_by_column["unit"]).strip()
            item["amount"] = " ".join(assigned_text_by_column["amount"]).replace(',', '').strip()

            if item["unit_price"]:
                try:
                    item["unit_price"] = "{:,.0f}".format(float(item["unit_price"]))
                except ValueError:
                     pass

            if item["quantity"]:
                pass

            if item["amount"]:
                try:
                    item["amount"] = "{:,.0f}".format(float(item["amount"]))
                except ValueError:
                     pass

            footer_keywords_lower = [kw.lower() for kw in ["小計", "消費税", "合計", "振込先", "備考"]]
            is_footer_row = item["description"].strip().lower() in footer_keywords_lower or \
                            item["amount"].strip().lower() in footer_keywords_lower or \
                            any(kw in item["description"].strip().lower() for kw in footer_keywords_lower)

            # Heuristic to filter out rows that are likely part of a footer (e.g., subtotal, tax, bank info)
            # This is critical to prevent misinterpreting footer lines as actual line items.
            is_valid_item = False
            if item["description"] or item["amount"] or item["unit_price"] or item["quantity"]: # Check if row has any content
                try:
                    # Check if amount is a plausible number if present
                    if item["amount"]:
                         float(item["amount"].replace(',', ''))
                         is_valid_item = True
                    elif item["unit_price"] and item["quantity"]:
                        # If no amount, but price and quantity exist, it's likely an item
                        float(item["unit_price"].replace(',', ''))
                        # Optionally check quantity is numeric too if needed
                        is_valid_item = True
                    elif item["description"]:
                         # If only description, only consider valid if no other fields are populated (might be a header/category line within items)
                         if not item["amount"] and not item["unit_price"] and not item["quantity"] and not item["unit"]:
                              pass # Filter out description-only lines for now
                         else:
                              # Description plus some other field without amount/price/qty might also be a valid item
                              is_valid_item = True # More lenient if description is present
                    else:
                         # Row has content but none of the above criteria met (e.g., just a unit or quantity standalone)
                         pass # Filter out likely noise

                except ValueError:
                    is_valid_item = False # If conversion fails, it's not a valid number

            if is_valid_item and not is_footer_row: # Ensure we don't add footer as line items and it's a valid item candidate
                line_items.append(item)


        invoice_data["line_items"] = line_items


    return invoice_data


def run_extraction(file_path):
    """
    Main function to run the OCR and data extraction.
    """
    start_time = time.time()
    
    ocr_results = process_document(file_path)
    if ocr_results is None:
        return {
            "status": "error",
            "message": "Failed to process document through OCR.",
            "file_path": file_path
        }

    invoice_data = extract_invoice_data(ocr_results)

    end_time = time.time()

    return {
        "status": "success",
        "message": "Document processed successfully.",
        "file_path": file_path,
        "invoice_data": invoice_data,
        "timestamp": int(end_time)
    }

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({
            "status": "error",
            "message": "Usage: python script.py <path_to_invoice_file>"
        }))
        sys.exit(1)

    input_file_path = sys.argv[1]
    result = run_extraction(input_file_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))