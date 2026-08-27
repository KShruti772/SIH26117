import os
import shutil
import tempfile
import logging
from typing import Dict, Any, List, Optional
import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger("aegis.ocr")

class OCREngineError(Exception):
    """Base exception for OCR processing and engine failures."""
    pass

class BaseOCR:
    """Interface class to allow replacement of the OCR engine (e.g. to EasyOCR or vision model)."""
    
    def ocr_image(self, image_path: str) -> str:
        """Runs OCR on a single image file on disk."""
        raise NotImplementedError

    def ocr_pdf(self, file_path: str) -> Dict[str, Any]:
        """Renders all PDF pages as images, performs OCR, and returns structured page contents."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Returns True if the underlying OCR engine binaries are installed and accessible."""
        raise NotImplementedError

class LocalPytesseractOCR(BaseOCR):
    """
    Local OCR engine wrapper using pytesseract (Tesseract OCR CLI).
    
    ---------------------------------------------------------------------------
    SECURITY CONTROLS:
    ---------------------------------------------------------------------------
    1. Input path validation: Enforces that target files are inside safe folders.
    2. Zero code execution: Extracted text is never parsed or run as code.
    3. Temp cleanup: Page image files and temporary folders are deleted in finally blocks.
    4. Confidentially: Extracted document contents are never logged.
    ---------------------------------------------------------------------------
    """
    
    def __init__(self, safe_directories: Optional[List[str]] = None, tesseract_cmd: Optional[str] = None):
        import pytesseract
        self.pytesseract = pytesseract
        
        # Enforce local workspace path boundaries
        self.safe_directories = [os.path.abspath(d) for d in (safe_directories or [os.getcwd()])]
        
        if tesseract_cmd:
            self.pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def is_available(self) -> bool:
        """Checks if the tesseract system command is executable on the path."""
        try:
            self.pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def _validate_safe_path(self, file_path: str) -> str:
        """Enforces safe paths and prevents directory traversal attacks."""
        abs_path = os.path.abspath(file_path)
        is_safe = any(abs_path.startswith(safe_dir) for safe_dir in self.safe_directories)
        if not is_safe:
            raise PermissionError(
                f"Access denied: Target path '{file_path}' lies outside configured safe directories."
            )
        return abs_path

    def ocr_image(self, image_path: str) -> str:
        """Extracts text characters from a single image file using pytesseract."""
        abs_path = self._validate_safe_path(image_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Target image not found: '{image_path}'")
            
        if not self.is_available():
            raise OCREngineError("Local Tesseract-OCR engine is unavailable or not installed on the system path.")

        try:
            with Image.open(abs_path) as img:
                text = self.pytesseract.image_to_string(img)
            return text or ""
        except Exception as e:
            raise OCREngineError(f"Tesseract OCR image extraction failed: {e}")

    def ocr_pdf(self, file_path: str) -> Dict[str, Any]:
        """Renders PDF pages as images, performs OCR on each, and cleans up all temporary files."""
        abs_path = self._validate_safe_path(file_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Target PDF document not found: '{file_path}'")

        if not self.is_available():
            raise OCREngineError("Local Tesseract-OCR engine is unavailable or not installed on the system path.")

        # Create temporary workspace folder inside the validated directory of the target file
        temp_dir = tempfile.mkdtemp(prefix="aegis_ocr_", dir=os.path.dirname(abs_path))
        pages_out = []
        
        try:
            logger.info(f"Initiating PDF OCR render for file: {os.path.basename(abs_path)}")
            doc = fitz.open(abs_path)
            
            for page_idx, page in enumerate(doc):
                # Render high-resolution page pixmap (default zoom level is fast and sufficient for printed text)
                pix = page.get_pixmap(dpi=150)
                img_name = f"page_{page_idx}.png"
                img_path = os.path.join(temp_dir, img_name)
                
                # Save intermediate image
                pix.save(img_path)
                
                # Run OCR
                raw_text = self.ocr_image(img_path)
                
                # Normalize spaces and newlines
                normalized_text = " ".join(raw_text.split())
                
                pages_out.append({
                    "page_number": page_idx + 1,
                    "text": normalized_text
                })
                
        except Exception as e:
            raise OCREngineError(f"PDF OCR render/extraction failed: {e}")
            
        finally:
            # Clean up all rendered page images and temporary folders
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                
        return {
            "document": os.path.basename(abs_path),
            "pages": pages_out
        }
