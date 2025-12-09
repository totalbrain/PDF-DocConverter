import streamlit as st
import os
import io
import json
import time
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from collections import deque

from pdf2image import convert_from_bytes
from PIL import Image
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from google import genai
from google.genai import types

st.set_page_config(
    page_title="PDF to DOCX Converter",
    page_icon="📄",
    layout="centered"
)

PROGRESS_FILE = "progress.json"
OUTPUT_DIR = "output"
TEMP_DIR = "temp_images"

OCR_PROMPT = """You are an expert OCR + text corrector for Persian & English.
Extract and correct ALL text perfectly (spelling, grammar, punctuation).
Preserve formatting: titles with #, bold with **, lists, tables.
Output only clean corrected Markdown. No explanation."""

def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

def save_progress(data: dict):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_progress() -> Optional[dict]:
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def clear_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

def image_to_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()

def process_page_with_gemini(client, image: Image.Image, page_num: int, log_container) -> tuple[str, bool]:
    image_bytes = image_to_bytes(image)
    
    max_retries = 5
    base_delay = 6
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/png",
                    ),
                    OCR_PROMPT,
                ],
            )
            
            if response.text:
                return response.text, True
            else:
                return "", True
                
        except Exception as e:
            error_str = str(e).lower()
            
            if "429" in str(e) or "resource exhausted" in error_str or "quota" in error_str:
                delay = base_delay * (2 ** attempt)
                log_container.warning(f"⚠️ Rate limit hit on page {page_num}. Waiting {delay}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            elif "500" in str(e) or "503" in str(e) or "internal" in error_str or "unavailable" in error_str:
                delay = base_delay * (2 ** attempt)
                log_container.warning(f"⚠️ Server error on page {page_num}. Retrying in {delay}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                log_container.error(f"❌ Error on page {page_num}: {str(e)[:100]}")
                return "", False
    
    log_container.error(f"❌ Failed page {page_num} after {max_retries} attempts")
    return "", False

def markdown_to_docx(markdown_pages: list[str], output_path: str):
    doc = Document()
    
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial'
    font.size = Pt(11)
    
    for page_idx, md_content in enumerate(markdown_pages):
        if page_idx > 0:
            doc.add_page_break()
        
        lines = md_content.split('\n')
        
        for line in lines:
            line = line.rstrip()
            
            if not line:
                doc.add_paragraph()
                continue
            
            if line.startswith('# '):
                p = doc.add_heading(line[2:], level=1)
            elif line.startswith('## '):
                p = doc.add_heading(line[3:], level=2)
            elif line.startswith('### '):
                p = doc.add_heading(line[4:], level=3)
            elif line.startswith('#### '):
                p = doc.add_heading(line[5:], level=4)
            elif line.startswith('- ') or line.startswith('* '):
                p = doc.add_paragraph(line[2:], style='List Bullet')
            elif re.match(r'^\d+\. ', line):
                text = re.sub(r'^\d+\. ', '', line)
                p = doc.add_paragraph(text, style='List Number')
            elif line.startswith('|') and line.endswith('|'):
                p = doc.add_paragraph(line)
            else:
                p = doc.add_paragraph()
                
                parts = re.split(r'(\*\*.*?\*\*)', line)
                for part in parts:
                    if part.startswith('**') and part.endswith('**'):
                        run = p.add_run(part[2:-2])
                        run.bold = True
                    else:
                        p.add_run(part)
    
    doc.save(output_path)

def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"

def main():
    st.title("📄 PDF to DOCX Converter")
    st.markdown("Upload a PDF to extract and convert text using AI-powered OCR")
    
    client = get_gemini_client()
    if not client:
        st.error("⚠️ GEMINI_API_KEY not found in environment secrets. Please add it to continue.")
        st.info("Go to Secrets tab and add your Gemini API key with the name 'GEMINI_API_KEY'")
        return
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'cancel_requested' not in st.session_state:
        st.session_state.cancel_requested = False
    if 'completed_file' not in st.session_state:
        st.session_state.completed_file = None
    
    saved_progress = load_progress()
    
    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=['pdf'],
        help="Upload a PDF file (up to 400-500 pages supported)"
    )
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        start_button = st.button("🚀 Start Conversion", disabled=st.session_state.processing, use_container_width=True)
    
    with col2:
        resume_enabled = saved_progress is not None and not st.session_state.processing
        resume_button = st.button("⏩ Resume", disabled=not resume_enabled, use_container_width=True)
    
    with col3:
        if st.button("🛑 Cancel", disabled=not st.session_state.processing, use_container_width=True):
            st.session_state.cancel_requested = True
            st.warning("Cancellation requested... Finishing current page...")
    
    if saved_progress and not st.session_state.processing:
        st.info(f"📝 Previous progress found: {saved_progress.get('completed_pages', 0)}/{saved_progress.get('total_pages', 0)} pages completed")
    
    if st.session_state.completed_file and os.path.exists(st.session_state.completed_file):
        with open(st.session_state.completed_file, 'rb') as f:
            st.download_button(
                label="📥 Download DOCX",
                data=f.read(),
                file_name=os.path.basename(st.session_state.completed_file),
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
    
    if (start_button or resume_button) and not st.session_state.processing:
        st.session_state.processing = True
        st.session_state.cancel_requested = False
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        eta_text = st.empty()
        log_container = st.container()
        
        try:
            if resume_button and saved_progress:
                if not uploaded_file:
                    st.error("Please upload the same PDF file to resume")
                    st.session_state.processing = False
                    st.rerun()
                
                pdf_bytes = uploaded_file.read()
                markdown_pages = saved_progress.get('markdown_pages', [])
                failed_pages = saved_progress.get('failed_pages', [])
                start_page = saved_progress.get('completed_pages', 0)
                total_pages = saved_progress.get('total_pages', 0)
                
                with log_container:
                    st.info(f"📂 Resuming from page {start_page + 1}")
                
            else:
                if not uploaded_file:
                    st.error("Please upload a PDF file first")
                    st.session_state.processing = False
                    st.rerun()
                
                pdf_bytes = uploaded_file.read()
                
                with log_container:
                    st.info("📄 Converting PDF pages to images...")
                
                images = convert_from_bytes(pdf_bytes, dpi=300)
                total_pages = len(images)
                
                with log_container:
                    st.success(f"✅ Found {total_pages} pages")
                
                markdown_pages = [""] * total_pages
                failed_pages = []
                start_page = 0
                
                save_progress({
                    'total_pages': total_pages,
                    'completed_pages': 0,
                    'markdown_pages': markdown_pages,
                    'failed_pages': failed_pages,
                    'filename': uploaded_file.name
                })
            
            images = convert_from_bytes(pdf_bytes, dpi=300)
            
            page_times = deque(maxlen=10)
            
            for page_idx in range(start_page, total_pages):
                if st.session_state.cancel_requested:
                    with log_container:
                        st.warning(f"⚠️ Cancelled at page {page_idx + 1}")
                    break
                
                page_start_time = time.time()
                
                progress = (page_idx + 1) / total_pages
                progress_bar.progress(progress)
                status_text.text(f"Processing page {page_idx + 1} of {total_pages} ({int(progress * 100)}%)")
                
                if page_times:
                    avg_time = sum(page_times) / len(page_times)
                    remaining_pages = total_pages - page_idx - 1
                    eta_seconds = remaining_pages * avg_time
                    eta_text.text(f"⏱️ ETA: {format_time(eta_seconds)}")
                
                image = images[page_idx]
                
                text, success = process_page_with_gemini(client, image, page_idx + 1, log_container)
                
                if success:
                    markdown_pages[page_idx] = text
                    with log_container:
                        st.success(f"✅ Page {page_idx + 1} processed")
                else:
                    failed_pages.append(page_idx)
                    with log_container:
                        st.warning(f"⚠️ Page {page_idx + 1} queued for retry")
                
                if (page_idx + 1) % 10 == 0:
                    save_progress({
                        'total_pages': total_pages,
                        'completed_pages': page_idx + 1,
                        'markdown_pages': markdown_pages,
                        'failed_pages': failed_pages,
                        'filename': uploaded_file.name
                    })
                
                page_time = time.time() - page_start_time
                page_times.append(page_time)
                
                if page_idx < total_pages - 1:
                    time.sleep(6)
            
            if not st.session_state.cancel_requested and failed_pages:
                with log_container:
                    st.info(f"🔄 Retrying {len(failed_pages)} failed pages...")
                
                retry_failed = []
                for fail_idx in failed_pages:
                    if st.session_state.cancel_requested:
                        break
                    
                    image = images[fail_idx]
                    text, success = process_page_with_gemini(client, image, fail_idx + 1, log_container)
                    
                    if success:
                        markdown_pages[fail_idx] = text
                        with log_container:
                            st.success(f"✅ Page {fail_idx + 1} recovered")
                    else:
                        retry_failed.append(fail_idx)
                    
                    time.sleep(6)
                
                if retry_failed:
                    with log_container:
                        st.warning(f"⚠️ {len(retry_failed)} pages could not be recovered: {[p+1 for p in retry_failed]}")
            
            if not st.session_state.cancel_requested:
                with log_container:
                    st.info("📝 Creating DOCX document...")
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base_name = Path(uploaded_file.name).stem
                output_filename = f"{base_name}_{timestamp}.docx"
                output_path = os.path.join(OUTPUT_DIR, output_filename)
                
                markdown_to_docx(markdown_pages, output_path)
                
                progress_bar.progress(1.0)
                status_text.text("✅ Conversion complete!")
                eta_text.empty()
                
                st.session_state.completed_file = output_path
                
                clear_progress()
                
                with log_container:
                    st.success(f"🎉 Document saved! Click Download button above.")
        
        except Exception as e:
            with log_container:
                st.error(f"❌ Error: {str(e)}")
            
            if "quota" in str(e).lower() or "exceeded" in str(e).lower():
                st.error("⚠️ API quota exceeded. Please wait or upgrade your Gemini API plan.")
        
        finally:
            st.session_state.processing = False
            st.rerun()

if __name__ == "__main__":
    main()
