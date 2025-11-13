# --------------------------------------------------------------
#  PDF to JPEG-in-ZIP Converter (Single File Only)
#  - Super lightweight for Render free tier
#  - In-memory, no temp files
# --------------------------------------------------------------

import os
import io
import zipfile
from flask import Flask, render_template, request, send_file, abort
import fitz  # PyMuPDF

app = Flask(__name__)

# --------------------- Config ---------------------
MAX_PAGES = 100        # Prevent abuse
DPI = 72               # Small images (~0.4 MB per page)
JPEG_QUALITY = 75      # Good balance size/quality
# --------------------------------------------------

def convert_pdf_to_zip(pdf_bytes: bytes, filename: str, skip_start: int, skip_end: int):
    """Convert one PDF → return (zip_name, BytesIO)"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)
    start = max(0, skip_start)
    end = total - max(0, skip_end)

    if start >= end or end <= 0:
        raise ValueError("No pages to convert. Check skip_start/skip_end values.")

    page_count = end - start
    if page_count > MAX_PAGES:
        raise ValueError(f"Too many pages: {page_count} > {MAX_PAGES}")

    # Build ZIP in memory
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(start, end):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=DPI)
            img_data = pix.tobytes("jpeg", jpg_quality=JPEG_QUALITY)
            # name pages starting at 1 inside the zip
            zf.writestr(f"({i - start + 1}).jpeg", img_data)

    buffer.seek(0)
    safe_name = os.path.splitext(os.path.basename(filename))[0]
    zip_name = f"{safe_name}_{page_count}.zip"
    return zip_name, buffer


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    # --- Get form data ---
    try:
        skip_start = int(request.form.get("skip_start", 0))
        skip_end = int(request.form.get("skip_end", 0))
    except ValueError:
        return abort(400, "skip_start and skip_end must be integers")

    file = request.files.get("pdf")
    if not file or not file.filename or not file.filename.lower().endswith(".pdf"):
        return abort(400, "Please upload a single PDF file")

    pdf_bytes = file.read()

    # --- Convert ---
    try:
        zip_name, zip_buffer = convert_pdf_to_zip(pdf_bytes, file.filename, skip_start, skip_end)
    except ValueError as e:
        return abort(400, str(e))
    except Exception as e:
        # unexpected error -> log on server; user gets 500
        app.logger.exception("Conversion failed")
        return abort(500, "Internal server error during conversion")

    # --- Return the in-memory BytesIO using send_file (works with gunicorn) ---
    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=zip_name
    )


# --- Run on Render / locally ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
