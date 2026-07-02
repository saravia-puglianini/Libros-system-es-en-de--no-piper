#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generar_htm_con_audios.py

Genera un visor htm offline interactivo HTML (con el PDF inyectado en Base64)
e inyecta soporte de texto a voz nativo (Web Speech API) para español (es),
inglés (en) y alemán (de) leyendo desde el cache de traducciones.
"""

import sys
import os
import re
import json
import base64

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get('PORTABLE_ROOT', os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR) == 'scripting' else SCRIPT_DIR)

def get_total_pages(pdf_path):
    try:
        import subprocess
        result = subprocess.run(['pdfinfo', pdf_path], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if line.startswith('Pages:'):
                return int(line.split()[1])
    except Exception:
        pass
    try:
        import subprocess
        result = subprocess.run(['qpdf', '--show-npages', pdf_path], capture_output=True, text=True, check=True)
        return int(result.stdout.strip())
    except Exception:
        pass
    return 0

def get_book_name(pdf_path):
    base_name = os.path.basename(pdf_path)
    # Patrón: nombre_libro.<idioma>.pdf
    match = re.search(r'\.(en|es|de)\.pdf$', base_name, re.IGNORECASE)
    if match:
        return base_name[:match.start()]
    else:
        if base_name.lower().endswith('.pdf'):
            return base_name[:-4]
        return base_name

def generate_htm(template_content, pdf_base64, text_map, filename, output_path):
    html = template_content
    
    # 1. Inyección de CSS para los botones de Audio
    css_to_inject = """
        /* Estilos Premium para Controles de Audio/Texto */
        .audio-controls {
            display: flex;
            flex-direction: column;
            align-items: stretch;
            width: 100%;
            gap: 0.5rem;
            margin-top: 0.5rem;
            margin-bottom: 0.5rem;
        }

        .audio-buttons-row {
            display: flex;
            flex-direction: row;
            justify-content: space-between;
            width: 100%;
            gap: 0.5rem;
        }

        .audio-btn {
            flex: 1;
            aspect-ratio: 1;
            justify-content: center;
            font-weight: bold;
            font-size: 1.1rem;
            padding: 10px;
            border: none;
            border-radius: 8px;
            background: #ffffff !important;
            color: var(--text-color);
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            text-transform: lowercase;
        }

        .audio-btn:hover:not(:disabled) {
            background: var(--text-color);
            color: #ffffff;
        }

        .audio-btn:disabled {
            opacity: 0.25;
            cursor: not-allowed;
            border-style: none;
        }

        .audio-btn.playing {
            background: #e74c3c;
            color: white;
            border-color: #e74c3c;
            animation: pulse-ring 2s infinite;
        }

        @keyframes pulse-ring {
            0% { box-shadow: 0 0 0 0 rgba(231, 76, 60, 0.4); }
            70% { box-shadow: 0 0 0 6px rgba(231, 76, 60, 0); }
            100% { box-shadow: 0 0 0 0 rgba(231, 76, 60, 0); }
        }

        /* Autoplay Toggle Premium Switch */
        .autoplay-container {
            display: none !important;
            align-items: center;
            justify-content: space-between;
            background: rgba(0,0,0,0.03);
            border: 2px solid var(--border-color);
            border-radius: 8px;
            padding: 8px 12px;
            font-weight: bold;
            font-size: 0.9rem;
            color: var(--text-color);
            margin-top: 0.25rem;
        }

        .switch {
            position: relative;
            display: inline-block;
            width: 44px;
            height: 24px;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #ccc;
            transition: .3s;
            border-radius: 24px;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }

        input:checked + .slider {
            background-color: #2ecc71;
        }

        input:checked + .slider:before {
            transform: translateX(20px);
        }
    """
    
    if "</style>" in html:
        html = html.replace("</style>", css_to_inject + "\n</style>", 1)

    # Inyección de HTML para los botones (los 3 idiomas siempre habilitados)
    html_to_inject = '\n            <div class="audio-controls">\n'
    html_to_inject += '                <div class="audio-buttons-row">\n'
    html_to_inject += '                    <button id="play-es" class="audio-btn" disabled>es</button>\n'
    html_to_inject += '                    <button id="play-en" class="audio-btn" disabled>en</button>\n'
    html_to_inject += '                    <button id="play-de" class="audio-btn" disabled>de</button>\n'
    html_to_inject += '                </div>\n'
    html_to_inject += """                <div class="autoplay-container">
                    <span>💡 Manos Libres</span>
                    <label class="switch" title="Cambio automático de página al terminar lectura">
                        <input type="checkbox" id="autoplay-toggle" checked>
                        <span class="slider"></span>
                    </label>
                </div>\n"""
    html_to_inject += '            </div>\n'

    if '<div class="zoom-controls">' in html:
        html = html.replace('<div class="zoom-controls">', html_to_inject + '\n            <div class="zoom-controls">', 1)

    # Configuración del nombre del archivo en la UI
    new_logic = f"""        const fileName = "{filename}";
        document.getElementById('filename').textContent = fileName;
        document.title = fileName;"""
    
    html = re.sub(r'const urlParams = new URLSearchParams\(window\.location\.search\);.*?document\.title = fileName;\s*\}', new_logic, html, flags=re.DOTALL)
    html = html.replace("pdfjsLib.getDocument(fileName)", "pdfjsLib.getDocument({data: pdfData})")

    # Inyectar pdfData Base64
    data_injection = f'\n        const pdfData = atob("{pdf_base64}");\n'
    insertion_point = "pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;"
    if insertion_point in html:
        html = html.replace(insertion_point, insertion_point + data_injection)
    else:
        html = html.replace("<script>\n        // Setup worker", "<script>\n" + data_injection + "        // Setup worker")

    # Inyectar Lógica de Reproducción TTS en JavaScript
    js_to_inject = f"""
        // --- LOGICA DE VOCIFERACION NATIVA (TTS) POR PAGINA ---
        const textMap = {json.dumps(text_map, indent=12)};
        let activeLang = null;

        // Get requested lang from URL
        const urlParamsAudio = new URLSearchParams(window.location.search);
        const reqLang = urlParamsAudio.get('lang');
        const fallbackChain = [];
        if (reqLang) fallbackChain.push(reqLang.toLowerCase());
        ['es', 'en', 'de'].forEach(l => {{
            if (!fallbackChain.includes(l)) fallbackChain.push(l);
        }});

        function stopAllAudio() {{
            if (window.speechSynthesis.speaking) {{
                window.speechSynthesis.cancel();
            }}
            const langs = ['en', 'es', 'de'];
            langs.forEach(l => {{
                const btn = document.getElementById('play-' + l);
                if (btn) {{
                    btn.textContent = l;
                    btn.classList.remove('playing');
                }}
            }});
            activeLang = null;
            const globalBtn = document.getElementById('global-play-btn');
            if (globalBtn) globalBtn.textContent = '>';
        }}

        function toggleAudio(lang) {{
            if (document.body.classList.contains('txt-mode')) {{
                if (window.speechSynthesis.speaking && activeLang === lang) {{
                    exitTxtMode();
                    return;
                }}
                activeLang = lang;
                speakCurrentPage();
                return;
            }}
            const pageText = textMap[pageNum] && textMap[pageNum][lang];
            if (!pageText || !pageText.trim()) {{
                const autoplayActive = document.getElementById('autoplay-toggle')?.checked;
                if (autoplayActive && pageNum < pdfDoc.numPages) {{
                    setTimeout(() => onNextPage(), 1000);
                }}
                return;
            }}

            const btn = document.getElementById('play-' + lang);

            // Si ya se está hablando el mismo idioma, detenemos
            if (window.speechSynthesis.speaking && activeLang === lang) {{
                stopAllAudio();
                return;
            }}

            // Detener cualquier audio previo
            stopAllAudio();

            // Configurar síntesis de voz nativa
            const mensaje = new SpeechSynthesisUtterance(pageText);
            if (lang === 'es') mensaje.lang = "es-ES";
            else if (lang === 'en') mensaje.lang = "en-US";
            else if (lang === 'de') mensaje.lang = "de-DE";
            else mensaje.lang = lang;
            
            activeLang = lang;
            
            // Re-order fallback chain to keep selected language
            const idx = fallbackChain.indexOf(lang);
            if (idx > -1) fallbackChain.splice(idx, 1);
            fallbackChain.unshift(lang);

            btn.textContent = lang;
            btn.classList.add('playing');
            
            const globalBtn = document.getElementById('global-play-btn');
            if (globalBtn) globalBtn.textContent = '||';

            mensaje.onend = () => {{
                stopAllAudio();
                
                const autoplayActive = document.getElementById('autoplay-toggle')?.checked;
                if (autoplayActive && pageNum < pdfDoc.numPages) {{
                    onNextPage();
                }}
            }};

            let resumeOnInteraction = null;
            mensaje.onerror = (e) => {{
                if (e && e.error === 'not-allowed') {{
                    console.warn("SpeechSynthesis blocked by autoplay policy. Waiting for user interaction...");
                    if (!resumeOnInteraction) {{
                        resumeOnInteraction = () => {{
                            document.removeEventListener('click', resumeOnInteraction);
                            document.removeEventListener('keydown', resumeOnInteraction);
                            toggleAudio(lang);
                        }};
                        document.addEventListener('click', resumeOnInteraction);
                        document.addEventListener('keydown', resumeOnInteraction);
                    }}
                }} else if (e && e.error !== 'interrupted') {{
                    console.error("SpeechSynthesis error:", e);
                }}
                stopAllAudio();
            }};

            window.speechSynthesis.speak(mensaje);

            // Ocultar menú al reproducir
            if (headerEl && showHeaderBtn) {{
                headerEl.style.display = 'none';
                showHeaderBtn.style.display = 'block';
                window.dispatchEvent(new Event('resize'));
            }}
        }}

        let isFirstLoad = true;

        function updateAudioButtons(num) {{
            stopAllAudio();
            const langs = ['en', 'es', 'de'];
            langs.forEach(lang => {{
                const btn = document.getElementById('play-' + lang);
                if (btn) {{
                    const hasText = textMap[num] && textMap[num][lang] && textMap[num][lang].trim();
                    if (hasText) {{
                        btn.removeAttribute('disabled');
                        btn.textContent = lang;
                    }} else {{
                        btn.setAttribute('disabled', 'true');
                        btn.textContent = lang;
                    }}
                }}
            }});

            const autoplayActive = document.getElementById('autoplay-toggle')?.checked;
            
            if (isFirstLoad) {{
                if (autoplayActive) {{
                    if (!document.body.classList.contains('sano-mode')) {{
                        document.body.classList.add('sano-mode');
                        if (headerEl && headerEl.style.display !== 'none') {{
                            headerEl.style.display = 'none';
                            if (showHeaderBtn) showHeaderBtn.style.display = 'block';
                        }}
                    }}
                }}
                isFirstLoad = false;
            }}

            // Autoplay only if Sano Mode is currently active
            if (autoplayActive && document.body.classList.contains('sano-mode')) {{
                let played = false;
                for (let i = 0; i < fallbackChain.length; i++) {{
                    const l = fallbackChain[i];
                    if (textMap[num] && textMap[num][l] && textMap[num][l].trim()) {{
                        setTimeout(() => toggleAudio(l), 800);
                        played = true;
                        break;
                    }}
                }}
                
                if (!played && pageNum < pdfDoc.numPages) {{
                    setTimeout(() => onNextPage(), 1000);
                }}
            }}
        }}

        // Enlace de Eventos
        const btnEn = document.getElementById('play-en');
        if (btnEn) btnEn.addEventListener('click', () => toggleAudio('en'));
        const btnEs = document.getElementById('play-es');
        if (btnEs) btnEs.addEventListener('click', () => toggleAudio('es'));
        const btnDe = document.getElementById('play-de');
        if (btnDe) btnDe.addEventListener('click', () => toggleAudio('de'));

        // Lógica de Mostrar/Ocultar Menú
        if (hideHeaderBtn && showHeaderBtn && headerEl) {{
            hideHeaderBtn.addEventListener('click', () => {{
                headerEl.style.display = 'none';
                showHeaderBtn.style.display = 'block';
                window.dispatchEvent(new Event('resize'));
            }});

            showHeaderBtn.addEventListener('click', () => {{
                headerEl.style.display = 'flex';
                showHeaderBtn.style.display = 'none';
                stopAllAudio();
                window.dispatchEvent(new Event('resize'));
            }});
        }}

        // Lógica Global Play Button
        setTimeout(() => {{
            const globalPlayBtn = document.getElementById('global-play-btn');
            if (globalPlayBtn) {{
                globalPlayBtn.addEventListener('click', () => {{
                    if (document.body.classList.contains('txt-mode')) {{
                        if (isReading) {{
                            exitTxtMode();
                        }} else {{
                            speakCurrentPage();
                        }}
                        return;
                    }}
                    if (window.speechSynthesis.speaking) {{
                        stopAllAudio();
                    }} else {{
                        for (let i = 0; i < fallbackChain.length; i++) {{
                            const l = fallbackChain[i];
                            if (textMap[pageNum] && textMap[pageNum][l] && textMap[pageNum][l].trim()) {{
                                toggleAudio(l);
                                break;
                            }}
                        }}
                    }}
                }});
            }}
        }}, 50);
    """

    # Inyectar el botón global de Play
    html_global_play = """
    <button id="global-play-btn" title="Reproducir/Pausar" style="position: fixed; bottom: 20px; right: 20px; z-index: 100000; background: var(--toolbar-bg, white); border: 2px solid var(--border-color, #ccc); border-radius: 50%; width: 50px; height: 50px; font-weight: bold; font-size: 1.5rem; cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(0,0,0,0.2); color: var(--text-color, black);">&gt;</button>
    """
    
    script_end = "</script>\n</body>"
    if script_end in html:
        html = html.replace(script_end, js_to_inject + f"\n    </script>\n{html_global_play}\n</body>", 1)
    else:
        html = html.replace("</body>", f"<script>{js_to_inject}</script>\n{html_global_play}\n</body>", 1)

    # Inyectar el hook en renderPage para actualizar botones al cambiar de página
    old_render_end = "if (pageNumEl) pageNumEl.value = num;"
    new_render_end = """if (pageNumEl) pageNumEl.value = num;
            if (typeof updateAudioButtons === 'function') {
                updateAudioButtons(num);
            }"""
    if old_render_end in html:
        html = html.replace(old_render_end, new_render_end, 1)

    # Guardar el HTM generado
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[+] Visor htm generado con éxito en: {output_path}")

def main():
    if len(sys.argv) < 3:
        print("Uso: python3 generar_htm_con_audios.py <pdf_path> <output_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2]
    
    template_path = f"{PROJECT_ROOT}/scripting/htm.htm"
    if not os.path.exists(template_path):
        print(f"Error: Template {template_path} no encontrado.")
        sys.exit(1)

    print(f"[*] Leyendo el template: {template_path}")
    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
    template_content = template_content.replace('\r\n', '\n')

    filename = os.path.basename(pdf_path)
    book_name = get_book_name(pdf_path)
    print(f"[*] Libro: '{book_name}'")

    # Parse range if OVERRIDE_RANGE is set
    total_pages = get_total_pages(pdf_path)
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
            
            # Bound check
            start_page = max(1, min(start_page, total_pages))
            end_page = max(1, min(end_page, total_pages))
            if start_page > end_page:
                start_page, end_page = end_page, start_page

    # Leer textos traducidos
    cache_path = os.path.join(PROJECT_ROOT, 'personal', 'text_cache', f"{book_name}.json")
    if not os.path.exists(cache_path):
        print(f"⚠️ Error: No se encontró cache de traducciones en {cache_path}. Por favor ejecute extract_and_translate.py primero.")
        sys.exit(1)
        
    with open(cache_path, 'r', encoding='utf-8') as f:
        text_map = json.load(f)

    # If partial range selected, crop PDF and reindex translations
    if start_page > 1 or end_page < total_pages:
        import tempfile
        import subprocess
        
        filename = f"{os.path.basename(pdf_path)} (Pág. {start_page}-{end_page})"
        print(f"[*] Recortando PDF para las páginas {start_page} a {end_page}...")
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_f:
            temp_pdf_path = tmp_f.name
        
        try:
            result = subprocess.run([
                "qpdf", "--empty",
                "--pages", pdf_path, f"{start_page}-{end_page}",
                "--", temp_pdf_path
            ], capture_output=True, text=True)
            if result.returncode not in (0, 3):
                raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
            
            with open(temp_pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        finally:
            if os.path.exists(temp_pdf_path):
                try:
                    os.remove(temp_pdf_path)
                except Exception:
                    pass
        
        # Reindex text_map
        new_text_map = {}
        for p in range(1, (end_page - start_page + 1) + 1):
            orig_page = start_page + p - 1
            if str(orig_page) in text_map:
                new_text_map[str(p)] = text_map[str(orig_page)]
        text_map = new_text_map
    else:
        # Codificar el PDF original a Base64
        print("[*] Codificando PDF a Base64...")
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    # Generar visor
    generate_htm(template_content, pdf_base64, text_map, filename, output_path)

if __name__ == "__main__":
    main()
