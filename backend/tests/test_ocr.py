import os
import unittest
import shutil
import tempfile
from unittest.mock import patch
from PIL import Image, ImageDraw
import fitz  # PyMuPDF
from backend.multimodal.ocr import LocalPytesseractOCR, OCREngineError

class TestAegisOcrPipeline(unittest.TestCase):
    """Unit tests for offline Tesseract-OCR wrapper and temporary document image rendering."""
    
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.safe_dir = os.path.join(cls.temp_dir, "safe")
        cls.unsafe_dir = os.path.join(cls.temp_dir, "unsafe")
        os.makedirs(cls.safe_dir, exist_ok=True)
        os.makedirs(cls.unsafe_dir, exist_ok=True)
        
        # Test paths
        cls.test_img = os.path.join(cls.safe_dir, "test_print.png")
        cls.test_pdf = os.path.join(cls.safe_dir, "test_scanned.pdf")
        cls.unsafe_file = os.path.join(cls.unsafe_dir, "secrets.txt")
        
        # 1. Create synthetic test image with text using Pillow
        img = Image.new("RGB", (200, 50), color="white")
        d = ImageDraw.Draw(img)
        d.text((10, 10), "AEGIS OCR OK", fill="black")
        img.save(cls.test_img)
        
        # 2. Create synthetic scanned PDF using PyMuPDF (fitz)
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        page.draw_rect([10, 10, 100, 100], color=(0, 0, 0))
        doc.save(cls.test_pdf)
        doc.close()
        
        # 3. Create dummy file outside safe zone
        with open(cls.unsafe_file, "w") as f:
            f.write("confidential data")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_dir):
            try:
                shutil.rmtree(cls.temp_dir)
            except Exception:
                pass

    def setUp(self):
        self.ocr = LocalPytesseractOCR(safe_directories=[self.safe_dir])

    def test_ocr_initialization(self):
        """1. Verify OCR engine initializes with safety directories."""
        self.assertIsNotNone(self.ocr)
        self.assertEqual(len(self.ocr.safe_directories), 1)

    @patch("pytesseract.get_tesseract_version")
    def test_ocr_is_available_true(self, mock_ver):
        """Verify is_available returns True when tesseract is found on system path."""
        mock_ver.return_value = "4.0.0"
        self.assertTrue(self.ocr.is_available())

    @patch("pytesseract.get_tesseract_version")
    def test_ocr_is_available_false(self, mock_ver):
        """Verify is_available returns False when version check fails."""
        mock_ver.side_effect = Exception("tesseract executable not found")
        self.assertFalse(self.ocr.is_available())

    @patch("pytesseract.get_tesseract_version")
    def test_engine_unavailable_raises_error(self, mock_ver):
        """10. Verify OCREngineError is thrown when engine is unreachable."""
        mock_ver.side_effect = Exception("tesseract not found")
        with self.assertRaises(OCREngineError):
            self.ocr.ocr_image(self.test_img)
            
        with self.assertRaises(OCREngineError):
            self.ocr.ocr_pdf(self.test_pdf)

    @patch("pytesseract.get_tesseract_version")
    @patch("pytesseract.image_to_string")
    def test_ocr_image_printed_text(self, mock_to_string, mock_ver):
        """2. Verify printed image text extraction resolves correctly."""
        mock_ver.return_value = "4.0.0"
        mock_to_string.return_value = "AEGIS OCR OK"
        
        text = self.ocr.ocr_image(self.test_img)
        self.assertEqual(text, "AEGIS OCR OK")

    @patch("pytesseract.get_tesseract_version")
    @patch("pytesseract.image_to_string")
    def test_ocr_pdf_scanned_multipage(self, mock_to_string, mock_ver):
        """3, 4, 9, 12. Verify multi-page rendering, page numbering, space normalization, and temp folder cleanup."""
        mock_ver.return_value = "4.0.0"
        mock_to_string.return_value = "   Refinery   turnaround   rules   \n  check pressure \t twice  "
        
        # Track temporary directory creation and cleanup
        original_mkdtemp = tempfile.mkdtemp
        temp_dirs = []
        
        def spy_mkdtemp(*args, **kwargs):
            folder = original_mkdtemp(*args, **kwargs)
            temp_dirs.append(folder)
            return folder
            
        with patch("tempfile.mkdtemp", side_effect=spy_mkdtemp):
            res = self.ocr.ocr_pdf(self.test_pdf)
            
        self.assertEqual(res["document"], "test_scanned.pdf")
        self.assertEqual(len(res["pages"]), 1)
        self.assertEqual(res["pages"][0]["page_number"], 1)
        # Assert spaces/tabs/newlines were normalized correctly
        self.assertEqual(res["pages"][0]["text"], "Refinery turnaround rules check pressure twice")
        
        # Assert temp folder was created and deleted
        self.assertEqual(len(temp_dirs), 1)
        self.assertFalse(os.path.exists(temp_dirs[0]), "Render workspace folders must be deleted after run.")

    @patch("pytesseract.get_tesseract_version")
    def test_ocr_invalid_pdf(self, mock_ver):
        """6. Verify invalid PDF structure raises OCREngineError."""
        mock_ver.return_value = "4.0.0"
        corrupted_pdf = os.path.join(self.safe_dir, "corrupted.pdf")
        with open(corrupted_pdf, "wb") as f:
            f.write(b"%PDF-invalid-bytes")
            
        with self.assertRaises(OCREngineError):
            self.ocr.ocr_pdf(corrupted_pdf)

    def test_ocr_missing_file(self):
        """7. Verify missing files raise FileNotFoundError."""
        missing = os.path.join(self.safe_dir, "missing.png")
        with self.assertRaises(FileNotFoundError):
            self.ocr.ocr_image(missing)

    def test_ocr_unsafe_path_traversal(self):
        """8. Verify path traversal attempts outside safe directories raise PermissionError."""
        with self.assertRaises(PermissionError):
            self.ocr.ocr_image(self.unsafe_file)
            
        with self.assertRaises(PermissionError):
            self.ocr.ocr_pdf(self.unsafe_file)

if __name__ == "__main__":
    unittest.main()
