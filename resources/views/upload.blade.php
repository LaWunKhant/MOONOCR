<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document OCR Uploader</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen">
    <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 class="text-2xl font-bold mb-6 text-center">Upload Document for OCR</h1>

        @if (session('success'))
            <div class="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative mb-4" role="alert">
                <strong class="font-bold">Success!</strong>
                <span class="block sm:inline">{{ session('success') }}</span>
                @if (session('ocr_data'))
                    <div class="mt-2 text-sm text-gray-800 bg-green-50 p-2 rounded">
                        <h3 class="font-semibold">Extracted Text:</h3>
                        <pre class="whitespace-pre-wrap font-mono text-xs">{{ session('ocr_data') }}</pre>
                    </div>
                @endif
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

        <form action="{{ route('ocr.process') }}" method="POST" enctype="multipart/form-data" class="space-y-4">
            @csrf
            <div>
                <label for="document" class="block text-sm font-medium text-gray-700">Select Document (PDF, JPG, PNG, GIF)</label>
                <input type="file" name="document" id="document" class="mt-1 block w-full text-sm text-gray-500
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-full file:border-0
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
    </div>
</body>
</html>