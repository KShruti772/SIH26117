import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from io import BytesIO
from backend.app.main import app
from backend.security.dependencies import get_current_user

# Mock user object matching sqlite Row interface/dict
class MockUser:
    def __init__(self, data):
        self.data = data
    def __getitem__(self, key):
        return self.data[key]
    def get(self, key, default=None):
        return self.data.get(key, default)
    def keys(self):
        return self.data.keys()

class TestRagRoutes(unittest.TestCase):
    """Unit tests verifying FastAPI `/documents` routes: validations, auth, and traversal guards."""

    def setUp(self):
        self.client = TestClient(app)
        self.mock_user = MockUser({
            "id": 1,
            "username": "testuser",
            "role": "user",
            "is_active": True
        })

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_unauthenticated_requests_rejected(self):
        """Verify unauthenticated requests return 401 Unauthorized."""
        app.dependency_overrides.clear()
        
        # 1. List docs
        response = self.client.get("/documents")
        self.assertEqual(response.status_code, 401)
        
        # 2. Upload
        response = self.client.post("/documents/upload", files={"file": ("test.txt", b"content")})
        self.assertEqual(response.status_code, 401)
        
        # 3. Delete
        response = self.client.delete("/documents/some-id")
        self.assertEqual(response.status_code, 401)

    def test_upload_empty_file_rejected(self):
        """Verify uploading empty file triggers 400 Bad Request."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        
        response = self.client.post(
            "/documents/upload",
            files={"file": ("empty.txt", b"")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Empty files", response.json()["detail"])

    def test_upload_oversized_file_rejected(self):
        """Verify uploading file > 10MB triggers 400 Bad Request."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        
        # Create a 10MB + 1 byte file stream
        oversized_data = b"x" * (10 * 1024 * 1024 + 1)
        response = self.client.post(
            "/documents/upload",
            files={"file": ("large.txt", oversized_data)}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds maximum limit", response.json()["detail"])

    def test_upload_invalid_extension_rejected(self):
        """Verify uploading unallowed file formats triggers 400 Bad Request."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        
        response = self.client.post(
            "/documents/upload",
            files={"file": ("malicious.exe", b"executable bytes")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file extension", response.json()["detail"])

    @patch("backend.app.main.rag_service")
    def test_upload_filename_traversal_sanitized(self, mock_rag):
        """Verify directory traversal indicators in uploaded filename are regex-sanitized."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        mock_rag.ingest_document.return_value = "ingested-id-123"
        
        # Traverse pattern in filename
        response = self.client.post(
            "/documents/upload",
            files={"file": ("../../escaped_name.txt", b"valid text content")}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "ingested-id-123")
        # Ensure path dots/slashes are sanitized out
        self.assertNotIn("..", data["filename"])
        self.assertNotIn("/", data["filename"])

    @patch("backend.app.main.rag_service")
    def test_successful_list_documents(self, mock_rag):
        """Verify list documents filters out absolute path fields before returning."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        mock_rag.list_documents.return_value = [
            {
                "document_id": "doc-id-abc",
                "filename": "manual.pdf",
                "source_path": "/absolute/server/path/manual.pdf",
                "ingested_at": 1690000000,
                "owner_id": 1
            }
        ]
        
        response = self.client.get("/documents")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "doc-id-abc")
        self.assertEqual(data[0]["filename"], "manual.pdf")
        self.assertEqual(data[0]["status"], "indexed")
        # Ensure source absolute path is completely concealed
        self.assertNotIn("source_path", data[0])

    @patch("backend.app.main.rag_service")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_successful_delete_document(self, mock_remove, mock_exists, mock_rag):
        """Verify deleting document deletes vector and removes file from disk."""
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        mock_rag.list_documents.return_value = [
            {
                "document_id": "doc-to-del",
                "filename": "manual.pdf",
                "source_path": "/safe/folder/manual.pdf",
                "ingested_at": 1690000000,
                "owner_id": 1
            }
        ]
        mock_exists.return_value = True
        
        response = self.client.delete("/documents/doc-to-del")
        self.assertEqual(response.status_code, 200)
        
        mock_rag.delete_document.assert_called_once_with("doc-to-del")
        mock_remove.assert_called_once_with("/safe/folder/manual.pdf")

if __name__ == "__main__":
    unittest.main()
