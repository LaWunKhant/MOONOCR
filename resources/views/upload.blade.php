<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document OCR Uploader</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        /* Optional: Add some custom styles for better readability/layout if needed */
        .grid-cols-2 {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .grid-cols-3 {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .grid-cols-4 {
            grid-template-columns: repeat(4, minmax(0, 1fr));
        }
    </style>
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen">
    <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-2xl"> {{-- Increased max-width for more fields --}}
        <h1 class="text-2xl font-bold mb-6 text-center">Upload Document for OCR</h1>

        @if (session('success'))
            <div class="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative mb-4" role="alert">
                <strong class="font-bold">Success!</strong>
                <span class="block sm:inline">{{ session('success') }}</span>
                {{-- Keep this commented out for now as per user request --}}
                {{-- @if (session('ocr_parsed_data.extracted_text'))
                    <div class="mt-2 text-sm text-gray-800 bg-green-50 p-2 rounded">
                        <h3 class="font-semibold">Extracted Text (Raw):</h3>
                        <pre class="whitespace-pre-wrap font-mono text-xs">{{ session('ocr_parsed_data.extracted_text') }}</pre>
                    </div>
                @endif --}}
            </div>
        @endif

        @if (session('error'))
            <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4" role="alert">
                <strong class="font-bold">Error!</strong>
                <span class="block sm:inline">{{ session('error') }}</span>
                @if (session('raw_output'))
                    <div class="mt-2 text-sm text-gray-800 bg-red-50 p-2 rounded">
                        <h3 class="font-semibold">Raw Python Output:</h3>
                        <pre class="whitespace-pre-wrap font-mono text-xs">{{ session('raw_output') }}</pre>
                        <h3 class="font-semibold mt-2">Python Error Output (stderr):</h3>
                        <pre class="whitespace-pre-wrap font-mono text-xs">{{ session('error_output') }}</pre>
                    </div>
                @endif
            </div>
        @endif

        @if ($errors->any())
            <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4">
                <ul class="list-disc list-inside">
                    @foreach ($errors->all() as $error)
                        <li>{{ $error }}</li>
                    @endforeach
                </ul>
            </div>
        @endif

        {{-- Keep this commented out for now as per user request --}}
        {{-- @if (session('ocr_parsed_data'))
            <div class="bg-blue-100 border border-blue-400 text-blue-700 px-4 py-3 rounded relative mb-4">
                <h3 class="font-bold mb-2">OCR Extracted Data (Raw JSON):</h3>
                <pre class="whitespace-pre-wrap text-sm">{{ json_encode(session('ocr_parsed_data'), JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) }}</pre>
            </div>
        @endif --}}

        <form action="{{ route('ocr.process') }}" method="POST" enctype="multipart/form-data" class="space-y-4 mb-8 p-6 bg-white shadow-md rounded-lg">
            @csrf
            <div>
                <label for="document" class="block text-sm font-medium text-gray-700">Select Document (PDF, JPG, PNG, GIF)</label>
                <input type="file" name="document" id="document" class="mt-1 block w-full text-sm text-gray-500
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-md file:border-0
                    file:text-sm file:font-semibold
                    file:bg-indigo-50 file:text-indigo-700
                    hover:file:bg-indigo-100"/>
            </div>
            <div>
                <button type="submit" class="w-full bg-indigo-600 text-white py-2 px-4 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2">
                    Upload and Process
                </button>
            </div>
        </form>

        {{-- Display OCR parsed data in a form if available --}}
        @if (session('ocr_parsed_data.invoice_data')) {{-- Only show if invoice_data exists --}}
            <h2 class="text-xl font-bold mb-4 text-center">Invoice Details (Pre-filled by OCR)</h2>
            <form action="/save-invoice-details" method="POST" class="space-y-4 p-6 bg-white shadow-md rounded-lg">
                @csrf
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label for="invoice_number" class="block text-sm font-medium text-gray-700">Invoice Number:</label>
                        <input type="text" name="invoice_number" id="invoice_number"
                               value="{{ session('ocr_parsed_data.invoice_data.invoice_number') ?? '' }}"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                    <div>
                        <label for="invoice_date" class="block text-sm font-medium text-gray-700">Invoice Date:</label>
                        @php
                            $invoiceDate = session('ocr_parsed_data.invoice_data.invoice_date');
                            // Convert to YYYY-MM-DD for input type="date"
                            if ($invoiceDate) {
                                $invoiceDate = str_replace(['/', '年', '月', '日'], ['-', '-', '-', ''], $invoiceDate);
                                try {
                                    $carbonDate = \Carbon\Carbon::parse($invoiceDate);
                                    $invoiceDate = $carbonDate->format('Y-m-d');
                                } catch (Exception $e) {
                                    $invoiceDate = ''; // Fallback if parsing fails
                                }
                            }
                        @endphp
                        <input type="date" name="invoice_date" id="invoice_date"
                               value="{{ $invoiceDate ?? '' }}"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                    <div class="col-span-1 md:col-span-2"> {{-- Full width for vendor name --}}
                        <label for="vendor_name" class="block text-sm font-medium text-gray-700">Vendor Name:</label>
                        <input type="text" name="vendor_name" id="vendor_name"
                               value="{{ session('ocr_parsed_data.invoice_data.vendor_name') ?? '' }}"
                               placeholder="e.g., テスト太郎会社"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                    <div>
                        <label for="total_amount" class="block text-sm font-medium text-gray-700">Total Amount (¥):</label>
                        {{-- total_amount is now formatted by Python script as string with commas --}}
                        <input type="text"
                               name="total_amount"
                               id="total_amount"
                               value="{{ session('ocr_parsed_data.invoice_data.total_amount') ?? '' }}"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                    <div>
                        <label for="due_date" class="block text-sm font-medium text-gray-700">Due Date:</label> {{-- Changed ID and Name --}}
                        @php
                            $dueDate = session('ocr_parsed_data.invoice_data.due_date'); // Changed session key
                            // Convert YYYY年MM月DD日 to YYYY-MM-DD for input type="date"
                            if ($dueDate) {
                                $dueDate = str_replace(['年', '月', '日'], ['-', '-', ''], $dueDate);
                                $dueDate = rtrim($dueDate, '-'); // Remove trailing hyphen if any
                                try {
                                    $carbonDate = \Carbon\Carbon::parse($dueDate);
                                    $dueDate = $carbonDate->format('Y-m-d');
                                } catch (Exception $e) {
                                    $dueDate = ''; // Fallback if parsing fails
                                }
                            }
                        @endphp
                        <input type="date" name="due_date" id="due_date" {{-- Changed ID and Name --}}
                               value="{{ $dueDate ?? '' }}"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                </div>

                <h3 class="text-lg font-bold mt-6 mb-2">Bank Details</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label for="bank_name" class="block text-sm font-medium text-gray-700">Bank Name:</label>
                        <input type="text" name="bank_name" id="bank_name"
                               value="{{ session('ocr_parsed_data.invoice_data.bank_name') ?? '' }}"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                    <div>
                        <label for="branch_name" class="block text-sm font-medium text-gray-700">Branch Name:</label>
                        <input type="text" name="branch_name" id="branch_name"
                               value="{{ session('ocr_parsed_data.invoice_data.branch_name') ?? '' }}"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                    <div>
                        <label for="account_type" class="block text-sm font-medium text-gray-700">Account Type:</label>
                        <input type="text" name="account_type" id="account_type"
                               value="{{ session('ocr_parsed_data.invoice_data.account_type') ?? '' }}"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                    <div>
                        <label for="account_number" class="block text-sm font-medium text-gray-700">Account Number:</label>
                        <input type="text" name="account_number" id="account_number"
                               value="{{ session('ocr_parsed_data.invoice_data.account_number') ?? '' }}"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                     <div class="col-span-1 md:col-span-2"> {{-- Full width for account holder --}}
                        <label for="account_holder" class="block text-sm font-medium text-gray-700">Account Holder Name:</label>
                        <input type="text" name="account_holder" id="account_holder"
                               value="{{ session('ocr_parsed_data.invoice_data.account_holder') ?? '' }}"
                               class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                    </div>
                </div>

                <h3 class="text-lg font-bold mt-6 mb-2">Line Items</h3>
                @if (!empty(session('ocr_parsed_data.invoice_data.line_items')))
                    <div class="overflow-x-auto">
                        <table class="min-w-full bg-white border border-gray-200 rounded-md shadow-sm">
                            <thead>
                                <tr>
                                    <th class="px-4 py-2 border-b-2 border-gray-200 bg-gray-50 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Description</th>
                                    <th class="px-4 py-2 border-b-2 border-gray-200 bg-gray-50 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Unit Price</th>
                                    <th class="px-4 py-2 border-b-2 border-gray-200 bg-gray-50 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Quantity</th>
                                    <th class="px-4 py-2 border-b-2 border-gray-200 bg-gray-50 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Unit</th>
                                    <th class="px-4 py-2 border-b-2 border-gray-200 bg-gray-50 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Amount</th>
                                </tr>
                            </thead>
                            <tbody>
                                @foreach (session('ocr_parsed_data.invoice_data.line_items') as $item)
                                    <tr class="hover:bg-gray-50">
                                        <td class="px-4 py-2 whitespace-normal text-sm text-gray-900">{{ $item['description'] ?? '' }}</td>
                                        <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-900">{{ $item['unit_price'] ?? '' }}</td>
                                        <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-900">{{ $item['quantity'] ?? '' }}</td>
                                        <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-900">{{ $item['unit'] ?? '' }}</td>
                                        <td class="px-4 py-2 whitespace-nowrap text-sm text-gray-900">{{ $item['amount'] ?? '' }}</td>
                                    </tr>
                                @endforeach
                            </tbody>
                        </table>
                    </div>
                @else
                    <p class="text-sm text-gray-600 mt-2">No line items extracted.</p>
                @endif

                {{-- --- REMOVED LINE ITEMS TABLE AS PER USER REQUEST --- --}}

                <button type="submit" class="w-full bg-green-600 text-white py-2 px-4 rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 mt-6">
                    Save Invoice Details
                </button>


            </form>
        @endif
    </div>
</body>
</html>