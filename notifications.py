from typing import Optional


def build_user_removed_notification(
    user_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> str:
    """Build a private admin notice for a member leaving or being removed."""
    name_parts = [part.strip() for part in (first_name, last_name) if part and part.strip()]
    display_name = " ".join(name_parts)

    clean_username = (username or "").strip().lstrip("@")
    if clean_username:
        display_name = f"{display_name} (@{clean_username})" if display_name else f"@{clean_username}"
    if not display_name:
        display_name = f"Пользователь {user_id}"

    if admin_id is None:
        headline = "👋 Участник самостоятельно покинул группу"
    else:
        headline = f"🚫 Участник удалён администратором (ID {admin_id})"

    return f"{headline}\nИмя: {display_name}\nID пользователя: {user_id}"
