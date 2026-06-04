"""WebSocket heartbeat/ping mechanism."""
from datetime import datetime
import json


def create_heartbeat_message() -> dict:
    """
    Create heartbeat (ping) message to keep connection alive.

    Returns:
        Message dict: {'type': 'ping', 'timestamp': ISO8601_string}

    Sent periodically (every 30s) to:
    - Detect stale connections
    - Prevent proxy timeout cutoffs
    - Ensure bidirectional communication
    """
    return {
        'type': 'ping',
        'timestamp': datetime.now().isoformat(),
    }


def create_heartbeat_response() -> dict:
    """
    Create heartbeat response (pong) from client.

    Returns:
        Message dict: {'type': 'pong', 'timestamp': ISO8601_string}

    Client responds to ping with pong to prove connection alive.
    """
    return {
        'type': 'pong',
        'timestamp': datetime.now().isoformat(),
    }
