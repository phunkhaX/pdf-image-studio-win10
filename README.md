# PDF & Image Studio (Windows 10)

A lightweight, offline Windows 10/11 desktop application for working with PDFs and images.

## Features
- **Merge PDFs**: Combine multiple PDFs in any custom order.
- **Images to PDF**: Merge PNG, JPG, WEBP, BMP, and TIFF images into a single PDF (supports `Fit to Image`, `A4`, `Letter`, `Legal`, margins, and EXIF auto-orientation).
- **Resize Images**: Batch resize by percentage or pixel dimensions (with aspect ratio lock) and convert formats (`JPEG`, `PNG`, `WEBP`).
- **Resize / Compress PDF**:
  - Resize PDF page dimensions (`A4`, `Letter`, `Legal`, `A3`, `A5`, or custom scale `%`) without rasterizing vector text.
  - Compress PDF file size (`Balanced` embedded image optimization, `Lossless` font subsetting/deflate, or `Maximum` rasterization).

## Run Locally on Windows 10
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build Standalone `.exe` Locally
```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile --name PDFImageStudio --collect-all customtkinter main.py
```
The executable will be generated in `dist\PDFImageStudio.exe`.

## License
Note: `PyMuPDF` is licensed under AGPL-3.0 (unless you hold a commercial Artifex license). Ensure your repository's `LICENSE` file matches AGPL-3.0 if distributing binaries.
