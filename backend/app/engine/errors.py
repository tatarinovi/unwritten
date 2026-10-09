class ActionError(Exception):
    """A player action was rejected. The current transaction must roll back."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
