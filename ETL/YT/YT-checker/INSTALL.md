# Installation Guide

The detector checks all dependencies automatically and tells you exactly what's missing. Just run it!

```bash
python detector_fixed.py "YOUR_URL" 
```

It will immediately show a dependency report like:

```
======================================================================
🔍 DEPENDENCY CHECK
======================================================================

📦 Python Packages:
  ✓ Pillow (required)
  ✓ imagehash (required)
  ✓ numpy (required)
  ✓ opencv-python (required)
  ✓ pytesseract (optional but recommended)

🔧 External Tools:
  ✓ yt-dlp (version: 2026.07.04)
  ✓ ffmpeg (C:\path\to\ffmpeg.exe)

🎯 OCR Support (Tesseract):
  ✓ Tesseract (v5.3.0)

======================================================================
✅ All critical dependencies OK
======================================================================
```

## If Something's Missing

### Python Packages
Install all at once:
```bash
pip install yt-dlp pillow imagehash opencv-python pytesseract numpy
```

Or individually:
```bash
pip install yt-dlp          # Download YouTube streams
pip install pillow          # Image processing
pip install imagehash       # Perceptual hashing
pip install opencv-python   # Computer vision
pip install pytesseract     # OCR interface
pip install numpy           # Numerical computing
```

### FFmpeg (Required)

**Windows (Recommended):**
```powershell
winget install -e --id Gyan.FFmpeg
# Then close and reopen your terminal
ffmpeg -version  # Confirm it works
```

**Windows (Alternative - Manual):**
1. Download from: https://ffmpeg.org/download.html
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to PATH environment variable
4. Restart terminal

**macOS:**
```bash
brew install ffmpeg
ffmpeg -version
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
ffmpeg -version
```

### Tesseract OCR (Optional but Recommended)

**Why install it?**
- Enables clock/timestamp detection in video frames
- Without it: detector still works (frame analysis only)

**Windows:**
1. Download installer: https://github.com/UB-Mannheim/tesseract/wiki
2. Run `.exe` installer (default path is fine)
3. Restart terminal
4. Verify: `tesseract --version`

**macOS:**
```bash
brew install tesseract
tesseract --version
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install tesseract-ocr
tesseract --version
```

## Troubleshooting

### "yt-dlp not found"
```bash
pip install yt-dlp
```

### "ffmpeg not found" (after installing)
- **Windows**: Close all terminal windows and reopen. PATH needs to refresh.
- **macOS/Linux**: Run `hash -r` in terminal to clear command cache

### "Tesseract binary not found"
- The Python package `pytesseract` is installed
- But the **binary executable** isn't installed
- Install Tesseract from the links above (not just pip)

### "opencv-python import error"
```bash
pip uninstall opencv-python
pip install opencv-python
```

### Port already in use / Permission denied
- Try running terminal as Administrator (Windows)
- Or use `python3` instead of `python`

---

## Minimal Install (Frame Analysis Only)

If you only want frame loop detection (no OCR):
```bash
pip install yt-dlp pillow imagehash numpy
# Still need ffmpeg (follow instructions above)
```

This skips pytesseract/Tesseract and clock detection, but detector still works fine.

---

## Full Feature Install

For complete functionality:
```bash
# Python packages
pip install yt-dlp pillow imagehash opencv-python pytesseract numpy

# ffmpeg (system dependency)
# → Follow platform-specific instructions above

# Tesseract OCR (system dependency)
# → Follow platform-specific instructions above
```

Then verify:
```bash
python detector_fixed.py "https://www.youtube.com/watch?v=XXXXX" --duration 5
```

Should see:
```
======================================================================
🔍 DEPENDENCY CHECK
======================================================================

📦 Python Packages:
  ✓ Pillow (required)
  ✓ imagehash (required)
  ✓ numpy (required)
  ✓ opencv-python (required)
  ✓ pytesseract (optional but recommended)

🔧 External Tools:
  ✓ yt-dlp
  ✓ ffmpeg

🎯 OCR Support (Tesseract):
  ✓ Tesseract

======================================================================
✅ All critical dependencies OK
======================================================================
```

Once that shows all ✓, you're ready to analyze streams!
