"""Connection ownership type used by future PostgreSQL repositories."""

from collections.abc import Callable
from typing import TypeAlias

import psycopg

# Each call supplies a fresh connection whose lifecycle and transaction are
# owned entirely by the repository operation that requested it. This is not a
# pool, UnitOfWork, or caller-visible transaction manager.
ConnectionFactory: TypeAlias = Callable[[], psycopg.Connection]
