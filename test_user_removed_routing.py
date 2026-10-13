import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["MAX_BOT_TOKEN"] = "test-token"
os.environ["ADMIN_ID"] = "100"
os.environ["GROUP_ID"] = "200"
os.environ["LEAVE_NOTIFY_CHANNEL_ID"] = "-80062952228285"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"

import bot as bot_module


class UserRemovedRoutingTests(unittest.IsolatedAsyncioTestCase):
    def make_event(self):
        return SimpleNamespace(
            chat_id=-200,
            is_channel=True,
            user=SimpleNamespace(
                user_id=273271550,
                first_name="Анна",
                last_name="Тестова",
                username="anna",
            ),
            admin_id=None,
        )

    async def test_sends_contact_card_only_to_channel(self):
        sender = AsyncMock(return_value=None)

        with patch.object(bot_module.bot, "send_message", sender):
            await bot_module.handle_user_removed(self.make_event())

        self.assertEqual(sender.await_count, 1)
        channel_call = sender.await_args_list[0]
        self.assertEqual(channel_call.kwargs["chat_id"], -80062952228285)
        self.assertNotIn("user_id", channel_call.kwargs)
        contact_card = channel_call.kwargs["attachments"][0].model_dump()
        self.assertEqual(contact_card["payload"]["contact_id"], 273271550)

    async def test_channel_send_failure_is_logged_without_admin_fallback(self):
        sender = AsyncMock(side_effect=RuntimeError("forbidden"))

        with patch.object(bot_module.bot, "send_message", sender):
            await bot_module.handle_user_removed(self.make_event())

        self.assertEqual(sender.await_count, 1)
        self.assertNotIn("user_id", sender.await_args.kwargs)


if __name__ == "__main__":
    unittest.main()
