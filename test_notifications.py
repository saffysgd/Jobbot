import unittest

from notifications import build_user_removed_notification


class UserRemovedNotificationTests(unittest.TestCase):
    def test_voluntary_exit_includes_user_identity(self):
        message = build_user_removed_notification(
            user_id=42,
            first_name="Анна",
            last_name="Петрова",
            username="anna",
        )

        self.assertIn("самостоятельно покинул группу", message)
        self.assertIn("Имя: Анна Петрова (@anna)", message)
        self.assertIn("ID пользователя: 42", message)

    def test_admin_removal_identifies_removing_admin(self):
        message = build_user_removed_notification(
            user_id=51,
            first_name="Иван",
            admin_id=7,
        )

        self.assertIn("удалён администратором из группы (ID 7)", message)
        self.assertIn("Имя: Иван", message)
        self.assertIn("ID пользователя: 51", message)

    def test_channel_exit_is_identified_as_channel(self):
        message = build_user_removed_notification(
            user_id=77,
            first_name="Мария",
            is_channel=True,
        )

        self.assertIn("самостоятельно покинул канал", message)
        self.assertIn("Имя: Мария", message)

    def test_missing_name_falls_back_to_username_or_id(self):
        with_username = build_user_removed_notification(user_id=63, username="member")
        without_name = build_user_removed_notification(user_id=64)

        self.assertIn("Имя: @member", with_username)
        self.assertIn("Имя: Пользователь 64", without_name)


if __name__ == "__main__":
    unittest.main()
