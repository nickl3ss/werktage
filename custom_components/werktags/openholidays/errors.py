"""Errors raised by the OpenHolidays client."""


class OpenHolidaysError(Exception):
    """Base class of every error of this library."""


class RequestFailed(OpenHolidaysError):
    """The API could not be reached or answered with an error status."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class InvalidResponse(OpenHolidaysError):
    """The API answered, but not with the expected JSON structure."""
