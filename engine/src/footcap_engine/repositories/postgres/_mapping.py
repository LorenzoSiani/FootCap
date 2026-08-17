"""PostgreSQL provider identity mapping repository (ADR-012/ADR-015)."""
from __future__ import annotations

from psycopg import sql

from ...domain.identity import (
    ProviderEntityRef,
    ProviderIdentityMapping,
    UnresolvedProviderIdentityError,
)
from ..errors import ProviderMappingConflictError, ReferencedEntityNotFoundError
from ._connection import ConnectionFactory
from ._errors import _raise_repository_error
from ._targets import _resolve_target

_SELECT_MAPPING = (
    "SELECT footcap_entity_id FROM public.provider_identity_mappings "
    "WHERE provider = %s AND entity_type = %s AND provider_entity_id = %s"
)
_INSERT_MAPPING = (
    "INSERT INTO public.provider_identity_mappings "
    "(provider, entity_type, provider_entity_id, footcap_entity_id) "
    "VALUES (%s, %s, %s, %s) "
    "ON CONFLICT (provider, entity_type, provider_entity_id) DO NOTHING "
    "RETURNING footcap_entity_id"
)


class PostgresProviderIdentityMappingRepository:
    """Exact provider-reference lookup and validated mapping insertion."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def resolve(self, provider_ref: ProviderEntityRef) -> str:
        result = self.lookup(provider_ref)
        if result is None:
            raise UnresolvedProviderIdentityError(provider_ref)
        return result

    def lookup(self, provider_ref: ProviderEntityRef) -> str | None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    _SELECT_MAPPING,
                    (provider_ref.provider, provider_ref.entity_type, provider_ref.provider_entity_id),
                )
                row = cur.fetchone()
            connection.commit()
        except Exception as exc:
            connection.rollback()
            _raise_repository_error(exc)
        finally:
            connection.close()
        return None if row is None else row[0]

    def add_mapping(self, mapping: ProviderIdentityMapping) -> None:
        # Resolve before opening a connection so fixture fails before any write.
        target = _resolve_target(mapping.provider_ref.entity_type)
        connection = self._connection_factory()
        try:
            with connection.cursor() as cur:
                target_query = sql.SQL("SELECT 1 FROM {}.{} WHERE {} = %s").format(
                    sql.Identifier(target.schema),
                    sql.Identifier(target.table),
                    sql.Identifier(target.key_column),
                )
                cur.execute(target_query, (mapping.footcap_entity_id,))
                if cur.fetchone() is None:
                    raise ReferencedEntityNotFoundError(
                        "competition" if mapping.provider_ref.entity_type == "league" else "team",
                        mapping.footcap_entity_id,
                    )

                ref = mapping.provider_ref
                cur.execute(
                    _INSERT_MAPPING,
                    (ref.provider, ref.entity_type, ref.provider_entity_id, mapping.footcap_entity_id),
                )
                inserted = cur.fetchone()
                if inserted is None:
                    cur.execute(
                        _SELECT_MAPPING,
                        (ref.provider, ref.entity_type, ref.provider_entity_id),
                    )
                    existing = cur.fetchone()
                    if existing is None or existing[0] != mapping.footcap_entity_id:
                        raise ProviderMappingConflictError(ref)
            connection.commit()
        except Exception as exc:
            connection.rollback()
            _raise_repository_error(exc)
        finally:
            connection.close()
