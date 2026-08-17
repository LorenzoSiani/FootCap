"""Private fallback boundary for unexpected psycopg failures."""

from typing import NoReturn

import psycopg

from ..errors import RepositoryError, RepositoryOperationError

_SAFE_OPERATION_FAILURE_MESSAGE = "repository persistence operation failed"


def _raise_repository_error(exc: BaseException) -> NoReturn:
    """Preserve repository errors and safely translate psycopg failures.

    Operation-specific code must classify known semantic constraints before
    reaching this fallback. Unknown exceptions are re-raised unchanged so
    programming errors are not mislabeled as database failures.
    """
    if isinstance(exc, RepositoryError):
        raise exc
    if isinstance(exc, psycopg.Error):
        raise RepositoryOperationError(_SAFE_OPERATION_FAILURE_MESSAGE) from exc
    raise exc
