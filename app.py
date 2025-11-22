import os
from flask import Flask, render_template, request, Response, abort
import fitz  # PyMuPDF
from zipstream import ZipStream

app = Flask(__name__)

# --------------------- Config ---------------------
MAX_PAGES = 1500
DPI = 55
JPEG_QUALITY = 60
# --------------------------------------------------


def generate_streaming_zip(pdf_bytes, filename, skip_start, skip_end):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)

    start = skip_start
    end = total - skip_end

    if start >= end or end <= 0:
        raise ValueError("No pages to convert")

    page_count = end - start
    if page_count > MAX_PAGES:
        raise ValueError(f"Too many pages: {page_count} > {MAX_PAGES}")

    zip_filename = f"{os.path.splitext(filename)[0]}_{page_count}.zip"

    zs = ZipStream()

    # FIXED VERSION ----------------------------
    # zipstream requires data=<generator> NOT data=function
    # ------------------------------------------
    for i in range(start, end):

        def jpeg_gen(index=i):
            page = doc.load_page(index)
            pix = page.get_pixmap(
                matrix=fitz.Matrix(DPI / 72, DPI / 72),
                alpha=False,
            )
            yield pix.tobytes("jpeg", jpg_quality=JPEG_QUALITY)
            pix = None
            page = None

        # IMPORTANT: pass generator function via data=
        zs.add(
            name=f"page_{i - start + 1}.jpeg",
            data=jpeg_gen(),   # this is the FIX
        )

    return zip_filename, zs


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    try:
        skip_start = int(request.form.get("skip_start", 0))
        skip_end = int(request.form.get("skip_end", 0))
    except:
        return abort(400, "Invalid skip_start or skip_end")

    file = request.files.get("pdf")
    if not file or not file.filename.lower().endswith(".pdf"):
        return abort(400, "Upload a valid PDF")

    pdf_bytes = file.read()

    try:
        zip_name, zs = generate_streaming_zip(pdf_bytes, file.filename, skip_start, skip_end)
    except Exception as e:
        return abort(400, str(e))

    return Response(
        zs.stream(),
        mimetype='application/zip',
        headers={"Content-Disposition": f"attachment; filename={zip_name}"}
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
