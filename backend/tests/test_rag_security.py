import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
import os
import json
from backend.app.main import app
from backend.security.dependencies import get_current_user
from backend.rag.pipeline import AegisRagService

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

class TestRagSecurity(unittest.TestCase):
    """Thorough multi-tenant security verification tests for RAG information boundaries."""

    def setUp(self):
        self.client = TestClient(app)
        
        # Two distinct normal users
        self.user_a = MockUser({"id": 10, "username": "usera", "role": "user"})
        self.user_b = MockUser({"id": 11, "username": "userb", "role": "user"})
        
        # One admin
        self.admin = MockUser({"id": 100, "username": "admin", "role": "admin"})

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("backend.app.main.rag_service")
    def test_document_listing_isolation(self, mock_rag):
        """Verify standard users see only their own files, while admins see all."""
        mock_rag.list_documents.return_value = [
            {"document_id": "a1", "filename": "docA.pdf", "source_path": "/p1", "ingested_at": 100, "owner_id": 10},
            {"document_id": "b1", "filename": "docB.pdf", "source_path": "/p2", "ingested_at": 100, "owner_id": 11},
            {"document_id": "legacy1", "filename": "legacy.pdf", "source_path": "/p3", "ingested_at": 100, "owner_id": -1}
        ]

        # 1. User A Listing (Should only see docA)
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        resp_a = self.client.get("/documents")
        self.assertEqual(resp_a.status_code, 200)
        list_a = resp_a.json()
        self.assertEqual(len(list_a), 1)
        self.assertEqual(list_a[0]["id"], "a1")
        self.assertEqual(list_a[0]["filename"], "docA.pdf")

        # 2. User B Listing (Should only see docB)
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        resp_b = self.client.get("/documents")
        self.assertEqual(resp_b.status_code, 200)
        list_b = resp_b.json()
        self.assertEqual(len(list_b), 1)
        self.assertEqual(list_b[0]["id"], "b1")
        self.assertEqual(list_b[0]["filename"], "docB.pdf")

        # 3. Admin Listing (Should see all including legacy)
        app.dependency_overrides[get_current_user] = lambda: self.admin
        resp_admin = self.client.get("/documents")
        self.assertEqual(resp_admin.status_code, 200)
        list_admin = resp_admin.json()
        self.assertEqual(len(list_admin), 3)

    @patch("backend.app.main.rag_service")
    def test_unauthorized_deletion_prevented(self, mock_rag):
        """Verify User B cannot delete User A's document."""
        mock_rag.list_documents.return_value = [
            {"document_id": "a1", "filename": "docA.pdf", "source_path": "/p1", "ingested_at": 100, "owner_id": 10}
        ]
        
        # User B attempts to delete A's document -> 403 Forbidden
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        response = self.client.delete("/documents/a1")
        self.assertEqual(response.status_code, 403)
        mock_rag.delete_document.assert_not_called()

        # User A attempts to delete own document -> 200 OK
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        response = self.client.delete("/documents/a1")
        self.assertEqual(response.status_code, 200)
        mock_rag.delete_document.assert_called_once_with("a1")

    @patch("backend.app.main.rag_service")
    @patch("os.path.exists")
    def test_unauthorized_reindexing_prevented(self, mock_exists, mock_rag):
        """Verify User B cannot reindex User A's document."""
        mock_rag.list_documents.return_value = [
            {"document_id": "a1", "filename": "docA.pdf", "source_path": "/p1", "ingested_at": 100, "owner_id": 10}
        ]
        mock_exists.return_value = True

        # User B attempts to reindex A's document -> 403
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        response = self.client.post("/documents/a1/index")
        self.assertEqual(response.status_code, 403)

        # User A attempts to reindex own document -> 200
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        response = self.client.post("/documents/a1/index")
        self.assertEqual(response.status_code, 200)

    @patch("backend.app.main.agent_controller")
    def test_chat_retrieval_flow_boundary(self, mock_controller):
        """Verify user context is successfully propagated into agent run."""
        app.dependency_overrides[get_current_user] = lambda: self.user_a
        mock_controller.run = AsyncMock(return_value={"success": True, "duration_ms": 10, "plan": {"final_output": "ok", "steps": []}})

        response = self.client.post("/chat", json={"message": "hello context"})
        self.assertEqual(response.status_code, 200)
        # Ensure agent_controller was called with current_user matching user_a
        mock_controller.run.assert_called_once()
        args, kwargs = mock_controller.run.call_args
        self.assertEqual(kwargs["current_user"]["id"], 10)

    @patch("backend.rag.pipeline.chromadb.PersistentClient")
    def test_rag_service_search_filters_by_owner(self, mock_chroma):
        """Verify vector search executes metadata filter matches and blocks ownerless legacy blocks."""
        # Setup mock collection
        mock_collection = MagicMock()
        mock_client = mock_chroma.return_value
        mock_client.get_or_create_collection.return_value = mock_collection
        
        # Initialize service targeting mock ChromaDB collection
        mock_embedding_model = MagicMock()
        service = AegisRagService(embedding_model=mock_embedding_model)

        # 1. Search with filter: owner_id = 10 (User A)
        service.search("query", filter_metadata={"owner_id": 10})
        mock_collection.query.assert_called_with(
            query_texts=["query"],
            n_results=3,
            where={"owner_id": 10}
        )

        # 2. Search without filter (Admin or Legacy Test)
        service.search("query", filter_metadata=None)
        mock_collection.query.assert_called_with(
            query_texts=["query"],
            n_results=3,
            where=None
        )

    @patch("backend.security.audit.AuditLogger.log_event")
    def test_unauthorized_audit_details_are_safe(self, mock_log):
        """Verify audit logger does not contain confidential contents, secrets, or passwords."""
        app.dependency_overrides[get_current_user] = lambda: self.user_b
        
        with patch("backend.app.main.rag_service") as mock_rag:
            mock_rag.list_documents.return_value = [
                {"document_id": "a1", "filename": "docA.pdf", "source_path": "/p1", "ingested_at": 100, "owner_id": 10}
            ]
            self.client.delete("/documents/a1")
            
        # Verify the logged event matches DOCUMENT_ACCESS_DENIED or ADMIN_OPERATION with safe metadata
        mock_log.assert_called_once()
        args, kwargs = mock_log.call_args
        
        # Check action parameter
        self.assertEqual(kwargs["action"], "DOCUMENT_ACCESS_DENIED")
        
        # Check metadata details do not leak content or tokens
        meta = kwargs["metadata"]
        self.assertEqual(meta["owner_id"], 10)
        self.assertEqual(meta["attempted_by"], 11)
        self.assertEqual(meta["operation"], "delete")
        self.assertNotIn("password", meta)
        self.assertNotIn("token", meta)
        self.assertNotIn("secret", meta)

if __name__ == "__main__":
    unittest.main()
