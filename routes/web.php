<?php

use App\Http\Controllers\OCRController;
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
use Illuminate\Support\Facades\Route;

// Route to show the upload form
Route::get('/upload-invoice', [OCRController::class, 'showUploadForm'])->name('ocr.form');

// Route to handle the form submission and process the document
Route::post('/process-invoice', [OCRController::class, 'processDocument'])->name('ocr.process');
// Optional: A simple route to test Python script execution directly (without file upload)
// This would be modified in OCRController for a hardcoded test file
// Route::get('/test-ocr-script', [OCRController::class, 'testPythonScript'])->name('ocr.test.script');
// (If you want a dedicated route for direct Python testing, you'd add a method 'testPythonScript' to OCRController)
