import os
import json
import re
import time
import warnings
from pathlib import Path
from pdf2image import convert_from_path
from PIL import Image
import torch

# Suppress warnings from libraries like urllib3
warnings.filterwarnings("ignore", category=UserWarning, module='urllib3')

# Check if EasyOCR is available
try:
    import easyocr
    EASY_AVAILABLE = True
except ImportError:
    EASY_AVAILABLE = False
    print("❌ EasyOCR not installed. Please install with: pip install easyocr")

# Define paths for input and temporary image files
script_dir = Path(__file__).parent
input_file = script_dir / 'photo' / 'invoice.pdf'
image_path = script_dir / 'converted_image.png'
input_file_str = str(input_file)
image_path_str = str(image_path)

# Global EasyOCR reader instance
READER = None

def initialize_ocr():
    """Initializes the EasyOCR reader, trying to use GPU if available."""
    global READER
    if READER is None and EASY_AVAILABLE:
        # print("🚀 Initializing EasyOCR with GPU support...") # Removed print
        use_gpu = torch.cuda.is_available()
        # print(f"GPU available: {use_gpu}") # Removed print
        READER = easyocr.Reader(['ja', 'en'], gpu=use_gpu, verbose=False)
        # print("✅ EasyOCR initialized") # Removed print

def prepare_image(input_file_path):
    """
    Converts a PDF to a PNG image, or returns the path if the input is already an image.
    This function is crucial for EasyOCR to process PDFs.
    """
    input_file_path = Path(input_file_path)
    if not input_file_path.exists():
        raise FileNotFoundError(f"File not found: {input_file_path}")

    if input_file_path.suffix.lower() == '.pdf':
        # print(f"Converting PDF to image: {input_file_path}") # Removed print
        try:
            # Changed DPI to 180 for potential speed gain
            images = convert_from_path(input_file_path, dpi=180, first_page=1, last_page=1)
        except Exception as e:
            raise RuntimeError(f"Failed to convert PDF. Ensure Poppler is installed and its 'bin' directory is in your system's PATH. Error: {e}")

        if images:
            img = images[0].convert('RGB')
            img.save(image_path_str, 'PNG', optimize=True)
            # print(f"Image saved at: {image_path_str}") # Removed print
            return image_path_str
        else:
            raise ValueError("No pages found in PDF")
    else:
        return str(input_file_path)

def extract_with_easyocr(image_path_to_ocr):
    """Performs OCR extraction on the given image path using the initialized EasyOCR reader."""
    if not EASY_AVAILABLE or READER is None:
        # print("EasyOCR is not available or not initialized.") # Removed print
        return None

    # print(f"🔍 Running OCR extraction on: {image_path_to_ocr}") # Removed print
    results = READER.readtext(
        image_path_to_ocr, detail=1, paragraph=False,
        width_ths=0.7, height_ths=0.7, batch_size=1
    )

    return [
        {'text': text, 'confidence': confidence, 'bbox': bbox}
        for bbox, text, confidence in results if confidence > 0.5 # Kept confidence at 0.5 for accuracy
    ]

def clean_amount(amount_str):
    """
    Cleans an amount string by removing currency symbols (¥, ￥, #), '半', and
    any non-numeric characters except for commas and decimal points.
    """
    if not amount_str:
        return None
    cleaned = re.sub(r'[半#¥￥\s]', '', str(amount_str))
    cleaned = re.sub(r'[^\d,.]', '', cleaned)
    return cleaned if cleaned else None

def parse_japanese_invoice(extracted_text):
    """
    Parses key invoice details and dynamically extracts line items.
    """

    def parse_line_items_logic():
        """
        Extracts individual line items by grouping text segments that are vertically aligned
        and then assigning them to description, quantity, unit_price, and amount columns.
        """
        line_items = []

        # Terms to ignore as they are typically headers or non-item data
        skip_terms_general = [
            '請求書番号', '請求日', 'お支払期限', '振込先', '小計', '消費税', '合計',
            'INVOICE', 'TEL:', '登録番号', '東京都', '御中', '様', '担当者',
            '備考', 'りそな銀行', '秋葉原支店', '普通', '下記のとおり', 'ご請求金額',
            '年', '月', '日', '消費税対象', '口座', '銀行', '振込手数料',
            '振込先銀行', '支店', '口座番号', '口座名義', '税抜金額', '税込み',
            '商品コード', '伝票番号', '番号'
        ]

        # Explicit column headers that might appear in the line item area
        column_headers = ['品目名', '商品名', 'サービス内容', '明細', '単価', '数量', '金額', '単位']

        # Filter out obvious non-item texts and headers
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
                if numeric_values and numeric_values[0] < numeric_values[1] and numeric_values[0] < 1000:
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
            except (ValueError, ZeroDivisionError):
                pass

            if line_item['description'] and (line_item['amount'] or line_item['unit_price'] or line_item['quantity']):
                line_items.append(line_item)

        return line_items

    output = {
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "vendor_name": None,
        "total_amount": None,
        "line_items": []
    }

    all_text = ' '.join(item['text'] for item in extracted_text)
    # print("--- OCR Combined Text (for primary fields) ---\n" + all_text + "\n-------------------------") # Removed print

    patterns = {
        'invoice_number': [r'(\d{8}-\d+)', r'(?:請求書|INVOICE)\s*No\.?[:：]?\s*([A-Za-z0-9\-]+)', r'請求\s*書\s*番号[:：]?\s*([A-Za-z0-9\-]+)'],
        'invoice_date': [r'(?:請求日|発行日)[:：]?\s*(\d{4}[/-年]\d{1,2}[/-月]?\d{1,2}日?)', r'(\d{4}/\d{1,2}/\d{1,2})'],
        'due_date': [r'(?:お?支払期限|支払期限|支払期日)[:：]?\s*(\d{4}[/-年]\d{1,2}[/-月]?\d{1,2}日?)', r'(?:お?支払期限|支払期限|支払期日)\s+(\d{4}年\d{1,2}月\d{1,2}日)'],
        'vendor_name': [r'([^\s]+株式会社)', r'([^\s]+合同会社)', r'([^\s]+会社)', r'([^\s]+Corp\.?)', r'([^\s]+Ltd\.?)', r'([^\s]+Co\.?,? ?Ltd\.?)', r'([^\s]+サービス)'],
        'total_amount': [r'(?:合計|ご請求金額|総額)[:：]?\s*[¥￥半#]?\s*([\d,]+(?:.\d{1,2})?)', r'[¥￥#]?\s*(?:合計|ご請求金額|総額)?\s*([\d,]+(?:.\d{1,2})?)', r'小計\s*[\d,]+(?:.\d{1,2})?\s*消費税\s*[\d,]+(?:.\d{1,2})?\s*合計\s*([\d,]+(?:.\d{1,2})?)']
    }

    for field, pattern_list in patterns.items():
        if output[field] is None:
            for pattern in pattern_list:
                match = re.search(pattern, all_text)
                if match:
                    value = match.group(match.lastindex or 1).strip()
                    if field == 'total_amount':
                        value = clean_amount(value)
                    output[field] = value
                    # print(f"✅ Found {field}: {value}") # Removed print
                    break

    if not output['invoice_date'] or not output['due_date']:
        date_matches = re.findall(r'(\d{4}[/-年]\d{1,2}[/-月]?\d{1,2}日?)', all_text)
        if len(date_matches) >= 1 and not output['invoice_date']:
            output['invoice_date'] = date_matches[0]
        if len(date_matches) >= 2 and not output['due_date']:
            output['due_date'] = date_matches[1]

    try:
        output['line_items'] = parse_line_items_logic()
    except Exception as e:
        print(f"⚠️ Failed to parse line items: {e}")
        output['line_items'] = []

    return output

def validate_result(result):
    """Prints a validation summary of the extracted invoice data."""
    print("\n=== VALIDATION ===")
    if not result:
        print("❌ No data extracted.")
        return

    required = ['invoice_number', 'invoice_date', 'vendor_name']
    missing = [f for f in required if not result.get(f)]

    if missing:
        print(f"⚠️ Missing critical fields: {', '.join(missing)}")
    else:
        print("✅ All required fields present.")

    print(f"✅ Found {len(result.get('line_items', []))} line item(s)")
    print("=== END VALIDATION ===")

def process_japanese_invoice_fast(input_file_path):
    """
    Main workflow function:
    1. Initializes EasyOCR.
    2. Prepares the input file (converts PDF to image if necessary).
    3. Performs OCR to extract text.
    4. Parses the extracted text into structured invoice data.
    5. Saves the result to a JSON file.
    6. Conducts a validation check and cleans up temporary files.
    """
    start_time = time.time()
    initialize_ocr()

    try:
        image_for_ocr = prepare_image(input_file_path)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"❌ Error during image preparation: {e}")
        return None

    extracted_data = extract_with_easyocr(image_for_ocr)

    if not extracted_data:
        print("❌ OCR extraction failed or returned no text.")
        if Path(image_path_str).exists():
            os.remove(image_path_str)
            print(f"Cleaned up: {image_path_str}")
        return None

    result = parse_japanese_invoice(extracted_data)
    if not result:
        print("❌ Invoice parsing failed.")
        if Path(image_path_str).exists():
            os.remove(image_path_str)
            print(f"Cleaned up: {image_path_str}")
        return None

    print("\n=== FINAL RESULT ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    output_json_filename = "japanese_invoice_output.json"
    with open(output_json_filename, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # print(f"\n✅ JSON saved to {output_json_filename}") # Removed print
    validate_result(result)
    print(f"\n🕒 Total processing time: {time.time() - start_time:.2f} seconds") # Removed print

    if Path(image_path_str).exists():
        os.remove(image_path_str)
        # print(f"Cleaned up: {image_path_str}") # Removed print

    return result

if __name__ == "__main__":
    print("Japanese Invoice OCR Processor (Fast Version)")
    print("==================================================")
    print("✅ EasyOCR is ready to go!" if EASY_AVAILABLE else "❌ EasyOCR is NOT installed. Please install it to use this script.")

    if not input_file.exists():
        print(f"\n🚨 Error: The input file '{input_file}' was not found.")
        print("Please make sure you have 'invoice.pdf' inside a 'photo' directory,")
        print("relative to where you are running this script (e.g., 'your_script_folder/photo/invoice.pdf').")
        print("Alternatively, update the 'input_file' variable in the script to point to your invoice PDF.")
    else:
        processed_result = process_japanese_invoice_fast(input_file_str)