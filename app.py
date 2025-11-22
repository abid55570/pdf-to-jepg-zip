# --------------------------------------------------------------
#  PDF → JPEG → Streaming ZIP (supports 300–1500 pages)
#  Ultra-low RAM, perfect for Render free tier
# --------------------------------------------------------------

import os
from flask import Flask, render_template, request, Response, abort
import fitz  # PyMuPDF
from zipstream import ZipStream

app = Flask(__name__)

# --------------------- Config ---------------------
MAX_PAGES = 1500       # Safe limit
DPI = 55               # Low memory footprint
JPEG_QUALITY = 60      # Balanced size/quality
# --------------------------------------------------


def generate_streaming_zip(pdf_bytes, filename, skip_start, skip_end):
    """Yields ZIP chunks without storing anything in memory."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)

    # Page range
    start = skip_start
    end = total - skip_end

    if start >= end or end <= 0:
        raise ValueError("No pages to convert")

    page_count = end - start
    if page_count > MAX_PAGES:
        raise ValueError(f"Too many pages: {page_count} > {MAX_PAGES}")

    zip_filename = f"{os.path.splitext(filename)[0]}_{page_count}.zip"

    # Create streaming ZIP
    zs = ZipStream()

    # Add each page as a separate streamed JPEG
    for i in range(start, end):
        def make_generator(page_index):

            def jpeg_generator():
                page = doc.load_page(page_index)

                # Low-RAM pixmap
                pix = page.get_pixmap(matrix=fitz.Matrix(DPI / 72, DPI / 72), alpha=False)
                data = pix.tobytes("jpeg", jpg_quality=JPEG_QUALITY)

                # Yield JPEG bytes
                yield data

                # Free memory
                pix = None
                page = None

            return jpeg_generator

        zs.add(f"({i - start + 1}).jpeg", make_generator(i))

    return zip_filename, zs


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    # --- Get form data ---
    try:
        skip_start = int(request.form.get("skip_start", 0))
        skip_end = int(request.form.get("skip_end", 0))
    except:
        return abort(400, "skip_start and skip_end must be integers")

    file = request.files.get("pdf")
    if not file or not file.filename.lower().endswith(".pdf"):
        return abort(400, "Upload a single PDF file")

    pdf_bytes = file.read()

    # Build streaming zip
    try:
        zip_name, zs = generate_streaming_zip(pdf_bytes, file.filename, skip_start, skip_end)
    except Exception as e:
        return abort(400, str(e))

    # Streaming response
    response = Response(
        zs.stream(),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"}
    )
    return response


# --- Run on Render ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
