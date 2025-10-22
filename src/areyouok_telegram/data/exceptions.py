class BaseDataError(Exception):
    """Base class for all data-related exceptions."""


class InvalidIDArgumentError(ValueError, BaseDataError):
    """Raised when an ID argument is invalid or improperly formatted."""

    def __init__(self, id_arguments: list[str]):
        super().__init__(f"Provide exactly one of: {', '.join(id_arguments)}")
        self.id_arguments = id_arguments
