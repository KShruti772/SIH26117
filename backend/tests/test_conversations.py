import unittest
import os
import tempfile
import sqlite3
from backend.security import database
from backend.agents.conversations import ConversationManager

class TestConversationManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_aegis.db")
        database.settings.AUTH_DB_PATH = self.db_path
        database.init_db()

    def test_create_and_get_conversation(self):
        conv = ConversationManager.create_conversation(title="Test Policy Query")
        self.assertIsNotNone(conv["id"])
        self.assertEqual(conv["title"], "Test Policy Query")

        fetched = ConversationManager.get_conversation(conv["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["title"], "Test Policy Query")
        self.assertEqual(len(fetched["messages"]), 0)

    def test_add_messages_to_conversation(self):
        conv = ConversationManager.create_conversation(title="Python Code Session")
        sid = conv["id"]

        user_msg = ConversationManager.add_message(
            session_id=sid,
            role="user",
            content="Write python code to reverse a string"
        )
        self.assertEqual(user_msg["role"], "user")

        asst_msg = ConversationManager.add_message(
            session_id=sid,
            role="assistant",
            content="def reverse_string(s):\n    return s[::-1]",
            rag_used=False,
            model_id="gemma3:4b",
            verification="UNVERIFIED"
        )
        self.assertEqual(asst_msg["model_id"], "gemma3:4b")

        fetched = ConversationManager.get_conversation(sid)
        self.assertEqual(len(fetched["messages"]), 2)
        self.assertEqual(fetched["messages"][0]["role"], "user")
        self.assertEqual(fetched["messages"][1]["role"], "assistant")
        self.assertFalse(fetched["messages"][1]["rag_used"])

    def test_list_and_delete_conversations(self):
        conv1 = ConversationManager.create_conversation(title="Session 1")
        conv2 = ConversationManager.create_conversation(title="Session 2")

        lst = ConversationManager.list_conversations()
        self.assertGreaterEqual(len(lst), 2)

        deleted = ConversationManager.delete_conversation(conv1["id"])
        self.assertTrue(deleted)

        fetched = ConversationManager.get_conversation(conv1["id"])
        self.assertIsNone(fetched)

if __name__ == "__main__":
    unittest.main()
