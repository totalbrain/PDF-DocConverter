# PDF to DOCX Converter

## Overview

This is a PDF to DOCX converter application built with Streamlit that uses Google's Gemini AI for OCR (Optical Character Recognition) and text correction. The application converts PDF documents to Word documents with support for both Persian and English text, preserving formatting while correcting spelling, grammar, and punctuation.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend
- **Streamlit** - Used as the web framework for the user interface
- Single-page application with centered layout
- Page configured with custom title and icon

### Core Processing Pipeline
1. **PDF Processing** - Uses `pdf2image` library to convert PDF pages to images
2. **OCR & Text Correction** - Leverages Google Gemini AI API to extract and correct text from images
3. **Document Generation** - Uses `python-docx` library to create Word documents from extracted text

### Key Components
- **Progress Tracking** - JSON-based progress file (`progress.json`) for tracking conversion state
- **Temporary Storage** - Dedicated directories for temporary images (`temp_images/`) and output files (`output/`)
- **Gemini Integration** - Client wrapper for Google's Generative AI API with structured prompts for OCR

### Design Decisions
- **AI-Powered OCR**: Chose Gemini AI over traditional OCR libraries (like Tesseract) for better accuracy with mixed Persian/English text and automatic grammar/spelling correction
- **Markdown Intermediate Format**: Text is extracted as Markdown to preserve formatting (headings, bold, lists, tables) before converting to DOCX
- **Progress Persistence**: JSON file-based progress tracking enables resumable conversions

## External Dependencies

### APIs & Services
- **Google Gemini AI** - Primary OCR and text correction service
  - Requires `GEMINI_API_KEY` environment variable
  - Uses `google-genai` Python client library

### Python Libraries
- `streamlit` - Web application framework
- `pdf2image` - PDF to image conversion (requires poppler system dependency)
- `Pillow` (PIL) - Image processing
- `python-docx` - Word document generation
- `google-genai` - Google Generative AI client

### System Dependencies
- **Poppler** - Required by pdf2image for PDF rendering (must be installed at system level)