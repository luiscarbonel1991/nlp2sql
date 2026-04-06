"""Adapter that exposes a SchemaRepository as a QueryExecutionPort."""

from __future__ import annotations

from ..ports.query_execution import QueryExecutionPort
from ..ports.schema_repository import SchemaRepositoryPort


class SchemaRepositoryExecutionAdapter(QueryExecutionPort):
    """Execute generated SQL through the active schema repository."""

    def __init__(self, repository: SchemaRepositoryPort):
        self.repository = repository

    async def execute_readonly(
        self,
        sql: str,
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        return await self.repository.execute_query(sql=sql, timeout_seconds=timeout_seconds)
