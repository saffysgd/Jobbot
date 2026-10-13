from typing import Optional


class ContactCardAttachment:
    """Outbound MAX contact-card attachment using the Bot API request schema."""

    def __init__(self, user_id: int, name: str):
        self.user_id = user_id
        self.name = name

    def model_dump(self) -> dict:
        """Return the payload expected by POST /messages."""
        return {
            "type": "contact",
            "payload": {
                "name": self.name,
                "contact_id": self.user_id,
            },
        }


def build_user_contact_attachment(
    user_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
) -> ContactCardAttachment:
    """Build a native MAX contact card for a registered user."""
    name_parts = [
        part.strip()
        for part in (first_name, last_name)
        if part and part.strip()
    ]
    name = " ".join(name_parts)

    if not name:
        clean_username = (username or "").strip().lstrip("@")
        name = f"@{clean_username}" if clean_username else f"Пользователь {user_id}"

    return ContactCardAttachment(user_id=user_id, name=name)


def build_user_removed_notification(
    user_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
    admin_id: Optional[int] = None,
    is_channel: bool = False,
) -> str:
    """Build a private admin notice for a member leaving or being removed."""
    name_parts = [part.strip() for part in (first_name, last_name) if part and part.strip()]
    display_name = " ".join(name_parts)

    clean_username = (username or "").strip().lstrip("@")
    if clean_username:
        display_name = f"{display_name} (@{clean_username})" if display_name else f"@{clean_username}"
    if not display_name:
        display_name = f"Пользователь {user_id}"

    chat_name = "канал" if is_channel else "группу"
    removal_place = "из канала" if is_channel else "из группы"
    if admin_id is None:
        headline = f"👋 Участник самостоятельно покинул {chat_name}"
    else:
        headline = f"🚫 Участник удалён администратором {removal_place} (ID {admin_id})"

    return f"{headline}\nИмя: {display_name}\nID пользователя: {user_id}"
