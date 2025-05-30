# ocr-test-project/scripts/process_invoice.py

import sys
import json
import os
import easyocr
from PIL import Image
from pdf2image import convert_from_path
import numpy as np # Make sure this is present and correct

def process_document(file_path):
    reader = easyocr.Reader(['en', 'ja']) # Assuming you still want both English and Japanese

    base_name = os.path.basename(file_path)
    file_extension = os.path.splitext(file_path)[1].lower()

    images = []
    if file_extension == '.pdf':
        try:
            images = convert_from_path(file_path, dpi=300)
            print(f"Successfully converted PDF to {len(images)} images.", file=sys.stderr)
        except Exception as e:
            print(f"Error converting PDF: {e}", file=sys.stderr)
            return None
    elif file_extension in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        try:
            images.append(Image.open(file_path))
            print(f"Loaded image file: {file_path}", file=sys.stderr)
        except Exception as e:
            print(f"Error loading image: {e}", file=sys.stderr)
            return None
    else:
        print(f"Unsupported file type: {file_extension}", file=sys.stderr)
        return None

    if not images:
        print("No images to process after conversion/loading.", file=sys.stderr)
        return None

    all_extracted_text = []
    for i, image in enumerate(images):
        try:
            # --- REPLACE THE ENTIRE PREVIOUS 'CHANGE IS HERE' BLOCK WITH THIS ---
            # Convert PIL Image to grayscale ('L') first, then to NumPy array
            # This is generally robust for OCR as it simplifies the image data.
            image_for_ocr = image.convert('L')
            numpy_image = np.array(image_for_ocr)

            # Perform OCR on the NumPy array
            results = reader.readtext(numpy_image, detail=0)
            # --- END OF REPLACEMENT ---

            page_text = " ".join(results)
            all_extracted_text.append(f"--- Page {i+1} ---\n{page_text}")
            print(f"Processed page {i+1} with {len(results)} text blocks.", file=sys.stderr)
        except Exception as e:
            print(f"Error during OCR on page {i+1}: {e}", file=sys.stderr)
            all_extracted_text.append(f"--- Page {i+1} (OCR Error) ---\nError: {e}")

    return "\n".join(all_extracted_text)

if __name__ == "__main__":
    # ... (rest of your script, which should remain unchanged) ...
    if len(sys.argv) < 2:
        print("Error: No input file path provided.", file=sys.stderr)
        sys.exit(1)

    input_file_path = sys.argv[1]
    print(f"Attempting to process: {input_file_path}", file=sys.stderr)

    if not os.path.exists(input_file_path):
        print(f"Error: Input file does not exist at {input_file_path}", file=sys.stderr)
        sys.exit(1)

    extracted_text = process_document(input_file_path)

    if extracted_text is not None:
        result = {
            "status": "success",
            "message": "Document processed successfully.",
            "file_path": input_file_path,
            "extracted_text": extracted_text,
            "timestamp": os.path.getmtime(input_file_path)
        }
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print("\nPython script finished successfully.", file=sys.stderr)
    else:
        print("Document processing failed.", file=sys.stderr)
        result = {
            "status": "error",
            "message": "Failed to process document."
        }
        json.dump(result, sys.stdout, indent=2)
        sys.exit(1)