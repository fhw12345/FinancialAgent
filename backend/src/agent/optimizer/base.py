"""
Base class for Order Optimizer.

Provides initialization and common utilities for order optimization.
"""

from typing import Any

import structlog

from ...database.repositories.message_repository import MessageRepository
from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository

logger = structlog.get_logger()


class OrderOptimizerBase:
    """
    Base class for order optimization and execution.

    Provides initialization and dependency management for the optimizer.
    Subclasses implement specific optimization and execution strategies.
    """

    def __init__(
        self,
        react_agent: Any,
        order_repo: PortfolioOrderRepository,
        message_repo: MessageRepository,
    ):
        """
        Initialize order optimizer.

        Args:
            react_agent: ReAct agent (for potential future use)
            order_repo: Repository for persisting orders
            message_repo: Repository for updating message metadata
        """
        self.react_agent = react_agent
        self.order_repo = order_repo
        self.message_repo = message_repo
