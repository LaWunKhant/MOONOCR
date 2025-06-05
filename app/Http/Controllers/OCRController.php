<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Storage;
use Symfony\Component\Process\Exception\ProcessFailedException;
use Symfony\Component\Process\Process;

class OCRController extends Controller
{
    public function showUploadForm()
    {
        return view('upload');
    }

    public function processDocument(Request $request)
    {
        $request->validate([
            'document' => 'required|file|mimes:pdf,jpeg,png,jpg|max:10240', // Max 10MB, removed gif as less common for invoices
        ]);

        $file = $request->file('document');
        // Store with a unique name to avoid conflicts and simplify
        $filePath = $file->store('uploads', 'public'); // Stores in storage/app/public/uploads with a unique name
        // $originalFileName = $file->getClientOriginalName(); // If you need it for display or records

        $absoluteFilePath = Storage::disk('public')->path($filePath); // Correct way to get path from public disk
        $pythonScriptPath = base_path('scripts/process_invoice.py'); // Assuming your script is named process_invoice.py

        // --- Python Interpreter Path: CRITICAL for DEPLOYMENT ---
        // Option 1: Generic (if python3 is in PATH for the web server user)
        // $pythonExecutable = 'python3';
        // Option 2: From .env (Recommended for flexibility)
        $pythonExecutable = env('OCR_PYTHON_EXECUTABLE', 'python3');
        // Option 3: Your local specific path (ONLY for local dev, update for server)
        // $pythonExecutable = env('OCR_PYTHON_EXECUTABLE', '/Users/cipc-002/easyocr-env/bin/python3');
        // FOR THIS EXAMPLE, let's assume a generic 'python3' or your specific path if testing locally.
        // Ensure the selected Python environment has all dependencies (easyocr, torch, pdf2image, Pillow, Poppler)

        Log::info('Attempting to run Python OCR script:', [
            'python_executable' => $pythonExecutable, // This will now log the full path
            'script_path' => $pythonScriptPath,
            'input_file' => $absoluteFilePath,
        ]);

        $command = [$pythonExecutable, $pythonScriptPath, $absoluteFilePath];

        $process = new Process($command);
        $process->setTimeout(360); // 6 minutes timeout. Adjust as needed. 3600 (1hr) is very long for a sync request.

        $popplerBinPath = '/opt/homebrew/bin';
        $currentProcessEnv = $process->getEnv(); // Get env vars set for THIS process instance (might be null initially)
        $systemPath = getenv('PATH'); // Get PATH from the PHP process's environment

        $basePath = '';
        if (! empty($currentProcessEnv['PATH'])) {
            $basePath = $currentProcessEnv['PATH'];
        } elseif ($systemPath !== false) {
            $basePath = $systemPath;
        }

        $newPath = $popplerBinPath.(empty($basePath) ? '' : PATH_SEPARATOR.$basePath);
        $process->setEnv(array_merge($currentProcessEnv ?: [], ['PATH' => $newPath]));
        Log::info('Process environment PATH set to:', ['path' => $newPath]);

        $outputData = null;
        $errorData = null;
        $pythonStdOut = '';
        $pythonStdErr = '';

        try {
            $process->mustRun(); // Throws ProcessFailedException if the process exits with a non-zero status

            $pythonStdOut = $process->getOutput();
            $pythonStdErr = $process->getErrorOutput(); // Capture stderr even on success for warnings

            Log::info('Python Script STDOUT:', ['output' => $pythonStdOut]);
            if (! empty($pythonStdErr)) {
                Log::warning('Python Script STDERR (on success):', ['stderr' => $pythonStdErr]);
            }

            $outputData = json_decode($pythonStdOut, true);

            if (json_last_error() !== JSON_ERROR_NONE) {
                // Python script succeeded (exit 0) but STDOUT was not valid JSON
                Log::error('Python script output was not valid JSON.', ['raw_stdout' => $pythonStdOut]);
                throw new \RuntimeException('OCR service returned an invalid format.');
            }

            // Check if the successful output from Python is actually an error message it generated
            if (isset($outputData['error'])) {
                Log::error('Python script reported an internal error:', ['error_payload' => $outputData]);
                throw new \RuntimeException('OCR processing error: '.$outputData['error']);
            }

            // Heuristic check for valid data (e.g., presence of a key expected in successful OCR)
            if (! isset($outputData['invoice_number']) && ! isset($outputData['line_items'])) { // Adjust key check as needed
                Log::warning('Parsed JSON from Python does not seem to contain expected invoice data.', ['parsed_json' => $outputData]);
                // Depending on strictness, you might throw an error here or proceed cautiously
                // For now, let's assume if no 'error' key, it's some form of success.
            }

            // If we reach here, processing is considered successful
            Storage::disk('public')->delete($filePath); // Clean up uploaded file

            return redirect()->back()
                ->with('success', 'Document processed successfully!')
                ->with('ocr_parsed_data', $outputData);

        } catch (ProcessFailedException $exception) {
            // Process exited with a non-zero status code
            $process = $exception->getProcess();
            $pythonStdOut = $process->getOutput(); // Python might have printed to stdout before erroring
            $pythonStdErr = $process->getErrorOutput(); // This is the primary error output

            Log::error('Python script process failed (ProcessFailedException):', [
                'command' => $process->getCommandLine(),
                'exit_code' => $process->getExitCode(),
                'stdout' => $pythonStdOut,
                'stderr' => $pythonStdErr,
            ]);

            // Try to parse stderr for a JSON error from Python, otherwise use raw stderr
            $errorMessage = 'Failed to process document. OCR script error.';
            if (! empty($pythonStdErr)) {
                $errorJson = json_decode($pythonStdErr, true);
                if (json_last_error() === JSON_ERROR_NONE && isset($errorJson['error'])) {
                    $errorMessage = 'OCR Error: '.$errorJson['error'];
                } else {
                    $errorMessage .= ' Details: '.substr($pythonStdErr, 0, 250); // Show a snippet
                }
            } elseif (! empty($pythonStdOut)) { // Check stdout if stderr is empty
                $errorJson = json_decode($pythonStdOut, true);
                if (json_last_error() === JSON_ERROR_NONE && isset($errorJson['error'])) {
                    $errorMessage = 'OCR Error: '.$errorJson['error'];
                }
            }

            Storage::disk('public')->delete($filePath);

            return redirect()->back()->with('error', $errorMessage)
                ->with('raw_output', $pythonStdOut) // For debugging in view
                ->with('error_output', $pythonStdErr); // For debugging in view

        } catch (\RuntimeException $e) { // Catch our custom runtime exceptions
            Log::error('OCRController RuntimeException:', ['message' => $e->getMessage()]);
            Storage::disk('public')->delete($filePath);

            return redirect()->back()->with('error', $e->getMessage());

        } catch (\Exception $e) { // Catch all other general exceptions
            Log::error('General error in OCRController:', [
                'message' => $e->getMessage(),
                'file' => $e->getFile(),
                'line' => $e->getLine(),
                'trace' => $e->getTraceAsString(),
            ]);
            Storage::disk('public')->delete($filePath);

            return redirect()->back()->with('error', 'An unexpected server error occurred during OCR processing.');
        }
    }
}
