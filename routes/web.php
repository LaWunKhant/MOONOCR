<?php

use App\Http\Controllers\OCRController;
use Illuminate\Support\Facades\Route; // Your new controller

/*
|--------------------------------------------------------------------------
| Web Routes
|--------------------------------------------------------------------------
|
| Here is where you can register web routes for your application. These
| routes are loaded by the RouteServiceProvider and all of them will
| be assigned to the "web" middleware group. Make something great!
|
*/

// Route to show the upload form
Route::get('/upload-document', [OCRController::class, 'showUploadForm'])->name('ocr.upload.form');

// Route to handle the file upload and OCR processing
Route::post('/process-document', [OCRController::class, 'processDocument'])->name('ocr.process');

// Optional: A simple route to test Python script execution directly (without file upload)
// This would be modified in OCRController for a hardcoded test file
// Route::get('/test-ocr-script', [OCRController::class, 'testPythonScript'])->name('ocr.test.script');
// (If you want a dedicated route for direct Python testing, you'd add a method 'testPythonScript' to OCRController)
