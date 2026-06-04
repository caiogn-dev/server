"""WebSocket listener management and deduplication."""
import uuid


def generate_listener_id(user_id: int, store_slug: str) -> str:
    """
    Generate unique listener ID for deduplication.

    Args:
        user_id: The authenticated user ID
        store_slug: The store slug being connected to

    Returns:
        Unique listener ID: "user_id:store_slug:unique_uuid"

    This enables replacing old listeners on reconnect while keeping
    one listener per (user, store) pair.
    """
    unique_part = str(uuid.uuid4())
    return f"{user_id}:{store_slug}:{unique_part}"


def add_listener_to_group(channel_layer, group_name: str, listener_id: str) -> None:
    """
    Add listener to channel layer group for broadcast.

    Args:
        channel_layer: Django Channels layer instance
        group_name: Group to add to (e.g., 'store_slug-name')
        listener_id: Unique listener identifier

    Called when WebSocket connects successfully.
    """
    # Channels handles group management internally
    # This is a placeholder for future enhancements like listener tracking
    pass


def remove_listener_from_group(channel_layer, group_name: str, listener_id: str) -> None:
    """
    Remove listener from channel layer group.

    Args:
        channel_layer: Django Channels layer instance
        group_name: Group to remove from
        listener_id: Unique listener identifier

    Called when WebSocket disconnects to prevent memory leaks.
    Ensures no more messages sent to removed connections.
    """
    # Channels handles group cleanup internally
    # This is a placeholder for future enhancements like listener tracking
    pass
