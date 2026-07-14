"""
Admin-only API models for system monitoring and health checks.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class DatabaseStats(BaseModel):
    """Statistics for a single MongoDB collection."""

    collection: str = Field(..., description="Collection name")
    document_count: int = Field(..., description="Number of documents")
    size_bytes: int = Field(..., description="Collection size in bytes")
    size_mb: float = Field(..., description="Collection size in megabytes")
    avg_document_size_bytes: int = Field(..., description="Average document size")


class SystemMetrics(BaseModel):
    """Local application health metrics."""

    timestamp: datetime = Field(..., description="Metrics collection timestamp")
    database: list[DatabaseStats] = Field(
        ..., description="Database collection statistics"
    )
    health_status: str = Field(
        ...,
        description="Overall health status",
        pattern="^(healthy|warning|critical|degraded)$",
    )


class HealthResponse(SystemMetrics):
    """Admin health endpoint response (alias for SystemMetrics)."""

    pass
