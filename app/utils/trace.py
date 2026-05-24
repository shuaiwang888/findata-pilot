import secrets


def generate_trace_id() -> str:
    """Return a 64-character hexadecimal trace id."""
    return secrets.token_hex(32)

