import os
import io
import re
import json
import zipfile
import logging
from dataclasses import dataclass
from typing import Optional, Set, Tuple

logger = logging.getLogger("aegis.rag.detector")

@dataclass
class DetectionResult:
    """Represents the server-side detected file type and classification."""
    file_type: str            # e.g., 'pdf', 'docx', 'xlsx', 'csv', 'pptx', 'png', 'jpg', 'python', 'sql'
    category: str             # 'document', 'spreadsheet', 'presentation', 'image', 'code', 'text', 'archive'
    mime_type: str            # e.g., 'application/pdf', 'image/png'
    extension: str            # normalized extension, e.g. '.pdf'
    is_valid: bool            # True if file content matches allowed type signatures
    is_safe: bool             # False if binary executable or dangerous format detected
    error_reason: Optional[str] = None
    extraction_method: str = "native" # 'native', 'ocr', 'tabular', 'slide_parser', 'code_parser'

class FileDetector:
    """
    Robust server-side file type and magic-byte signature detector.
    Protects AEGIS from extension spoofing, binary executable uploads, and format corruption.
    """

    # Binary Magic Byte Signatures
    MAGIC_SIGNATURES = {
        "pdf": b"%PDF-",
        "png": b"\x89PNG\r\n\x1a\n",
        "jpeg": b"\xff\xd8\xff",
        "gif87": b"GIF87a",
        "gif89": b"GIF89a",
        "bmp": b"BM",
        "tiff_le": b"II*\x00",
        "tiff_be": b"MM\x00*",
        "zip": b"PK\x03\x04",
        "zip_empty": b"PK\x05\x06",
        "zip_spanned": b"PK\x07\x08",
        "ole2": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        # Executable signatures (Dangerous)
        "pe_exe": b"MZ",
        "elf": b"\x7fELF",
        "macho_32": b"\xfe\xed\xfa\xce",
        "macho_64": b"\xfe\xed\xfa\xcf",
        "macho_32_rev": b"\xce\xfa\xed\xfe",
        "macho_64_rev": b"\xcf\xfa\xed\xfe",
        "macho_fat": b"\xca\xfe\xba\xbe"
    }

    CODE_EXTENSIONS = {
        ".py": ("python", "text/x-python"),
        ".js": ("javascript", "application/javascript"),
        ".jsx": ("javascript", "application/javascript"),
        ".ts": ("typescript", "application/typescript"),
        ".tsx": ("typescript", "application/typescript"),
        ".java": ("java", "text/x-java-source"),
        ".c": ("c", "text/x-c"),
        ".cpp": ("cpp", "text/x-c++src"),
        ".cc": ("cpp", "text/x-c++src"),
        ".cxx": ("cpp", "text/x-c++src"),
        ".h": ("c_header", "text/x-chdr"),
        ".hpp": ("cpp_header", "text/x-c++hdr"),
        ".cs": ("csharp", "text/plain"),
        ".go": ("go", "text/x-go"),
        ".rs": ("rust", "text/x-rust"),
        ".rb": ("ruby", "text/x-ruby"),
        ".php": ("php", "application/x-httpd-php"),
        ".sh": ("shell", "application/x-sh"),
        ".bash": ("shell", "application/x-sh"),
        ".zsh": ("shell", "application/x-sh"),
        ".sql": ("sql", "application/sql"),
        ".json": ("json", "application/json"),
        ".xml": ("xml", "application/xml"),
        ".yaml": ("yaml", "application/x-yaml"),
        ".yml": ("yaml", "application/x-yaml"),
        ".toml": ("toml", "application/toml"),
        ".ini": ("ini", "text/plain"),
        ".conf": ("config", "text/plain"),
        ".env": ("config", "text/plain")
    }

    TEXT_EXTENSIONS = {
        ".txt": ("txt", "text/plain"),
        ".log": ("log", "text/plain"),
        ".md": ("markdown", "text/markdown"),
        ".markdown": ("markdown", "text/markdown"),
        ".rst": ("rst", "text/x-rst"),
        ".rtf": ("rtf", "application/rtf"),
    }

    TABULAR_EXTENSIONS = {
        ".csv": ("csv", "text/csv"),
        ".tsv": ("tsv", "text/tab-separated-values"),
        ".tab": ("tsv", "text/tab-separated-values"),
        ".xlsx": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ".xlsm": ("xlsx", "application/vnd.ms-excel.sheet.macroEnabled.12"),
        ".xls": ("xls", "application/vnd.ms-excel"),
        ".ods": ("ods", "application/vnd.oasis.opendocument.spreadsheet")
    }

    DOCUMENT_EXTENSIONS = {
        ".pdf": ("pdf", "application/pdf"),
        ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ".doc": ("doc", "application/msword"),
        ".odt": ("odt", "application/vnd.oasis.opendocument.text")
    }

    PRESENTATION_EXTENSIONS = {
        ".pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ".ppt": ("ppt", "application/vnd.ms-powerpoint"),
        ".odp": ("odp", "application/vnd.oasis.opendocument.presentation")
    }

    IMAGE_EXTENSIONS = {
        ".png": ("png", "image/png"),
        ".jpg": ("jpeg", "image/jpeg"),
        ".jpeg": ("jpeg", "image/jpeg"),
        ".webp": ("webp", "image/webp"),
        ".bmp": ("bmp", "image/bmp"),
        ".tif": ("tiff", "image/tiff"),
        ".tiff": ("tiff", "image/tiff"),
        ".gif": ("gif", "image/gif")
    }

    @classmethod
    def detect_from_path(cls, file_path: str, filename_override: Optional[str] = None) -> DetectionResult:
        """Reads file header from disk and performs full magic-byte & content analysis."""
        if not os.path.exists(file_path):
            return DetectionResult(
                file_type="unknown",
                category="unknown",
                mime_type="application/octet-stream",
                extension="",
                is_valid=False,
                is_safe=False,
                error_reason="File not found on disk."
            )

        filename = filename_override or os.path.basename(file_path)
        try:
            with open(file_path, "rb") as f:
                header = f.read(8192)
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
        except Exception as e:
            return DetectionResult(
                file_type="unknown",
                category="unknown",
                mime_type="application/octet-stream",
                extension="",
                is_valid=False,
                is_safe=False,
                error_reason=f"Failed to read file from disk: {e}"
            )

        return cls.detect_from_bytes(header, filename, file_size=file_size, full_path=file_path)

    @classmethod
    def detect_from_bytes(
        cls,
        header: bytes,
        filename: str,
        file_size: Optional[int] = None,
        full_path: Optional[str] = None
    ) -> DetectionResult:
        """
        Validates magic bytes, checks for dangerous executables, inspects container formats,
        and returns a deterministic DetectionResult.
        """
        if not header or len(header) == 0:
            return DetectionResult(
                file_type="empty",
                category="unknown",
                mime_type="application/octet-stream",
                extension=os.path.splitext(filename)[1].lower(),
                is_valid=False,
                is_safe=True,
                error_reason="File is empty (0 bytes)."
            )

        ext = os.path.splitext(filename)[1].lower()

        # 1. Dangerous Executable Extensions & Headers (PE, ELF, Mach-O, Scripts)
        if ext in [".exe", ".dll", ".sys", ".scr", ".com", ".bat", ".cmd", ".vbs", ".bin", ".iso", ".apk", ".msi"]:
            return DetectionResult(
                file_type="executable",
                category="blocked",
                mime_type="application/x-dosexec",
                extension=ext,
                is_valid=False,
                is_safe=False,
                error_reason=f"Dangerous executable format ({ext}) detected and blocked."
            )

        if header.startswith(cls.MAGIC_SIGNATURES["pe_exe"]):
            is_pe = False
            if len(header) >= 0x40:
                e_lfanew = int.from_bytes(header[0x3c:0x40], "little")
                if e_lfanew + 4 <= len(header) and header[e_lfanew:e_lfanew + 4] == b"PE\x00\x00":
                    is_pe = True
            if is_pe or ext in [".exe", ".dll", ".sys", ".scr", ".com"]:
                return DetectionResult(
                    file_type="executable",
                    category="blocked",
                    mime_type="application/x-dosexec",
                    extension=ext,
                    is_valid=False,
                    is_safe=False,
                    error_reason="Dangerous executable format (Windows PE .exe/.dll) detected and blocked."
                )

        if header.startswith(cls.MAGIC_SIGNATURES["elf"]):
            return DetectionResult(
                file_type="executable",
                category="blocked",
                mime_type="application/x-executable",
                extension=ext,
                is_valid=False,
                is_safe=False,
                error_reason="Dangerous executable format (Linux ELF binary) detected and blocked."
            )

        if (header.startswith(cls.MAGIC_SIGNATURES["macho_32"]) or
            header.startswith(cls.MAGIC_SIGNATURES["macho_64"]) or
            header.startswith(cls.MAGIC_SIGNATURES["macho_32_rev"]) or
            header.startswith(cls.MAGIC_SIGNATURES["macho_64_rev"])):
            return DetectionResult(
                file_type="executable",
                category="blocked",
                mime_type="application/x-mach-binary",
                extension=ext,
                is_valid=False,
                is_safe=False,
                error_reason="Dangerous executable format (macOS Mach-O binary) detected and blocked."
            )

        # 2. PDF Magic Byte Check
        if header.startswith(cls.MAGIC_SIGNATURES["pdf"]) or b"%PDF-" in header[:1024]:
            return DetectionResult(
                file_type="pdf",
                category="document",
                mime_type="application/pdf",
                extension=ext or ".pdf",
                is_valid=True,
                is_safe=True,
                extraction_method="native_or_ocr"
            )

        # 3. Image Magic Byte Checks
        if header.startswith(cls.MAGIC_SIGNATURES["png"]):
            return DetectionResult(
                file_type="png",
                category="image",
                mime_type="image/png",
                extension=ext or ".png",
                is_valid=True,
                is_safe=True,
                extraction_method="vision_ocr"
            )

        if header.startswith(cls.MAGIC_SIGNATURES["jpeg"]):
            return DetectionResult(
                file_type="jpeg",
                category="image",
                mime_type="image/jpeg",
                extension=ext or ".jpg",
                is_valid=True,
                is_safe=True,
                extraction_method="vision_ocr"
            )

        if header.startswith(cls.MAGIC_SIGNATURES["gif87"]) or header.startswith(cls.MAGIC_SIGNATURES["gif89"]):
            return DetectionResult(
                file_type="gif",
                category="image",
                mime_type="image/gif",
                extension=ext or ".gif",
                is_valid=True,
                is_safe=True,
                extraction_method="vision_ocr"
            )

        if header.startswith(cls.MAGIC_SIGNATURES["bmp"]):
            return DetectionResult(
                file_type="bmp",
                category="image",
                mime_type="image/bmp",
                extension=ext or ".bmp",
                is_valid=True,
                is_safe=True,
                extraction_method="vision_ocr"
            )

        if header.startswith(cls.MAGIC_SIGNATURES["tiff_le"]) or header.startswith(cls.MAGIC_SIGNATURES["tiff_be"]):
            return DetectionResult(
                file_type="tiff",
                category="image",
                mime_type="image/tiff",
                extension=ext or ".tiff",
                is_valid=True,
                is_safe=True,
                extraction_method="vision_ocr"
            )

        if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
            return DetectionResult(
                file_type="webp",
                category="image",
                mime_type="image/webp",
                extension=ext or ".webp",
                is_valid=True,
                is_safe=True,
                extraction_method="vision_ocr"
            )

        # 4. ZIP-Based Open XML Formats (DOCX, XLSX, PPTX, ODT, ODP, ODS, JAR, ZIP)
        if (header.startswith(cls.MAGIC_SIGNATURES["zip"]) or
            header.startswith(cls.MAGIC_SIGNATURES["zip_empty"]) or
            header.startswith(cls.MAGIC_SIGNATURES["zip_spanned"])):
            
            zip_type, mime, cat, method = cls._inspect_zip_container(full_path, header, ext)
            return DetectionResult(
                file_type=zip_type,
                category=cat,
                mime_type=mime,
                extension=ext or f".{zip_type}",
                is_valid=True,
                is_safe=True,
                extraction_method=method
            )

        # 5. OLE2 Compound File Binary Formats (Legacy DOC, XLS, PPT)
        if header.startswith(cls.MAGIC_SIGNATURES["ole2"]):
            if ext in [".xls", ".xlsm"]:
                return DetectionResult(
                    file_type="xls",
                    category="spreadsheet",
                    mime_type="application/vnd.ms-excel",
                    extension=ext,
                    is_valid=True,
                    is_safe=True,
                    extraction_method="tabular"
                )
            elif ext in [".ppt"]:
                return DetectionResult(
                    file_type="ppt",
                    category="presentation",
                    mime_type="application/vnd.ms-powerpoint",
                    extension=ext,
                    is_valid=True,
                    is_safe=True,
                    extraction_method="slide_parser"
                )
            else:
                return DetectionResult(
                    file_type="doc",
                    category="document",
                    mime_type="application/msword",
                    extension=ext or ".doc",
                    is_valid=True,
                    is_safe=True,
                    extraction_method="native"
                )

        # 6. Text-Based Formats (Code, Tabular CSV/TSV, Markdown, JSON, XML, YAML, TXT)
        text_res = cls._inspect_text_format(header, ext, filename)
        if text_res:
            return text_res

        # 7. Unrecognized Binary Format
        return DetectionResult(
            file_type="unknown",
            category="unknown",
            mime_type="application/octet-stream",
            extension=ext,
            is_valid=False,
            is_safe=True,
            error_reason=f"Unsupported or unrecognized file format for extension '{ext}'."
        )

    @classmethod
    def _inspect_zip_container(
        cls,
        full_path: Optional[str],
        header: bytes,
        ext: str
    ) -> Tuple[str, str, str, str]:
        """Inspects internal ZIP structure to disambiguate docx, xlsx, pptx, odt, odp, zip."""
        file_list: Set[str] = set()
        try:
            if full_path and os.path.exists(full_path):
                with zipfile.ZipFile(full_path, 'r') as zf:
                    file_list = set(zf.namelist())
            else:
                # Read from partial memory stream if complete
                zf = zipfile.ZipFile(io.BytesIO(header), 'r')
                file_list = set(zf.namelist())
        except Exception:
            pass

        # Disambiguate by internal marker paths
        if any(p.startswith("word/") or p == "word/document.xml" for p in file_list) or ext == ".docx":
            return ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "document", "docx_parser")
            
        if any(p.startswith("xl/") or p == "xl/workbook.xml" for p in file_list) or ext in [".xlsx", ".xlsm"]:
            return ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "spreadsheet", "tabular")
            
        if any(p.startswith("ppt/") or p == "ppt/presentation.xml" for p in file_list) or ext == ".pptx":
            return ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "presentation", "slide_parser")

        # OpenDocument Formats
        if ext == ".odt" or any("opendocument.text" in p for p in file_list):
            return ("odt", "application/vnd.oasis.opendocument.text", "document", "native")
        if ext == ".odp" or any("opendocument.presentation" in p for p in file_list):
            return ("odp", "application/vnd.oasis.opendocument.presentation", "presentation", "slide_parser")
        if ext == ".ods" or any("opendocument.spreadsheet" in p for p in file_list):
            return ("ods", "application/vnd.oasis.opendocument.spreadsheet", "spreadsheet", "tabular")

        # Fallback to generic safe zip archive
        return ("zip", "application/zip", "archive", "archive_inspector")

    @classmethod
    def _inspect_text_format(cls, header: bytes, ext: str, filename: str) -> Optional[DetectionResult]:
        """Validates plain text / code / structured data encoding and content heuristics."""
        # Try decoding as utf-8 or latin-1
        text = None
        for enc in ["utf-8", "utf-16", "latin-1"]:
            try:
                text = header.decode(enc)
                break
            except Exception:
                continue

        if text is None:
            return None

        # Check ratio of printable text characters
        non_printable = sum(1 for c in text if ord(c) < 32 and c not in "\r\n\t\b\f")
        if len(text) > 0 and (non_printable / len(text)) > 0.15:
            return None  # Likely raw binary data

        # Check Code Categories
        if ext in cls.CODE_EXTENSIONS:
            file_type, mime = cls.CODE_EXTENSIONS[ext]
            return DetectionResult(
                file_type=file_type,
                category="code",
                mime_type=mime,
                extension=ext,
                is_valid=True,
                is_safe=True,
                extraction_method="code_parser"
            )

        # Check Tabular Text Formats (CSV / TSV)
        if ext in cls.TABULAR_EXTENSIONS:
            file_type, mime = cls.TABULAR_EXTENSIONS[ext]
            return DetectionResult(
                file_type=file_type,
                category="spreadsheet",
                mime_type=mime,
                extension=ext,
                is_valid=True,
                is_safe=True,
                extraction_method="tabular"
            )

        # Check Structured Documents (Markdown, RTF)
        if ext in cls.TEXT_EXTENSIONS:
            file_type, mime = cls.TEXT_EXTENSIONS[ext]
            return DetectionResult(
                file_type=file_type,
                category="text",
                mime_type=mime,
                extension=ext,
                is_valid=True,
                is_safe=True,
                extraction_method="native"
            )

        # Content heuristics if extension is unknown or .txt
        stripped = text.strip()
        if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
            try:
                json.loads(stripped)
                return DetectionResult(
                    file_type="json",
                    category="code",
                    mime_type="application/json",
                    extension=ext or ".json",
                    is_valid=True,
                    is_safe=True,
                    extraction_method="code_parser"
                )
            except Exception:
                pass

        if stripped.startswith("<?xml") or (stripped.startswith("<") and stripped.endswith(">") and "</" in stripped):
            return DetectionResult(
                file_type="xml",
                category="code",
                mime_type="application/xml",
                extension=ext or ".xml",
                is_valid=True,
                is_safe=True,
                extraction_method="code_parser"
            )

        # Default to clean plain text
        return DetectionResult(
            file_type="txt",
            category="text",
            mime_type="text/plain",
            extension=ext or ".txt",
            is_valid=True,
            is_safe=True,
            extraction_method="native"
        )
