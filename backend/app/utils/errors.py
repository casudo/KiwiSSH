"""Error utilities for consistent error messages across the application."""

### How many exceptions of a cause chain are looked at
MAX_CAUSE_DEPTH = 5


def describe_exception(ex: BaseException) -> str:
    """Return the actual cause of an exception.

    The cause often holds the detail that is missing in the message itself,
    e.g. "Command failed: show running-config: Timed out waiting for prompt".

    Use this instead of str(ex) for messages that are stored or returned to the user.
    """
    messages: list[str] = []
    current: BaseException | None = ex
    for _ in range(MAX_CAUSE_DEPTH):
        if current is None:
            break
        message = str(current).strip()
        ### Skip a cause that is already part of a message, e.g. raise ValueError(f"Commits not found: {ex}") from ex
        if message and not any(message in known for known in messages):
            messages.append(message)
        current = current.__cause__
    return ": ".join(messages) or ex.__class__.__name__
