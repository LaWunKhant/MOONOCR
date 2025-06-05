import os
import json
import re
import time
import warnings
from pathlib import Path
from pdf2image import convert_from_path # Ensure Poppler is installed and in PATH
from PIL import Image
import torch
import sys
import tempfile

# Suppress warnings from libraries like urllib3
warnings.filterwarnings("ignore", category=UserWarning, module='urllib3')

# Check if EasyOCR is available
try:
    import easyocr
    EASY_AVAILABLE = True
except ImportError:
    EASY_AVAILABLE = False
    # This error will be handled in __main__ by printing JSON and exiting

# Global EasyOCR reader instance
READER = None
# Global variable to store the path of the temporary image if one is created by prepare_image
_TEMP_IMAGE_PATH_FOR_CLEANUP = None

def initialize_ocr():
    """Initializes the EasyOCR reader, trying to use GPU if available."""
    global READER
    if READER is None and EASY_AVAILABLE:
        use_gpu = torch.cuda.is_available()
        READER = easyocr.Reader(['ja', 'en'], gpu=use_gpu, verbose=False)

def prepare_image(input_file_path_str):
    """
    Converts a PDF to a temporary PNG image, or returns the path if the input is already an image.
    Crucial for EasyOCR to process PDFs. Temporary PNGs are created in the system's temp directory.
    """
    global _TEMP_IMAGE_PATH_FOR_CLEANUP
    _TEMP_IMAGE_PATH_FOR_CLEANUP = None # Reset for each call

    input_file_p_obj = Path(input_file_path_str)
    if not input_file_p_obj.exists():
        raise FileNotFoundError(f"Input file not found: {input_file_p_obj}")

    if input_file_p_obj.suffix.lower() == '.pdf':
        try:
            images = convert_from_path(input_file_p_obj, dpi=150, first_page=1, last_page=1)
        except Exception as e:
            # Detailed error message for Poppler issues
            poppler_msg = "Ensure Poppler is installed and its 'bin' directory is in your system's PATH."
            raise RuntimeError(f"Failed to convert PDF '{input_file_p_obj.name}'. {poppler_msg} Original error: {e}")

        if images:
            img = images[0].convert('RGB')
            # Create a temporary file for the image
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                temp_image_path = tmp_file.name
            _TEMP_IMAGE_PATH_FOR_CLEANUP = temp_image_path # Store for cleanup
            img.save(temp_image_path, 'PNG', optimize=True)
            return temp_image_path # Return path to the new temp image
        else:
            raise ValueError(f"No pages found in PDF: {input_file_p_obj.name}")
    else:
        # If not a PDF, use the original path directly
        return str(input_file_p_obj)

def extract_with_easyocr(image_path_to_ocr):
    """Performs OCR extraction on the given image path using the initialized EasyOCR reader."""
    if not EASY_AVAILABLE or READER is None:
        # This case should ideally be caught before calling, e.g., in initialize_ocr or main
        raise RuntimeError("EasyOCR is not available or not initialized.")

    results = READER.readtext(
        image_path_to_ocr, detail=1, paragraph=False,
        width_ths=0.7, height_ths=0.7, batch_size=1
    )
    return [
        {'text': text, 'confidence': confidence, 'bbox': bbox}
        for bbox, text, confidence in results if confidence > 0.3
    ]

def clean_amount(amount_str):
    if not amount_str:
        return None
    cleaned = re.sub(r'[半#¥￥\s]', '', str(amount_str))
    cleaned = re.sub(r'[^\d,.]', '', cleaned)
    if re.match(r'^\d{7,}$', cleaned.replace(',', '')) and cleaned.startswith('1') and ',' in cleaned:
        cleaned = cleaned[1:]
    return cleaned if cleaned else None

def parse_japanese_invoice(extracted_text):
    def parse_line_items_logic():
        line_items = []
        skip_terms_general = [
            '請求書番号', '請求日', 'お支払期限', '振込先', '小計', '消費税', '合計',
            'INVOICE', 'TEL:', '登録番号', '東京都', '御中', '様', '担当者',
            '備考', 'りそな銀行', '秋葉原支店', '普通', '下記のとおり', 'ご請求金額',
            '年', '月', '日', '消費税対象', '口座', '銀行', '振込手数料',
            '振込先銀行', '支店', '口座番号', '口座名義', '税抜金額', '税込み',
            '商品コード', '伝票番号', '番号'
        ]
        column_headers = ['品目名', '商品名', 'サービス内容', '明細', '単価', '数量', '金額', '単位']
        relevant_items = []
        for item in extracted_text:
            text = item['text'].strip()
            if len(text) < 1 or text in ['-', '/', '\\', '|', '=', '_', '.', ':', ';', '(', ')', '#', '半', '¥', '￥']:
                continue
            if any(term in text for term in skip_terms_general):
                continue
            if text in column_headers:
                continue
            if re.match(r'^\d{4}[/-年]\d{1,2}[/-月]?\d{1,2}日?$', text) or re.match(r'^\d{1,2}:\d{2}$', text):
                continue
            relevant_items.append(item)

        relevant_items.sort(key=lambda x: x['bbox'][0][1])
        rows = []
        current_row_y_center = -1
        row_vertical_tolerance = 15
        for item in relevant_items:
            item_y_center = (item['bbox'][0][1] + item['bbox'][2][1]) / 2
            if not rows or abs(item_y_center - current_row_y_center) > row_vertical_tolerance:
                rows.append([item])
                current_row_y_center = item_y_center
            else:
                rows[-1].append(item)
                all_y_centers = [(i['bbox'][0][1] + i['bbox'][2][1]) / 2 for i in rows[-1]]
                current_row_y_center = sum(all_y_centers) / len(all_y_centers)

        for row_items in rows:
            row_items.sort(key=lambda x: x['bbox'][0][0])
            description = []
            numbers_in_row = []
            unit = None
            for item in row_items:
                text = item['text'].strip()
                if re.match(r'^[0-9,]+(\.[0-9]+)?$', text):
                    numbers_in_row.append({'text': text, 'bbox': item['bbox']})
                elif text in ['パック', 'kg', 'g', '個', '本', '枚', 'セット', '袋', '円', '式', '件', '個口']:
                    unit = text
                else:
                    if not re.match(r'^[0-9\s#¥￥]+$', text) and text not in ['INVOICE', 'TEL']:
                        description.append(text)
            current_description = ' '.join(description).strip()
            if not current_description and not numbers_in_row:
                continue
            if not current_description and len(numbers_in_row) < 2:
                 continue
            line_item = {
                "description": current_description,
                "unit_price": None,
                "quantity": None,
                "unit": unit,
                "amount": None
            }
            cleaned_numbers = [clean_amount(n['text']) for n in numbers_in_row if clean_amount(n['text'])]
            numeric_values = []
            for num_str in cleaned_numbers:
                try:
                    numeric_values.append(float(num_str.replace(',', '')))
                except ValueError:
                    pass
            if len(cleaned_numbers) >= 3:
                line_item['unit_price'] = cleaned_numbers[0]
                line_item['quantity'] = cleaned_numbers[1]
                line_item['amount'] = cleaned_numbers[2]
            elif len(cleaned_numbers) == 2:
                if numeric_values and len(numeric_values) == 2 and numeric_values[0] < numeric_values[1] and numeric_values[0] < 1000:
                    line_item['quantity'] = cleaned_numbers[0]
                    line_item['amount'] = cleaned_numbers[1]
                else:
                    line_item['unit_price'] = cleaned_numbers[0]
                    line_item['amount'] = cleaned_numbers[1]
            elif len(cleaned_numbers) == 1:
                line_item['amount'] = cleaned_numbers[0]
            try:
                qty = float(line_item['quantity'].replace(',', '')) if line_item['quantity'] else None
                u_price = float(line_item['unit_price'].replace(',', '')) if line_item['unit_price'] else None
                amt = float(line_item['amount'].replace(',', '')) if line_item['amount'] else None
                if qty and u_price and amt is None:
                    line_item['amount'] = f"{qty * u_price:,.0f}"
                elif qty and amt and u_price is None and qty > 0:
                    unit_price_calc = amt / qty
                    line_item['unit_price'] = f"{int(unit_price_calc):,}" if unit_price_calc.is_integer() else f"{unit_price_calc:,.2f}"
                elif u_price and amt and qty is None and u_price > 0:
                    quantity_calc = amt / u_price
                    line_item['quantity'] = f"{int(quantity_calc):,}" if quantity_calc.is_integer() else f"{quantity_calc:,.2f}"
            except (ValueError, ZeroDivisionError, TypeError): # Added TypeError for None.replace
                pass
            if line_item['description'] and (line_item['amount'] or line_item['unit_price'] or line_item['quantity']):
                line_items.append(line_item)
        return line_items

    output = {
        "invoice_number": None, "invoice_date": None, "due_date": None,
        "vendor_name": None, "total_amount": None, "account_holder": None,
        "line_items": []
    }
    all_text = ' '.join(item['text'] for item in extracted_text)
    patterns = {
        'invoice_number': [r'(\d{8}-\d+)', r'(?:請求書|INVOICE)\s*No\.?[:：]?\s*([A-Za-z0-9\-]+)',
                           r'請求\s*書\s*番号[:：]?\s*([A-Za-z0-9\-]+)'],
        'invoice_date': [r'(?:請求日|発行日)[:：]?\s*(\d{4}[/-年]\d{1,2}[/-月]?\d{1,2}日?)', r'(\d{4}/\d{1,2}/\d{1,2})'],
        'due_date': [r'(?:お?支払期限|支払期限|支払期日)[:：]?\s*(\d{4}[/-年]\d{1,2}[/-月]?\d{1,2}日?)',
                     r'(?:お?支払期限|支払期限|支払期日)\s+(\d{4}年\d{1,2}月\d{1,2}日)'],
        'vendor_name': [r'([^\s]+株式会社)', r'([^\s]+合同会社)', r'([^\s]+会社)', r'([^\s]+Corp\.?)',
                        r'([^\s]+Ltd\.?)', r'([^\s]+Co\.?,? ?Ltd\.?)', r'([^\s]+サービス)'],
        'total_amount': [
            r'(?:ご請求金額)[:：]?\s*[¥￥#]?\s*([\d,]+(?:\.\d{1,2})?)',
            r'(?:合計|総計)[:：]?\s*[¥￥#]?\s*([\d,]+(?:\.\d{1,2})?)', # Added 総計
            r'[¥￥#]?\s*(?:合計|ご請求金額|総額)?\s*([\d,]+(?:.\d{1,2})?)',
            r'小計\s*[\d,]+(?:.\d{1,2})?\s*消費税\s*[\d,]+(?:.\d{1,2})?\s*合計\s*([\d,]+(?:.\d{1,2})?)'
        ],
        'account_holder': [
            r'(?:普通\s*\d{6,8}\s*)([^\s]+)', r'口座名義[:：]?\s*([^\s]+)', r'名義[:：]?\s*([^\s]+)'
        ]
    }
    for field, pattern_list in patterns.items():
        if output[field] is None:
            for pattern in pattern_list:
                match = re.search(pattern, all_text)
                if match:
                    value = match.group(match.lastindex or 1).strip()
                    if field == 'total_amount': value = clean_amount(value)
                    output[field] = value
                    break
    if not output['invoice_date'] or not output['due_date']:
        date_matches = re.findall(r'(\d{4}[/-年]\d{1,2}[/-月]?\d{1,2}日?)', all_text)
        if len(date_matches) >= 1 and not output['invoice_date']: output['invoice_date'] = date_matches[0]
        if len(date_matches) >= 2 and not output['due_date']: output['due_date'] = date_matches[1]
    try:
        output['line_items'] = parse_line_items_logic()
    except Exception: # pylint: disable=broad-except
        # In case of unexpected error in line item parsing, keep it empty but don't crash
        output['line_items'] = []
    return output

# def validate_result(result): # Kept for potential direct debugging, but output goes to STDOUT.
#     """Prints a validation summary of the extracted invoice data."""
#     print("\n=== VALIDATION (for debugging) ===")
#     if not result:
#         print("❌ No data extracted.")
#         return
#     required = ['invoice_number', 'invoice_date', 'vendor_name']
#     missing = [f for f in required if not result.get(f)]
#     if missing: print(f"⚠️ Missing critical fields: {', '.join(missing)}")
#     else: print("✅ All required fields present.")
#     print(f"✅ Found {len(result.get('line_items', []))} line item(s)")
#     print("=== END VALIDATION ===")

def process_japanese_invoice_fast(input_file_path_for_processing):
    global _TEMP_IMAGE_PATH_FOR_CLEANUP
    # start_time = time.time() # For debugging duration

    try:
        initialize_ocr()
        if not EASY_AVAILABLE or READER is None: # Double check after initialization attempt
            raise RuntimeError("EasyOCR could not be initialized or is not available.")

        image_for_ocr_path = prepare_image(input_file_path_for_processing)
        extracted_data = extract_with_easyocr(image_for_ocr_path)

        if not extracted_data:
            raise ValueError("OCR extraction failed or returned no text.")

        result = parse_japanese_invoice(extracted_data)
        if not result: # Should always return a dict, but as a safeguard
            raise ValueError("Invoice parsing failed to produce a result structure.")

        # Primary output for Laravel: JSON to STDOUT
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result # Return for potential direct use if not called as script

    except Exception as e: # pylint: disable=broad-except
        error_output = {
            "error": str(e),
            "type": type(e).__name__
        }
        print(json.dumps(error_output, indent=2, ensure_ascii=False))
        return None
    finally:
        if _TEMP_IMAGE_PATH_FOR_CLEANUP and Path(_TEMP_IMAGE_PATH_FOR_CLEANUP).exists():
            try:
                os.remove(_TEMP_IMAGE_PATH_FOR_CLEANUP)
                # print(f"Cleaned up temp image: {_TEMP_IMAGE_PATH_FOR_CLEANUP}", file=sys.stderr) # Debug to stderr
            except OSError:
                # print(f"Error cleaning up temp file: {_TEMP_IMAGE_PATH_FOR_CLEANUP}", file=sys.stderr) # Debug to stderr
                pass
        # print(f"🕒 Total processing time: {time.time() - start_time:.2f} seconds", file=sys.stderr) # Debug to stderr

if __name__ == "__main__":
    if not EASY_AVAILABLE:
        print(json.dumps({"error": "EasyOCR is NOT installed. Please install with: pip install easyocr"}, ensure_ascii=False))
        sys.exit(1)

    current_script_dir = Path(__file__).parent
    actual_input_file = None

    if len(sys.argv) > 1:
        cmd_line_path = Path(sys.argv[1])
        # If path from cmd is relative, assume it's relative to current working directory
        if not cmd_line_path.is_absolute():
            cmd_line_path = Path.cwd() / cmd_line_path
        
        if not cmd_line_path.exists():
            print(json.dumps({"error": f"Input file provided via command line not found: {cmd_line_path}"}, ensure_ascii=False))
            sys.exit(1)
        actual_input_file = str(cmd_line_path.resolve())
    else:
        # Fallback to default file in 'photo' folder (for easy local testing)
        photo_dir = current_script_dir / 'photo'
        # Look for common image/pdf types
        possible_extensions = ['*.pdf', '*.png', '*.jpg', '*.jpeg']
        found_files = []
        for ext in possible_extensions:
            found_files.extend(list(photo_dir.glob(ext)))
        
        if found_files:
            actual_input_file = str(found_files[0].resolve())
            # print(f"⚠️ No input file provided via command line. Using default: {actual_input_file}", file=sys.stderr)
        else:
            err_msg = {
                "error": "No input file provided and no default file found.",
                "details": f"Provide path as argument or place file in '{photo_dir}'."
            }
            print(json.dumps(err_msg, ensure_ascii=False))
            sys.exit(1)

    # Call the main processing function
    final_result = process_japanese_invoice_fast(actual_input_file)

    # Exit code for Laravel Process component
    if final_result is None:
        sys.exit(1)  # Indicate failure
    else:
        # Optional: Save JSON to a file for local debugging if needed
        # debug_output_path = current_script_dir / "japanese_invoice_output_debug.json"
        # with open(debug_output_path, "w", encoding="utf-8") as f:
        #     json.dump(final_result, f, indent=2, ensure_ascii=False)
        # print(f"Debug JSON saved to {debug_output_path}", file=sys.stderr)
        sys.exit(0)  # Indicate success