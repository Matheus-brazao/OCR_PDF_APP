import argparse
import io
import os
import shutil
import subprocess
import json
import csv
import sys
from tkinter import filedialog, Tk
from pathlib import Path
from statistics import mean
import fitz  # PyMuPDF
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\matheus.paixao\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
LANGS = "por+eng"  # idiomas padrão

def escolher_pdf():
    root = Tk()
    root.withdraw()
    filename = filedialog.askopenfilename(
        filetypes=[("PDF files","*.pdf")],
        title="Selecione o PDF para OCR"
    )
    return filename
def extract_native_text(pdf_path: Path) -> list[str]:
    doc = fitz.open(pdf_path)
    texts = []
    for page in doc:
        texts.append(page.get_text("text") or "")
    return texts

def save_txt(pages_text: list[str], out_txt: Path):
    with out_txt.open("w", encoding="utf-8") as f:
        for i, t in enumerate(pages_text, start=1):
            f.write(f"--- PAGE {i} ---\n")
            f.write((t or "").strip() + "\n\n")

def ocr_page_text_and_conf(img: Image.Image, langs: str):
    """
    Retorna:
      - text: string OCR da página
      - conf_list: lista de confs (0–100) por palavra (ignora -1)
      - words_count: total de palavras consideradas
    """
    text = pytesseract.image_to_string(img, lang=langs)

    tsv = pytesseract.image_to_data(img, lang=langs, output_type=pytesseract.Output.DATAFRAME)
    conf_vals = []
    words = 0
    if tsv is not None and len(tsv) > 0:
        # Filtra nível 'word' (level==5) se existir a coluna 'level'
        if "level" in tsv.columns:
            tsv = tsv[tsv["level"] == 5]
        # coluna 'conf' pode ter -1; filtrar válidos
        if "conf" in tsv.columns:
            for c in tsv["conf"].tolist():
                try:
                    c = float(c)
                except Exception:
                    continue
                if c >= 0:
                    conf_vals.append(c)
        # conta palavras não vazias
        if "text" in tsv.columns:
            words = sum(1 for w in tsv["text"].tolist() if isinstance(w, str) and w.strip())

    return text, conf_vals, words

def ocr_pages_to_text_and_conf(pdf_path: Path, dpi=300, langs=LANGS):
    """
    Retorna:
      texts: lista de textos por página
      report: dict com métricas (por página e global)
    """
    doc = fitz.open(pdf_path)
    texts = []
    page_reports = []

    for page_idx, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text, conf_vals, words = ocr_page_text_and_conf(img, langs)

        page_conf_mean = round(mean(conf_vals), 2) if conf_vals else None
        texts.append(text)

        page_reports.append({
            "page": page_idx + 1,
            "words": int(words),
            "conf_values_count": len(conf_vals),
            "mean_conf": page_conf_mean
        })

    # métricas globais
    all_confs = []
    total_words = 0
    for pr in page_reports:
        total_words += pr["words"]
        # não temos os arrays completos aqui; a média global será média ponderada por palavras:
        # para isso, rodamos OCR novamente? Melhor: recalcular somando pesos.
        # Como não guardamos os arrays, vamos computar média simples entre páginas ponderada por words.
        # Implementação: peso = words; média global = sum(mean_conf_i * words_i) / sum(words_i)
    num = 0.0
    den = 0
    for pr in page_reports:
        if pr["mean_conf"] is not None and pr["words"] > 0:
            num += pr["mean_conf"] * pr["words"]
            den += pr["words"]
    global_mean = round(num / den, 2) if den > 0 else None

    report = {
        "pages": page_reports,
        "global": {
            "total_pages": len(page_reports),
            "total_words": int(total_words),
            "mean_conf_weighted_by_words": global_mean
        }
    }
    return texts, report

def try_ocrmypdf(in_pdf: Path, out_pdf: Path) -> bool:
    """Tenta gerar PDF pesquisável com ocrmypdf (melhor opção)."""
    if shutil.which("ocrmypdf") is None:
        return False
    cmd = [
        "ocrmypdf",
        "--language", "por",
        "--language", "eng",
        "--deskew",
        "--optimize", "3",
        "--skip-text",
        str(in_pdf),
        str(out_pdf)
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception:
        return False

def build_searchable_pdf_fallback(in_pdf: Path, out_pdf: Path, overlay_text_pages: list[str], dpi=200):
    """
    Fallback simples:
    - Renderiza a página como imagem
    - Desenha a imagem como fundo
    - Sobrepõe texto OCR (visível; troque cor para branco se quiser “invisível”).
    """
    doc = fitz.open(in_pdf)
    c = canvas.Canvas(str(out_pdf))
    for idx, page in enumerate(doc):
        rect = page.rect
        width_pt, height_pt = rect.width, rect.height
        c.setPageSize((width_pt, height_pt))

        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        c.drawImage(ImageReader(img), 0, 0, width=width_pt, height=height_pt)

        txt = overlay_text_pages[idx] if idx < len(overlay_text_pages) else ""
        textobject = c.beginText(20, height_pt - 40)
        textobject.setFont("Helvetica", 8)
        # Para “invisível”, use texto branco (selecionável, mas não visível):
        # from reportlab.lib.colors import white
        # c.setFillColor(white)
        for line in txt.splitlines():
            if line.strip():
                textobject.textLine(line)
        c.drawText(textobject)
        c.showPage()
    c.save()

def save_report(report: dict, json_path: Path, csv_path: Path):
    # JSON
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV (por página)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "words", "conf_values_count", "mean_conf"])
        for p in report["pages"]:
            w.writerow([p["page"], p["words"], p["conf_values_count"], p["mean_conf"]])
        w.writerow([])
        g = report["global"]
        w.writerow(["GLOBAL_total_pages", g["total_pages"]])
        w.writerow(["GLOBAL_total_words", g["total_words"]])
        w.writerow(["GLOBAL_mean_conf_weighted_by_words", g["mean_conf_weighted_by_words"]])

def main():
    ap = argparse.ArgumentParser(description="OCR → TXT, PDF pesquisável e RELATÓRIO de confiança")
    ap.add_argument("input_pdf", nargs="?", help="Caminho do PDF de entrada")
    ap.add_argument("--outdir", default="out", help="Pasta de saída (default: out/)")
    ap.add_argument("--dpi", type=int, default=300, help="DPI para OCR/imagem (default: 300)")
    ap.add_argument("--langs", default=LANGS, help="Idiomas Tesseract (ex.: por, por+eng)")
    args = ap.parse_args()
    
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)

    
    outdir.mkdir(parents=True, exist_ok=True)

    pdf_path_str = args.input_pdf or escolher_pdf()
    if not pdf_path_str: 
        print("Nenhum PDF selecionado."); return

    in_pdf = Path(pdf_path_str).resolve()           # <-- só cria Path depois de garantir string

    

    base = in_pdf.stem
    out_txt = outdir / f"{base}.txt"
    out_searchable = outdir / f"{base}_searchable.pdf"
    out_json = outdir / f"{base}_ocr_report.json"
    out_csv  = outdir / f"{base}_ocr_report.csv"


    
    
    # 1) tenta extrair nativo
    native_pages = extract_native_text(in_pdf)
    native_chars = sum(len(t) for t in native_pages)

    if native_chars > 100:
        save_txt(native_pages, out_txt)
        if not try_ocrmypdf(in_pdf, out_searchable):
            out_searchable.write_bytes(in_pdf.read_bytes())
        # relatório “nativo”
        report = {
            "pages": [{"page": i+1, "words": None, "conf_values_count": None, "mean_conf": None} for i in range(len(native_pages))],
            "global": {"total_pages": len(native_pages), "total_words": None, "mean_conf_weighted_by_words": None},
            "note": "Documento já possuía texto nativo; confiança de OCR não se aplica."
        }
        save_report(report, out_json, out_csv)
        print(f"> OK (texto nativo). TXT: {out_txt}")
        print(f"> PDF pesquisável: {out_searchable}")
        print(f"> Relatórios: {out_json} | {out_csv}")
        return

    # 2) OCR com confidências
    print("> Rodando OCR com métricas de confiança...")
    texts, report = ocr_pages_to_text_and_conf(in_pdf, dpi=args.dpi, langs=args.langs)
    save_txt(texts, out_txt)
    save_report(report, out_json, out_csv)

    # 3) PDF pesquisável
    print("> Gerando PDF pesquisável...")
    if try_ocrmypdf(in_pdf, out_searchable):
        print(f"> PDF pesquisável (ocrmypdf): {out_searchable}")
    else:
        build_searchable_pdf_fallback(in_pdf, out_searchable, texts, dpi=200)
        print(f"> PDF pesquisável (fallback): {out_searchable}")

    # 4) resumo no terminal
    g = report["global"]
    print("\n=== OCR REPORT (RESUMO) ===")
    for p in report["pages"]:
        print(f"Página {p['page']:>2}: mean_conf={p['mean_conf']}  (palavras={p['words']})")
    print(f"GLOBAL: páginas={g['total_pages']}  palavras={g['total_words']}  mean_conf_w_avg={g['mean_conf_weighted_by_words']}")
    print(f"\n> TXT: {out_txt}")
    print(f"> PDF: {out_searchable}")
    print(f"> JSON: {out_json}")
    print(f"> CSV:  {out_csv}")

if __name__ == "__main__":
    main()


#comando a ser dado dentro da pasta ocr_pdf_app.py: python ocr_pdf_app.py "C:\Users\matheus.paixao\Downloads\prg jac.pdf" --outdir out --langs por+eng