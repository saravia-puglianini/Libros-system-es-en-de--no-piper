#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get('PORTABLE_ROOT', os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR) == 'scripting' else SCRIPT_DIR)

# Dynamically add portable python site-packages to sys.path
for folder in os.listdir(PROJECT_ROOT):
    if folder.startswith('portable-bin-'):
        site_pkg = os.path.join(PROJECT_ROOT, folder, 'python', 'site-packages')
        if os.path.exists(site_pkg) and site_pkg not in sys.path:
            sys.path.insert(0, site_pkg)

# Add scripting directory to path so we can import check_garbled
sys.path.append(SCRIPT_DIR)
import check_garbled

def get_book_info(pdf_path):
    base_name = os.path.basename(pdf_path)
    # Check language extension (e.g. book.es.pdf)
    match = re.search(r'\.(en|es|de)\.pdf$', base_name, re.IGNORECASE)
    if match:
        orig_lang = match.group(1).lower()
        book_name = base_name[:match.start()]
    else:
        orig_lang = 'en'
        if base_name.lower().endswith('.pdf'):
            book_name = base_name[:-4]
        else:
            book_name = base_name
    return book_name, orig_lang

def get_total_pages(pdf_path):
    try:
        # Try pdfinfo
        result = subprocess.run(['pdfinfo', pdf_path], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if line.startswith('Pages:'):
                return int(line.split()[1])
    except Exception:
        pass
    
    try:
        # Try qpdf
        result = subprocess.run(['qpdf', '--show-npages', pdf_path], capture_output=True, text=True, check=True)
        return int(result.stdout.strip())
    except Exception:
        pass
    
    return 0

def clean_text_content(content):
    permitidos = "0123456789abcdefghijklmnñopqrstuvwxyzäöüáéíóúßABCDEFGHIJKLMNÑOPQRSTUVWXYZÄÖÜÁÉÍÓÚ!?.,:;ʼ”“()- "
    set_permitidos = set(permitidos)
    signos_puntuacion = "!?.,:;ʼ”“()-"
    
    # 1. Filter permitted chars
    texto = "".join(c if c in set_permitidos else " " for c in content)
    # 2. Collapse whitespace
    texto = re.sub(r'\s+', ' ', texto)
    # 3. Punctuation rules
    for signo in signos_puntuacion:
        texto = texto.replace(f" {signo}", signo)
        texto = texto.replace(signo, f"{signo} ")
    # 4. Final collapse and strip
    return re.sub(r'\s+', ' ', texto).strip()

def run_ocr(pdf_path, page, orig_lang):
    tess_langs = {'en': 'eng', 'es': 'spa', 'de': 'deu'}
    tess_lang = tess_langs.get(orig_lang, 'eng')
    
    # Check if tesseract has this lang
    try:
        langs_out = subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True).stdout
        if tess_lang not in langs_out:
            tess_lang = 'eng'
    except Exception:
        tess_lang = 'eng'
        
    with tempfile.TemporaryDirectory() as tmpdir:
        img_prefix = os.path.join(tmpdir, f"page_img_{page}")
        # pdftoppm -png -f page -l page -r 150 -singlefile pdf img_prefix
        subprocess.run([
            'pdftoppm', '-png', '-f', str(page), '-l', str(page),
            '-r', '150', '-singlefile', pdf_path, img_prefix
        ], capture_output=True)
        
        img_path = img_prefix + ".png"
        if os.path.exists(img_path):
            text_prefix = os.path.join(tmpdir, f"page_text_{page}")
            subprocess.run([
                'tesseract', img_path, text_prefix, '-l', tess_lang,
                '--oem', '1', '--psm', '6'
            ], capture_output=True)
            
            txt_path = text_prefix + ".txt"
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
    return ""

def translate_page(text, target_lang):
    if not text.strip():
        return ""
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target=target_lang)
        # Handle chunking if too long (Google Translate limit is 5000 chars)
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        translated_chunks = [translator.translate(chunk) for chunk in chunks if chunk.strip()]
        return " ".join(translated_chunks)
    except Exception as e:
        print(f"⚠️ Error translating to {target_lang}: {e}. Falling back to original text.")
        return text

def process_page(pdf_path, page, orig_lang, cache_entry):
    # If already fully translated in cache, return it
    targets = ['es', 'en', 'de']
    if cache_entry and all(t in cache_entry and cache_entry[t].strip() for t in targets):
        return cache_entry

    print(f"[*] Procesando Página {page}...")
    
    # 1. pdftotext
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp_f:
        tmp_txt_path = tmp_f.name
    
    try:
        subprocess.run(['pdftotext', '-f', str(page), '-l', str(page), '-layout', pdf_path, tmp_txt_path], capture_output=True)
        
        # Check if garbled or empty
        needs_ocr = False
        if not os.path.exists(tmp_txt_path) or os.path.getsize(tmp_txt_path) == 0:
            needs_ocr = True
        elif check_garbled.is_garbled(tmp_txt_path, orig_lang):
            needs_ocr = True
            
        if needs_ocr:
            print(f"    [!] Página {page} requiere OCR (Tesseract)...")
            raw_text = run_ocr(pdf_path, page, orig_lang)
        else:
            with open(tmp_txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                raw_text = f.read()
    finally:
        if os.path.exists(tmp_txt_path):
            os.remove(tmp_txt_path)

    # 2. Clean text
    # Clean hyphens at line endings before regular cleaning
    raw_text = re.sub(r'-\n', '', raw_text)
    raw_text = re.sub(r'\n([^\n])', r' \1', raw_text)
    cleaned_text = clean_text_content(raw_text)
    
    if not cleaned_text.strip():
        return {"es": "", "en": "", "de": ""}

    # 3. Translate
    result = {}
    for lang in targets:
        # If cache already has this lang, reuse it
        if cache_entry and lang in cache_entry and cache_entry[lang].strip():
            result[lang] = cache_entry[lang]
        elif lang == orig_lang:
            result[lang] = cleaned_text
        else:
            result[lang] = translate_page(cleaned_text, lang)
            
    return result

def main():
    force_rebuild = False
    if "--force" in sys.argv:
        force_rebuild = True
        sys.argv.remove("--force")

    if len(sys.argv) < 2:
        print("Uso: python3 extract_and_translate.py <pdf_path> [--force]")
        sys.exit(1)
        
    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"Error: No se encontró {pdf_path}")
        sys.exit(1)
        
    book_name, orig_lang = get_book_info(pdf_path)
    total_pages = get_total_pages(pdf_path)
    print(f"📖 Libro: {book_name} | Idioma origen: {orig_lang} | Páginas: {total_pages}")
    
    # Setup cache file
    cache_dir = os.path.join(PROJECT_ROOT, 'personal', 'text_cache')
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{book_name}.json")
    
    if force_rebuild and os.path.exists(cache_path):
        print(f"[!] --force detectado. Eliminando caché de traducción previa: {cache_path}")
        try:
            os.remove(cache_path)
        except Exception as e:
            print(f"⚠️ Error al eliminar caché: {e}")

    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[+] Cargado cache existente desde {cache_path}")
        except Exception as e:
            print(f"⚠️ Error cargando cache: {e}. Iniciando de cero.")
            
    # We will process in parallel using a ThreadPoolExecutor
    # 4 workers is a good balance for web requests / CPU
    max_workers = min(4, os.cpu_count() or 1)
    
    try:
        # Ensure deep_translator is installed
        try:
            import deep_translator
        except ImportError:
            print("[*] Instalando deep-translator...")
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'deep-translator'], check=True)
    except Exception as e:
        print(f"⚠️ Warning calling pip: {e}. Make sure deep-translator is installed.")
    
    # Parse range if OVERRIDE_RANGE is set
    start_page = 1
    end_page = total_pages
    override_range = os.environ.get('OVERRIDE_RANGE')
    if override_range:
        range_str = override_range.strip()
        if range_str and range_str != "0":
            match_range = re.match(r'^(\d+)-(\d+)$', range_str)
            if match_range:
                start_page = int(match_range.group(1))
                end_page = int(match_range.group(2))
            else:
                match_single = re.match(r'^(\d+)$', range_str)
                if match_single:
                    start_page = 1
                    end_page = int(match_single.group(1))
                else:
                    print(f"⚠️ Selección no reconocida. Usando rango por defecto: todas (1 a {total_pages}).")
            
            # Bound check
            start_page = max(1, min(start_page, total_pages))
            end_page = max(1, min(end_page, total_pages))
            if start_page > end_page:
                start_page, end_page = end_page, start_page
            print(f"[+] Rango seleccionado: Páginas {start_page} a {end_page}")

    # We loop pages and execute
    for page in range(start_page, end_page + 1):
        str_page = str(page)
        page_cache = cache.get(str_page)
        
        # Process single page
        res = process_page(pdf_path, page, orig_lang, page_cache)
        cache[str_page] = res
        
        # Save cache progressively
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
            
    print(f"🎉 Extracción y traducción completada para {book_name}. Cache guardado en: {cache_path}")

if __name__ == '__main__':
    main()
