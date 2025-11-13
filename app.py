# --------------------------------------------------------------
#  Lightweight PDF → JPEG-in-ZIP converter (Flask)
#  - No on-disk JPEGs
#  - In-memory ZIP streaming
#  - Configurable DPI / JPEG quality
#  - Hard page-count limit
# --------------------------------------------------------------

import os
import io
import zipfile
import tempfile
from flask import Flask, render_template, request, send_file, stream_with_context, abort

import fitz  # PyMuPDF

app = Flask(__name__)

# --------------------------------------------------------------
#  Configuration (tweak for your free tier)
# --------------------------------------------------------------
MAX_PAGES_PER_PDF = 100          # safety net – increase if you trust the source
DPI = 72                         # 72 → ~ 0.5 MB per page; 100 → ~ 1 MB
JPEG_QUALITY = 75                # 0-100, lower = smaller file
CHUNK_SIZE = 8192                # streaming chunk size


# --------------------------------------------------------------
#  Core conversion – yields (filename, bytes_io) for each PDF
# --------------------------------------------------------------
def pdf_to_zip_stream(pdf_bytes: bytes, original_name: str, skip_start: int, skip_end: int):
    """
    Yield (zip_entry_name, BytesIO) for a single PDF.
    The ZIP contains JPEGs named (1).jpeg … (N).jpeg.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    start = skip_start
    end = total_pages - skip_end
    if start >= end:
        return

    page_count = end - start
    if page_count > MAX_PAGES_PER_PDF:
        raise ValueError(f"PDF would produce {page_count} pages – exceeds limit of {MAX_PAGES_PER_PDF}")

    # Build ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx in range(start, end):
            page = doc.load_page(idx)
            pix = page.get_pixmap(dpi=DPI)
            img_bytes = pix.tobytes("jpeg", jpg_quality=JPEG_QUALITY)

            entry_name = f"({idx - start + 1}).jpeg"
            zf.writestr(entry_name, img_bytes)

    zip_buffer.seek(0)
    zip_name = f"{os.path.splitext(original_name)[0]}_{page_count}.zip"
    yield zip_name, zip_buffer


# --------------------------------------------------------------
#  Flask routes
# --------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    # ---- POST -------------------------------------------------
    try:
        skip_start = int(request.form.get("skip_start", 0))
        skip_end   = int(request.form.get("skip_end", 0))
    except ValueError:
        abort(400, "skip_start / skip_end must be integers")

    uploaded = request.files.getlist("pdfs")
    if not uploaded:
        abort(400, "No PDF files uploaded")

    # ---------- Single PDF → direct download ----------
    if len(uploaded) == 1:
        file = uploaded[0]
        if not file.filename.lower().endswith(".pdf"):
            abort(400, "Only PDF files are allowed")
        pdf_bytes = file.read()

        def generate():
            for zip_name, zip_io in pdf_to_zip_stream(pdf_bytes, file.filename, skip_start, skip_end):
                yield from zip_io
        return send_file(
            generate(),
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_name,
        )

    # ---------- Multiple PDFs → master ZIP ----------
    def master_generator():
        master_zip = io.BytesIO()
        with zipfile.ZipFile(master_zip, "w", zipfile.ZIP_DEFLATED) as mz:
            for file in uploaded:
                if not file.filename.lower().endswith(".pdf"):
                    continue
                pdf_bytes = file.read()
                for sub_zip_name, sub_zip_io in pdf_to_zip_stream(
                    pdf_bytes, file.filename, skip_start, skip_end
                ):
                    sub_zip_io.seek(0)
                    mz.writestr(sub_zip_name, sub_zip_io.read())

        master_zip.seek(0)
        while True:
            chunk = master_zip.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk

    return send_file(
        stream_with_context(master_generator()),
        mimetype="application/zip",
        as_attachment=True,
        download_name="all_converted.zip",
    )


# --------------------------------------------------------------
#  Run (debug off for production)
# --------------------------------------------------------------
if __name__ == "__main__":
    # On Render free tier use the port supplied by the platform
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
