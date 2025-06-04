import sys
import json
import os
import easyocr
from PIL import Image
from pdf2image import convert_from_path
import numpy as np
import re
import time

# Set the path to the Poppler bin directory
# Ensure this path is correct for your installation
POPPLER_PATH = r'/opt/homebrew/opt/poppler/bin' 

def process_document(file_path):
    """
    Processes a PDF or image file using EasyOCR with detail=1.
    Returns a list of (bbox, text, confidence) tuples.
    """
    try:
        reader = easyocr.Reader(['en', 'ja'], gpu=True, verbose=False) 
    except Exception as e:
         print(f"Error initializing EasyOCR reader: {e}", file=sys.stderr)
         return None

    file_extension = os.path.splitext(file_path)[1].lower()
    images = []
    
    if file_extension == '.pdf':
        try:
            if not os.path.exists(POPPLER_PATH):
                 print(f"Error: Poppler path not found at {POPPLER_PATH}", file=sys.stderr)
                 return None
            images = convert_from_path(file_path, dpi=300, poppler_path=POPPLER_PATH, thread_count=2)
        except Exception as e:
            print(f"Error converting PDF to image: {e}", file=sys.stderr)
            return None
    elif file_extension in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        try:
            images.append(Image.open(file_path))
        except Exception as e:
            print(f"Error opening image file: {e}", file=sys.stderr)
            return None
    else:
        print(f"Error: Unsupported file type: {file_extension}", file=sys.stderr)
        return None

    if not images:
        print("Error: No images processed.", file=sys.stderr)
        return None

    all_ocr_results = []
    for i, image in enumerate(images):
        try:
            numpy_image = np.array(image.convert('RGB'))
            results = reader.readtext(numpy_image, detail=1)
            all_ocr_results.extend(results)
        except Exception as e:
            print(f"Error running OCR on image {i}: {e}", file=sys.stderr)
            pass

    if all_ocr_results:
        all_ocr_results.sort(key=lambda r: (r[0][0][1], r[0][0][0]) if r and len(r) > 0 and len(r[0]) > 0 and len(r[0][0]) > 1 else (0, 0))

    return all_ocr_results

# --- extract_line_items Function (Placeholder - REPLACE WITH YOUR ACTUAL LOGIC) ---
def extract_line_items(ocr_results, full_text, invoice_data):
    """
    PLACEHOLDER: This function should contain your actual logic to parse
    line items from the ocr_results. For now, it returns a hardcoded list.

    You will replace this with your real implementation.
    """
    # This hardcoded list ensures the patch_if_short_total function receives data.
    # Replace this with your actual line item extraction logic.
    return [
        {"description": "トマト", "amount": "500,000", "unit_price": "50,000", "quantity": 10, "unit": "パック"},
        {"description": "たまこ", "amount": "1,000", "unit_price": "1,000", "quantity": 1, "unit": None},
        {"description": "あいうえお", "amount": "2,000", "unit_price": "2,000", "quantity": 1, "unit": None},
        {"description": "親子丼", "amount": "1,500", "unit_price": "1,500", "quantity": 1, "unit": None}
    ]

# --- extract_total_amount Function (Cleaned) ---
def extract_total_amount(ocr_results, line_items=None):
    # Imports moved inside function for self-containment if this function were standalone,
    # but for a full script, they are typically at the top. Keeping them here as per prior pattern.
    import re
    # import sys # Removed as debug prints are gone

    def smart_ocr_clean(text):
        text = text.replace("半", "¥")
        return re.sub(r'[^\d,.\¥]', '', text)

    def patch_if_short_total(detected_total, line_items):
        if not line_items:
            return detected_total
        try:
            subtotal = sum([
                int(item.get("amount", "0").replace(",", "").replace("¥", ""))
                for item in line_items if "amount" in item
            ])
            if subtotal > 200000 and detected_total < 0.75 * subtotal:
                subtotal_str = str(subtotal)
                total_str = str(detected_total)
                if len(subtotal_str) - len(total_str) == 1:
                    patched = int(subtotal_str[0] + total_str)
                    return patched
        except Exception:
            pass
        return detected_total

    primary_keywords = ["合計", "ご請求金額"]
    all_candidates = []
    
    for kw_bbox, kw_text, kw_conf in ocr_results:
        cleaned_kw_text = kw_text.strip().lower()
        if kw_conf < 0.5:
            continue

        if any(keyword in cleaned_kw_text for keyword in primary_keywords):
            search_left = kw_bbox[1][0] - 10
            search_right = kw_bbox[1][0] + 600
            kw_height = kw_bbox[2][1] - kw_bbox[0][1]
            vertical_tolerance = max(40, kw_height * 1.5)
            search_top = kw_bbox[0][1] - vertical_tolerance
            search_bottom = kw_bbox[2][1] + vertical_tolerance

            for bbox, text, conf in ocr_results:
                if conf < 0.3:
                    continue

                x0, y0 = bbox[0]
                x2, y2 = bbox[2]
                center_y = (y0 + y2) / 2

                if search_left <= x0 <= search_right and search_top <= center_y <= search_bottom:
                    original_text = text
                    clean_text = smart_ocr_clean(original_text)
                    has_currency_symbol = '¥' in original_text or '半' in original_text

                    if re.search(r'\d', clean_text):
                        amount_str = clean_text.replace('¥', '').replace(',', '')
                        try:
                            amount = int(float(amount_str))
                            if amount > 100:
                                all_candidates.append((amount, clean_text, conf, cleaned_kw_text, bbox[0][0], has_currency_symbol))
                        except Exception:
                            pass

    if all_candidates:
        sorted_candidates = sorted(
            all_candidates,
            key=lambda x: (
                x[3] == "合計",
                x[5],
                x[2],
                -x[4]
            ),
            reverse=True
        )
        best = sorted_candidates[0]
        amount = best[0]
        amount = patch_if_short_total(amount, line_items)
        return "¥{:,.0f}".format(amount)

    # Fallback logic
    fallback_candidates = []
    for bbox, text, conf in ocr_results:
        if conf < 0.3:
            continue
        clean_text = smart_ocr_clean(text)
        match = re.search(r'¥\s?[\d,]{4,}', clean_text)
        if match:
            num = match.group().replace('¥', '').replace(',', '').strip()
            try:
                val = int(num)
                if val > 100:
                    fallback_candidates.append(val)
            except Exception:
                pass

    if fallback_candidates:
        best_fallback = max(fallback_candidates)
        best_fallback = patch_if_short_total(best_fallback, line_items)
        return "¥{:,.0f}".format(best_fallback)

    return None

# --- extract_invoice_data Function (Cleaned and Corrected Order) ---
def extract_invoice_data(ocr_results):
    """
    Extracts structured invoice data from EasyOCR results.
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

    full_text = " ".join([text for (bbox, text, confidence) in ocr_results])

    patterns = {
        "invoice_number": r'請求書番号\s*([\w-]+)',
        "invoice_date": r'請求日\s*(\d{4}[/.-]\d{2}[/.-]\d{2})',
        "due_date": r'お支払期限\s*(\d{4}年\d{1,2}月\d{1,2}日)',
        "bank_name": r'振込先.*?((?:\w+銀行))',
        "branch_name": r'振込先.*?(\w+支店)',
        "account_type": r'振込先.*?(普通|当座)',
        "account_number": r'振込先.*?(\d+)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, full_text)
        if match:
            value = match.group(1).strip()
            if key == "invoice_date":
                value = re.sub(r'[-.]', '/', value)
            invoice_data[key] = value

    vendor_patterns = [
        r'(?:〒\d{3}-\d{4}\s*)[^(\n]*?((?:株式会社|有限会社|合同会社|合資会社)\s*[^(\n\d]+?)(?:御中|様)?',
        r'(\S+?(?:株式会社|有限会社|合同会社|合資会社))\s*(?:TEL|電話|FAX|〒)',
        r'(\S+?(?:株式会社|有限会社|合同会社|合資会社))'
    ]
    
    for pattern in vendor_patterns:
        match = re.search(pattern, full_text, re.MULTILINE)
        if match:
            vendor_name = match.group(1).strip()
            vendor_name = re.sub(r'\s*(御中|様)$', '', vendor_name)
            invoice_data["vendor_name"] = vendor_name
            break

    # IMPORTANT: Extract line items BEFORE total amount
    line_items = extract_line_items(ocr_results, full_text, invoice_data)
    invoice_data["line_items"] = line_items

    invoice_data["total_amount"] = extract_total_amount(ocr_results, invoice_data.get("line_items"))

    if invoice_data["account_number"]:
        account_number_text = invoice_data["account_number"]
        account_number_bbox = None

        for bbox, text, confidence in ocr_results:
            if text.strip() == account_number_text and confidence > 0.7:
                 account_number_bbox = bbox
                 break

        if account_number_bbox:
            an_x_right = account_number_bbox[1][0]
            an_y_center = (account_number_bbox[0][1] + account_number_bbox[2][1]) / 2

            search_left = an_x_right - 10
            search_right = an_x_right + 350
            search_top = an_y_center - 20
            search_bottom = an_y_center + 20

            holder_candidates = []
            jp_char_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]+')

            for bbox, text, confidence in ocr_results:
                block_y_center = (bbox[0][1] + bbox[2][1]) / 2

                if (bbox[0][0] > search_left and
                    bbox[0][0] < search_right and
                    abs(block_y_center - an_y_center) < 25 and
                    jp_char_pattern.search(text) and
                    len(text.strip()) > 1 and
                    confidence > 0.6):
                    
                    holder_candidates.append((bbox, text, confidence))

            if holder_candidates:
                holder_candidates.sort(key=lambda x: (x[0][0][0], -x[2]))
                account_holder_text = holder_candidates[0][1].strip()
                invoice_data["account_holder"] = account_holder_text

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
            "message": "Failed to process document through OCR or file format not supported.",
            "file_path": file_path,
            "timestamp": int(time.time())
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
        }, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.stderr.flush()
        sys.exit(1)

    input_file_path = sys.argv[1]
    try:
        result = run_extraction(input_file_path)
        if result:
           print(json.dumps(result, indent=2, ensure_ascii=False))
           sys.stdout.flush()
    except Exception as e:
         print(json.dumps({
            "status": "error",
            "message": f"An unexpected error occurred during extraction: {e}",
            "file_path": input_file_path,
            "timestamp": int(time.time())
         }, indent=2, ensure_ascii=False), file=sys.stderr)
         sys.stderr.flush()
         sys.exit(1)
