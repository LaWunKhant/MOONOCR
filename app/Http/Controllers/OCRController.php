<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Storage;
use Symfony\Component\Process\Exception\ProcessFailedException;
use Symfony\Component\Process\Process; // For file handling

class OCRController extends Controller
{
    public function showUploadForm()
    {
        return view('upload'); // We'll create this Blade view next
    }

    public function processDocument(Request $request)
    {
        $request->validate([
            'document' => 'required|file|mimes:pdf,jpeg,png,jpg,gif|max:10240', // Max 10MB
        ]);

        $file = $request->file('document');
        $originalFileName = $file->getClientOriginalName();
        $filePath = $file->storeAs('public/uploads', $originalFileName); // Store in storage/app/public/uploads

        // Get the absolute path to the stored file
        $absoluteFilePath = Storage::path($filePath);
        $pythonScriptPath = base_path('scripts/process_invoice.py');

        Log::info('Attempting to run Python script:', [
            'script_path' => $pythonScriptPath,
            'input_file' => $absoluteFilePath,
        ]);

        // Use 'python3' or 'python' based on your system's setup
        $command = ['/Users/cipc-002/easyocr-env/bin/python3', $pythonScriptPath, $absoluteFilePath];

        $process = new Process($command);
        $process->setTimeout(3600); // Set a generous timeout (e.g., 1 hour)

        try {
            $process->run();

            if (! $process->isSuccessful()) {
                throw new ProcessFailedException($process);
            }

            $output = $process->getOutput();
            $errorOutput = $process->getErrorOutput();

            Log::info('Python Script Raw Output:', ['output' => $output]);
            if (! empty($errorOutput)) {
                Log::error('Python Script Error Output (stderr):', ['error' => $errorOutput]);
            }

            $jsonOutput = json_decode($output, true);

            if (json_last_error() === JSON_ERROR_NONE && isset($jsonOutput['status']) && $jsonOutput['status'] === 'success') {
                // Delete the temporary uploaded file after successful processing
                Storage::delete($filePath);

                return redirect()->back()->with('success', 'Document processed successfully!')->with('ocr_data', $jsonOutput['extracted_text']);
            } else {
                // Delete the temporary uploaded file even on JSON error
                Storage::delete($filePath);

                $errorMessage = 'Python script executed, but returned invalid or error JSON.';
                if (json_last_error() !== JSON_ERROR_NONE) {
                    $errorMessage .= ' JSON Error: '.json_last_error_msg();
                } elseif (isset($jsonOutput['message'])) {
                    $errorMessage .= ' Python Message: '.$jsonOutput['message'];
                }

                return redirect()->back()->with('error', $errorMessage)->with('raw_output', $output)->with('error_output', $errorOutput);
            }

        } catch (ProcessFailedException $exception) {
            Storage::delete($filePath); // Delete file on process failure
            $errorOutput = $exception->getProcess()->getErrorOutput();
            Log::error('Python script process failed:', [
                'command' => $process->getCommandLine(),
                'exit_code' => $process->getExitCode(),
                'error_output' => $errorOutput,
                'exception_message' => $exception->getMessage(),
            ]);

            return redirect()->back()->with('error', 'Failed to process document: '.$errorOutput);
        } catch (\Exception $e) {
            Storage::delete($filePath); // Delete file on general exception
            Log::error('General error in OCRController:', [
                'message' => $e->getMessage(),
                'file' => $e->getFile(),
                'line' => $e->getLine(),
            ]);

            return redirect()->back()->with('error', 'An unexpected error occurred: '.$e->getMessage());
        }
    }
}
