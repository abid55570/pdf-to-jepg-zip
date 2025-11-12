import os
import zipfile
import tempfile
import fitz  # PyMuPDF
from flask import Flask, render_template, request, send_file

app = Flask(__name__)

# --- Utility function ---
def convert_pdf(pdf_path, pdf_original_name, skip_start, skip_end):
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    start_index = skip_start
    end_index = total_pages - skip_end
    if start_index >= end_index:
        return None, 0, None

    temp_dir = tempfile.mkdtemp()
    pdf_name = os.path.splitext(pdf_original_name)[0]

    # Convert pages to images (renumber from (1))
    page_counter = 1
    for i in range(start_index, end_index):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=200)
        img_path = os.path.join(temp_dir, f"({page_counter}).jpeg")
        pix.save(img_path)
        page_counter += 1

    # Create ZIP file named <pdf_name>_<page_count>.zip
    page_count = end_index - start_index
    zip_name = f"{pdf_name}_{page_count}.zip"
    zip_path = os.path.join(temp_dir, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in sorted(os.listdir(temp_dir)):
            if file.endswith(".jpeg"):
                zipf.write(os.path.join(temp_dir, file), arcname=file)

    return zip_path, page_count, zip_name


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        skip_start = int(request.form.get("skip_start", 0))
        skip_end = int(request.form.get("skip_end", 0))
        uploaded_files = request.files.getlist("pdfs")

        output_files = []

        for file in uploaded_files:
            if file and file.filename.endswith(".pdf"):
                pdf_original_name = file.filename  # ✅ Keep original filename
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                    file.save(temp_pdf.name)
                    zip_path, count, zip_name = convert_pdf(
                        temp_pdf.name, pdf_original_name, skip_start, skip_end
                    )
                    if zip_path:
                        output_files.append((zip_name, zip_path, count))

        # --- Handle output ---
        if len(output_files) == 1:
            # Single file → Download directly with correct name
            zip_name, zip_path, _ = output_files[0]
            return send_file(
                zip_path,
                as_attachment=True,
                download_name=zip_name,  # ✅ ensures correct name
            )
        else:
            # Multiple files → bundle into one master zip
            combined_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            with zipfile.ZipFile(combined_zip.name, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, path, _ in output_files:
                    zf.write(path, arcname=name)

            return send_file(
                combined_zip.name,
                as_attachment=True,
                download_name="all_converted.zip",
            )

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
