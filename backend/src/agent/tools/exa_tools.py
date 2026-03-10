"""
LangChain tool for web search via Exa API.

Independent data source for the debater agent. Exa provides structured
web search results useful for finding lawsuits, regulatory actions,
analyst reports, and other context that financial APIs miss.
"""

import asyncio
import json

import structlog
from exa_py import Exa
from langchain_core.tools import tool

logger = structlog.get_logger()


def create_exa_tools(api_key: str) -> list:
    """Create Exa web search tools for independent verification.

    Args:
        api_key: Exa API key

    Returns:
        List of LangChain tools
    """
    client = Exa(api_key=api_key)

    @tool
    async def search_web_exa(query: str) -> str:
        """Search the web for financial news, lawsuits, regulatory actions, and analysis.

        Use this to find information that financial data APIs may miss:
        litigation, regulatory filings, analyst opinions, competitive threats.

        Args:
            query: Search query (e.g., "Apple CSAM lawsuit West Virginia AG")

        Returns:
            JSON string with search results including titles, URLs, and content
        """
        try:
            # Exa client is synchronous — run in thread to avoid blocking event loop
            response = await asyncio.to_thread(
                client.search_and_contents,
                query,
                num_results=5,
                text={"max_characters": 500},
                type="auto",
            )

            results = [
                {
                    "title": getattr(r, "title", ""),
                    "url": getattr(r, "url", ""),
                    "snippet": getattr(r, "text", "")[:500],
                }
                for r in response.results[:5]
            ]

            return json.dumps({"source": "exa_web_search", "results": results})
        except Exception as e:
            logger.warning("Exa search failed", query=query, error=str(e))
            return json.dumps({"source": "exa_web_search", "error": str(e)})

    return [search_web_exa]
