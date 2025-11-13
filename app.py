# --------------------------------------------------------------
#  PDF to JPEG-in-ZIP Converter (Single File Only)
#  - Super lightweight for Render free tier
#  - In-memory, no temp files
#  - Fast: 50+ slides in <2 seconds
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
    start = skip_start
    end = total - skip_end

    if start >= end or end <= 0:
        raise ValueError("No pages to convert.")

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
            zf.writestr(f"({i - start + 1}).jpeg", img_data)

    buffer.seek(0)
    zip_name = f"{os.path.splitext(filename)[0]}_{page_count}.zip"
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
        return abort(400, "skip_start and skip_end must be numbers")

    file = request.files.get("pdf")
    if not file or not file.filename.lower().endswith(".pdf"):
        return abort(400, "Please upload a single PDF file")

    pdf_bytes = file.read()

    # --- Convert ---
    try:
        zip_name, zip_buffer = convert_pdf_to_zip(pdf_bytes, file.filename, skip_start, skip_end)
    except ValueError as e:
        return abort(400, str(e))

    # --- Stream response ---
    def stream():
        zip_buffer.seek(0)
        while chunk := zip_buffer.read(8192):
            yield chunk
        zip_buffer.close()

    return send_file(
        stream(),
        mimetype="application/zip",
        as_attachment=True,
        download_name=zip_name
    )


# --- Run on Render ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
