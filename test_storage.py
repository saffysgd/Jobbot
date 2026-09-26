import unittest
from unittest.mock import MagicMock, patch

from storage import JobStore


class JobStoreTests(unittest.TestCase):
    def test_database_url_is_required(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
                JobStore()

    @patch("storage.psycopg.connect")
    def test_initialize_creates_jobs_table(self, connect):
        store = JobStore("postgresql://example")
        store.initialize()

        connection = connect.return_value.__enter__.return_value
        query = connection.execute.call_args.args[0]
        self.assertIn("CREATE TABLE IF NOT EXISTS jobs", query)
        self.assertIn("JSONB", query)

    @patch("storage.psycopg.connect")
    def test_save_uses_upsert_and_jsonb(self, connect):
        store = JobStore("postgresql://example")
        job = {
            "status": "active",
            "text": "Новая заявка",
            "admin_msg_ids": {"42": "admin-message-456"},
        }

        store.save("group-message-123", job)

        connection = connect.return_value.__enter__.return_value
        query, parameters = connection.execute.call_args.args
        self.assertIn("ON CONFLICT (message_id) DO UPDATE", query)
        self.assertEqual(parameters[:3], ("group-message-123", "active", "Новая заявка"))
        self.assertEqual(parameters[3].obj, {"42": "admin-message-456"})

    @patch("storage.psycopg.connect")
    def test_get_returns_job_from_postgres(self, connect):
        connection = connect.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = (
            "active",
            "Новая заявка",
            {"42": "admin-message-456"},
        )
        store = JobStore("postgresql://example")

        job = store.get("group-message-123")

        self.assertEqual(
            job,
            {
                "status": "active",
                "text": "Новая заявка",
                "admin_msg_ids": {"42": "admin-message-456"},
            },
        )


if __name__ == "__main__":
    unittest.main()