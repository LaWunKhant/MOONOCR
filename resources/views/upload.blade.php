<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Upload Invoice for OCR</title>
    {{-- Add some basic styling or link to your CSS --}}
    <style>
        body { font-family: sans-serif; margin: 20px; }
        .container { max-width: 800px; margin: auto; padding: 20px; border: 1px solid #ccc; border-radius: 8px; }
        .alert { padding: 15px; margin-bottom: 20px; border: 1px solid transparent; border-radius: 4px; }
        .alert-success { color: #155724; background-color: #d4edda; border-color: #c3e6cb; }
        .alert-danger { color: #721c24; background-color: #f8d7da; border-color: #f5c6cb; }
        .ocr-data { margin-top: 20px; padding: 15px; border: 1px solid #eee; border-radius: 4px; background-color: #f9f9f9; }
        .ocr-data h3 { margin-top: 0; }
        .ocr-data pre { background-color: #e9e9e9; padding: 10px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Upload Japanese Invoice for OCR</h1>

        {{-- Display Success Messages --}}
        @if (session('success'))
            <div class="alert alert-success">
                {{ session('success') }}
            </div>
        @endif

        {{-- Display Error Messages --}}
        @if (session('error'))
            <div class="alert alert-danger">
                {{ session('error') }}
                @if (session('raw_output'))
                    <p><strong>Raw Output:</strong></p>
                    <pre>{{ session('raw_output') }}</pre>
                @endif
                @if (session('error_output'))
                    <p><strong>Error Output (stderr):</strong></p>
                    <pre>{{ session('error_output') }}</pre>
                @endif
            </div>
        @endif

        {{-- File Upload Form --}}
        <form action="{{ route('ocr.process') }}" method="POST" enctype="multipart/form-data">
            @csrf {{-- CSRF Protection --}}
            <div>
                <label for="document">Choose Document (PDF, JPG, PNG):</label><br>
                <input type="file" id="document" name="document" accept=".pdf,.jpg,.jpeg,.png" required>
            </div>
            @error('document')
                <div class="alert alert-danger" style="margin-top: 5px;">{{ $message }}</div>
            @enderror
            <br>
            <button type="submit">Process Document</button>
        </form>

        {{-- Display Parsed OCR Data --}}
        @if (session('ocr_parsed_data'))
            <div class="ocr-data">
                <h3>Extracted Invoice Information:</h3>
                @php $data = session('ocr_parsed_data'); @endphp

                <p><strong>Invoice Number:</strong> {{ $data['invoice_number'] ?? 'N/A' }}</p>
                <p><strong>Invoice Date:</strong> {{ $data['invoice_date'] ?? 'N/A' }}</p>
                <p><strong>Due Date:</strong> {{ $data['due_date'] ?? 'N/A' }}</p>
                <p><strong>Vendor Name:</strong> {{ $data['vendor_name'] ?? 'N/A' }}</p>
                <p><strong>Total Amount:</strong> {{ $data['total_amount'] ?? 'N/A' }}</p>
                <p><strong>Account Holder:</strong> {{ $data['account_holder'] ?? 'N/A' }}</p>

                @if (!empty($data['line_items']))
                    <h4>Line Items:</h4>
                    <table>
                        <thead>
                            <tr>
                                <th>Description</th>
                                <th>Unit Price</th>
                                <th>Quantity</th>
                                <th>Unit</th>
                                <th>Amount</th>
                            </tr>
                        </thead>
                        <tbody>
                            @foreach ($data['line_items'] as $item)
                                <tr>
                                    <td>{{ $item['description'] ?? 'N/A' }}</td>
                                    <td>{{ $item['unit_price'] ?? 'N/A' }}</td>
                                    <td>{{ $item['quantity'] ?? 'N/A' }}</td>
                                    <td>{{ $item['unit'] ?? 'N/A' }}</td>
                                    <td>{{ $item['amount'] ?? 'N/A' }}</td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                @else
                    <p>No line items extracted.</p>
                @endif
                <hr>
                <h4>Raw JSON Data:</h4>
                <pre>{{ json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) }}</pre>
            </div>
        @endif
    </div>
</body>
</html>