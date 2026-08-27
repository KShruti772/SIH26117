import os
import sys

# Add backend directory to sys.path to enable absolute imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.tools.document_generators.generators import DocxGenerator, XlsxGenerator, PdfGenerator

def generate_demo():
    # Target outputs/ folder in the workspace root
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "outputs"))
    
    docx_gen = DocxGenerator(output_base_dir=output_dir)
    xlsx_gen = XlsxGenerator(output_base_dir=output_dir)
    pdf_gen = PdfGenerator(output_base_dir=output_dir)
    
    # Formatted content
    mock_content = [
        {"type": "heading", "text": "AEGIS MVP - Approval Note", "level": 1},
        {"type": "paragraph", "text": "This approval note authorizes the implementation of local RAG pipelines for Mangalore Refinery & Petrochemicals Limited."},
        {"type": "heading", "text": "Action Items", "level": 2},
        {"type": "bullet", "text": "Install and verify local model registry configuration"},
        {"type": "bullet", "text": "Deploy CPU-optimized SentenceTransformers embedding model"},
        {"type": "bullet", "text": "Configure SQLite ChromaDB vector persistent storage"},
        {"type": "heading", "text": "Hardware Context", "level": 2},
        {
            "type": "table",
            "headers": ["Parameter", "Target Specification", "Developer Machine Status"],
            "rows": [
                ["CPU", "Intel Core i7-13620H", "Verified (Intel Core i7-13620H)"],
                ["RAM", "16 GB", "Verified (16 GB)"],
                ["GPU", "NVIDIA RTX 4050 (6GB VRAM)", "Intel UHD Graphics (Pending physical switch)"]
            ]
        }
    ]
    
    mock_sheets = [
        {
            "name": "Inspection Summary",
            "headers": ["Equipment ID", "Inspection Type", "Status", "Pressure (PSI)", "Notes"],
            "rows": [
                ["P-101", "Pressure Check", "Normal", 120.5, "No leakage detected"],
                ["V-202", "Valve Check", "Warning", 145.2, "Packing gland needs tightening"],
                ["T-303", "Tank Seal", "Under Repair", 0.0, "Seal replacement in progress"]
            ]
        }
    ]
    
    docx_path = docx_gen.generate_docx("sample_approval_note.docx", "Aegis Project Authorization Note", mock_content)
    xlsx_path = xlsx_gen.generate_xlsx("sample_inspection_report.xlsx", mock_sheets)
    pdf_path = pdf_gen.generate_pdf("sample_report.pdf", "Aegis Operations Audit Report", mock_content)
    
    print(f"Generated DOCX: {docx_path}")
    print(f"Generated XLSX: {xlsx_path}")
    print(f"Generated PDF: {pdf_path}")

if __name__ == "__main__":
    generate_demo()
