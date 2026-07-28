"""Deterministic identifiers derived from durable agent runs."""


def message_id_for_run(run_id: str) -> str:
    """Return the deterministic assistant message ID for a durable run."""
    normalized_run_id = "".join(
        character for character in run_id if character.isalnum()
    )
    if not normalized_run_id:
        raise ValueError("run_id must contain at least one alphanumeric character")
    return f"msg_run_{normalized_run_id}"
