"""Package-specific exceptions."""


class ExoPyError(Exception):
    """Base exception for ExoPy failures."""


class DaceClientError(ExoPyError):
    """Raised when a DACE query or download cannot be completed."""


class StorageError(ExoPyError):
    """Raised when local cache or HDF5 storage operations fail."""


class ObservationLoadError(ExoPyError):
    """Raised when an observation cannot be loaded from a FITS/HDF5 source."""
