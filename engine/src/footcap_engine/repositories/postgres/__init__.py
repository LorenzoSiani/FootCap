"""Private PostgreSQL adapter foundation for FootCap repositories.

No concrete repository implementation is provided in this package yet.
Only the connection-factory type is exposed at this adapter boundary.
"""

from ._connection import ConnectionFactory

__all__ = ["ConnectionFactory"]
