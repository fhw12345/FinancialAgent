"""
Hybrid Deep Agent Architecture Experiment with Dynamic Debate Loop.

This experiment implements the following architecture:
1. Main Deep Agent: Delegates to 3 specialist subagents (Technical, News, Financial)
2. LangGraph Orchestration: Research ↔ Debate cycle with convergence detection

Architecture:
    User_Input → Main_Deep_Agent (Researcher)
                    ├─ Technical_SubAgent (Fibonacci, Stochastic, Price History)
                    ├─ News_SubAgent (News Sentiment, Market Movers)
                    └─ Financial_SubAgent (Company Overview, Cash Flow)
                → Report → Debater_Agent → Critique
                         ↑                    ↓
                         └── (if concerns) ───┘
                              (max 5 rounds or "NO FURTHER CONCERNS")
                → Final_Output

Key Features:
    - Dynamic debate cycling (max 5 rounds)
    - Early exit on "NO FURTHER CONCERNS"
    - Researcher can re-invoke subagents to verify Debater's claims
    - Message accumulation for full debate history

Status: ✅ VERIFIED (2026-01-24)
    - Deep Agents framework works with ChatTongyi/Qwen models
    - Subagent delegation pattern functions correctly
    - LangGraph conditional edges enable debate cycling

Usage:
    cd backend
    python -m src.agent.experiments.exp_hybrid_deep_agent

Environment:
    DASHSCOPE_API_KEY: Required for ChatTongyi (Qwen models)

Future Integration (TODO):
    To use real tools instead of mocks, integrate with:
    - DataManager (from src.services.data_manager) for cached OHLCV data
    - FibonacciAnalyzer (from src.core.analysis.fibonacci) for real Fibonacci analysis
    - StochasticAnalyzer (from src.core.analysis.stochastic_analyzer) for real signals
    - AlphaVantageMarketDataService for live market data
    - create_alpha_vantage_tools() for news, fundamentals, market movers
"""

import operator
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from langchain_community.chat_models import ChatTongyi

# Load environment variables from .env.development
# Try multiple paths for flexibility
env_paths = [
    Path(__file__).parents[3] / ".env.development",  # From src/agent/experiments/
    Path(__file__).parents[4]
    / "backend"
    / ".env.development",  # From backend/src/agent/experiments/
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded environment from {env_path}")
        break
else:
    print(f"⚠️ No .env.development found. Tried: {env_paths}")
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

# Try to import ToolRuntime for context injection (langchain >= 1.2)
try:
    from langchain.tools import ToolRuntime

    RUNTIME_AVAILABLE = True
except ImportError:
    RUNTIME_AVAILABLE = False
    ToolRuntime = None  # type: ignore

# Try to import built-in middleware
try:
    from langchain.agents.middleware import SummarizationMiddleware

    MIDDLEWARE_AVAILABLE = True
except ImportError:
    MIDDLEWARE_AVAILABLE = False
    SummarizationMiddleware = None  # type: ignore

# Configuration for debate loop
MAX_DEBATE_ROUNDS = 5
TERMINATION_SIGNAL = "NO FURTHER CONCERNS"


# =============================================================================
# RUNTIME CONTEXT (Dependency Injection)
# =============================================================================


@dataclass
class AgentContext:
    """
    Runtime context for agent invocations.

    This provides dependency injection for tools and middleware,
    making agents more testable, reusable, and flexible.
    """

    # Session info
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_id: str = "anonymous"

    # Analysis target
    symbol: str = "AAPL"
    analysis_type: str = "investment"  # investment, technical, fundamental

    # Time context (critical for relative date queries)
    current_date: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )
    six_months_ago: str = field(
        default_factory=lambda: (datetime.now() - timedelta(days=180)).strftime(
            "%Y-%m-%d"
        )
    )

    # Configuration
    max_debate_rounds: int = MAX_DEBATE_ROUNDS
    risk_tolerance: str = "moderate"  # conservative, moderate, aggressive

    def __post_init__(self):
        """Generate derived fields after initialization."""
        # Ensure dates are strings
        if isinstance(self.current_date, datetime):
            self.current_date = self.current_date.strftime("%Y-%m-%d")
        if isinstance(self.six_months_ago, datetime):
            self.six_months_ago = self.six_months_ago.strftime("%Y-%m-%d")

    def to_context_file(self) -> str:
        """Generate context file content for Backend filesystem."""
        return f"""# Session Context
Generated: {datetime.now().isoformat()}

## Session Info
- Session ID: {self.session_id}
- User ID: {self.user_id}

## Analysis Target
- Symbol: {self.symbol}
- Analysis Type: {self.analysis_type}
- Risk Tolerance: {self.risk_tolerance}

## Time Context
- Current Date: {self.current_date}
- Analysis Period: {self.six_months_ago} to {self.current_date}

## Configuration
- Max Debate Rounds: {self.max_debate_rounds}
"""


def create_context_files(
    context: AgentContext, verbose: bool = False
) -> dict[str, dict[str, list[str]]]:
    """
    Create initial context files dict for StateBackend.

    These files are passed via invoke(files={...}) when using StateBackend.
    The agent can read these files via the filesystem tools.

    StateBackend expects files in format: {"content": ["line1", "line2", ...]}

    Args:
        context: AgentContext with session info
        verbose: Print detailed info about files being created

    Returns:
        Dict of file paths to FileData dicts ({"content": [lines]})
    """

    # Helper to convert string content to FileData format
    def to_file_data(content: str) -> dict[str, list[str]]:
        """Convert string content to StateBackend FileData format."""
        return {"content": content.split("\n")}

    session_content = context.to_context_file()
    files = {
        "/context/session.md": to_file_data(session_content),
        "/context/symbol.txt": to_file_data(context.symbol),
        "/context/date.txt": to_file_data(context.current_date),
    }

    if verbose:
        print(f"\n{'─'*60}")
        print("📁 CONTEXT FILES CREATED FOR BACKEND")
        print(f"{'─'*60}")
        for path, file_data in files.items():
            content = "\n".join(file_data["content"])
            print(
                f"\n📄 {path} ({len(content)} bytes, {len(file_data['content'])} lines):"
            )
            # Show first 200 chars of content
            preview = content[:200] + "..." if len(content) > 200 else content
            for line in preview.split("\n"):
                print(f"   {line}")
        print(f"{'─'*60}")

    return files


def create_backend_with_context(
    context: AgentContext, use_store: bool = False, verbose: bool = False
):
    """
    Create a Backend factory for deep agents.

    Note: Context files should be passed via invoke(files={...}), not through
    the backend constructor. Use create_context_files() to get the files dict.

    Args:
        context: AgentContext with session info (used for documentation only)
        use_store: Enable persistent memory via StoreBackend
        verbose: Print detailed info about backend creation

    Returns:
        Tuple of (backend_factory, store, initial_files) where initial_files is
        in StateBackend FileData format: {path: {"content": [lines]}}
    """
    initial_files = create_context_files(context, verbose=verbose)

    if use_store and STORE_AVAILABLE:
        # CompositeBackend: ephemeral workspace + persistent memories
        def backend_factory(rt):
            if verbose:
                print(
                    "   🔧 Creating CompositeBackend with StateBackend + StoreBackend"
                )
            state_backend = StateBackend(rt)
            store_backend = StoreBackend(rt)
            return CompositeBackend(
                default=state_backend,
                routes={
                    "/memories/": store_backend,  # Persistent across threads
                },
            )

        if verbose:
            print("\n🏗️ Backend: CompositeBackend (StateBackend + StoreBackend)")
            print("   - /context/* → StateBackend (ephemeral)")
            print("   - /workspace/* → StateBackend (ephemeral)")
            print("   - /memories/* → StoreBackend (persistent)")

        return backend_factory, InMemoryStore(), initial_files
    else:
        # Simple StateBackend (default)
        def backend_factory(rt):
            if verbose:
                print("   🔧 Creating StateBackend (ephemeral)")
            return StateBackend(rt)

        if verbose:
            print("\n🏗️ Backend: StateBackend (ephemeral)")
            print("   - All paths stored in LangGraph state")
            print("   - Files passed via invoke(files={...})")

        return backend_factory, None, initial_files


# Check for deepagents availability
try:
    from deepagents import create_deep_agent
    from deepagents.backends import CompositeBackend, StateBackend

    DEEPAGENTS_AVAILABLE = True
except ImportError:
    DEEPAGENTS_AVAILABLE = False
    StateBackend = None  # type: ignore
    CompositeBackend = None  # type: ignore
    print("⚠️ deepagents not installed. Run: pip install deepagents")

# Try to import StoreBackend for persistent memory (optional)
try:
    from deepagents.backends import StoreBackend
    from langgraph.store.memory import InMemoryStore

    STORE_AVAILABLE = True
except ImportError:
    STORE_AVAILABLE = False
    StoreBackend = None  # type: ignore
    InMemoryStore = None  # type: ignore


# =============================================================================
# CONFIGURATION
# =============================================================================

# Model configuration (using DashScope/Qwen)
# Note: qwen-plus free tier exhausted, using qwen-turbo instead
MODEL_NAME = "qwen-turbo"
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

if not DASHSCOPE_API_KEY:
    print("⚠️ DASHSCOPE_API_KEY not set. Please set it in your environment.")


# =============================================================================
# STEP 1: DEFINE TOOLS FOR EACH DOMAIN (with Runtime Context Support)
# =============================================================================


def create_tools_with_context():
    """
    Create tools that can access runtime context for dynamic data.

    Returns tools that use ToolRuntime[AgentContext] when available,
    falling back to simpler implementations otherwise.
    """

    # --- Technical Analysis Tools ---
    if RUNTIME_AVAILABLE:

        @tool
        def get_stock_price_history(
            symbol: str, days: int = 30, runtime: ToolRuntime[AgentContext] = None  # type: ignore
        ) -> str:
            """
            Retrieves historical price data for technical analysis.

            Args:
                symbol: Stock ticker symbol (e.g., "AAPL", "TSLA")
                days: Number of days of history to retrieve (default: 30)
                runtime: Injected runtime context with session info

            Returns:
                Summary of price action and key levels
            """
            # Access context if available
            ctx_info = ""
            if runtime and runtime.context:
                ctx_info = f"\n- Analysis Date: {runtime.context.current_date}"
                ctx_info += f"\n- Session: {runtime.context.session_id}"

            return f"""Price History for {symbol} (last {days} days):{ctx_info}
- Current Price: $185.50
- 30-day High: $195.20
- 30-day Low: $172.30
- Trend: Upward (higher highs, higher lows)
- Support Level: $175.00
- Resistance Level: $195.00
- Volume: Average 45M shares/day"""

        @tool
        def get_fibonacci_levels(
            symbol: str, runtime: ToolRuntime[AgentContext] = None  # type: ignore
        ) -> str:
            """
            Calculates Fibonacci retracement levels for a stock.

            Args:
                symbol: Stock ticker symbol
                runtime: Injected runtime context

            Returns:
                Fibonacci levels and golden zone analysis
            """
            date_range = ""
            if runtime and runtime.context:
                date_range = f"\n- Period: {runtime.context.six_months_ago} to {runtime.context.current_date}"

            return f"""Fibonacci Analysis for {symbol}:{date_range}
- Detected Trend: Uptrend from $150.00 to $195.00
- 23.6% Level: $184.38
- 38.2% Level: $177.81
- 50.0% Level: $172.50
- 61.8% Level (Golden): $167.19
- Golden Zone: $165.00 - $170.00 (key support area)
- Current Price vs Golden Zone: ABOVE - bullish position"""

        @tool
        def get_stochastic_signals(
            symbol: str, runtime: ToolRuntime[AgentContext] = None  # type: ignore
        ) -> str:
            """
            Gets Stochastic oscillator signals for momentum analysis.

            Args:
                symbol: Stock ticker symbol
                runtime: Injected runtime context

            Returns:
                Stochastic %K, %D values and signal interpretation
            """
            return f"""Stochastic Analysis for {symbol}:
- %K Value: 72.5
- %D Value: 68.3
- Signal: NEUTRAL (not overbought, not oversold)
- Crossover: %K above %D (bullish momentum)
- Zone: Upper neutral (approaching overbought at 80)"""

    else:
        # Fallback: Simple tools without runtime

        @tool
        def get_stock_price_history(symbol: str, days: int = 30) -> str:
            """Retrieves historical price data for technical analysis."""
            return f"""Price History for {symbol} (last {days} days):
- Current Price: $185.50
- 30-day High: $195.20
- 30-day Low: $172.30
- Trend: Upward (higher highs, higher lows)
- Support Level: $175.00
- Resistance Level: $195.00
- Volume: Average 45M shares/day"""

        @tool
        def get_fibonacci_levels(symbol: str) -> str:
            """Calculates Fibonacci retracement levels for a stock."""
            return f"""Fibonacci Analysis for {symbol}:
- Detected Trend: Uptrend from $150.00 to $195.00
- 23.6% Level: $184.38
- 38.2% Level: $177.81
- 50.0% Level: $172.50
- 61.8% Level (Golden): $167.19
- Golden Zone: $165.00 - $170.00 (key support area)
- Current Price vs Golden Zone: ABOVE - bullish position"""

        @tool
        def get_stochastic_signals(symbol: str) -> str:
            """Gets Stochastic oscillator signals for momentum analysis."""
            return f"""Stochastic Analysis for {symbol}:
- %K Value: 72.5
- %D Value: 68.3
- Signal: NEUTRAL (not overbought, not oversold)
- Crossover: %K above %D (bullish momentum)
- Zone: Upper neutral (approaching overbought at 80)"""

    # --- News/Qualitative Tools (same for both modes) ---
    @tool
    def search_stock_news(symbol: str, max_results: int = 5) -> str:
        """
        Searches for recent news about a stock.

        Args:
            symbol: Stock ticker symbol
            max_results: Maximum number of news items to return

        Returns:
            Recent news headlines and sentiment summary
        """
        return f"""Recent News for {symbol}:
1. [Positive] "Strong Q4 earnings beat expectations" - 2 days ago
2. [Neutral] "CEO discusses AI strategy at investor day" - 3 days ago
3. [Positive] "Analyst upgrades to Buy with $220 target" - 5 days ago
4. [Negative] "Supply chain concerns in Asia" - 7 days ago
5. [Neutral] "New product launch scheduled for Q2" - 10 days ago

Overall Sentiment: MODERATELY POSITIVE (3 positive, 2 neutral, 1 negative)"""

    @tool
    def get_market_movers() -> str:
        """
        Gets today's market movers and sector performance.

        Returns:
            Top gainers, losers, and sector performance
        """
        return """Market Overview:
Top Gainers: NVDA (+5.2%), AMD (+3.8%), META (+2.1%)
Top Losers: BA (-2.5%), NKE (-1.8%), DIS (-1.2%)

Sector Performance:
- Technology: +1.8%
- Healthcare: +0.5%
- Financials: +0.3%
- Energy: -0.2%
- Consumer Discretionary: -0.5%

Market Sentiment: RISK-ON (tech leading)"""

    # --- Financial/Fundamental Tools ---
    @tool
    def get_company_overview(symbol: str) -> str:
        """
        Gets company overview and key metrics.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Company description and key financial metrics
        """
        return f"""Company Overview: {symbol}
- Sector: Technology
- Industry: Consumer Electronics
- Market Cap: $2.8T
- P/E Ratio: 28.5
- Forward P/E: 24.2
- PEG Ratio: 1.8
- Dividend Yield: 0.5%
- 52-Week Range: $150.25 - $199.62"""

    @tool
    def get_cash_flow_analysis(symbol: str) -> str:
        """
        Analyzes company cash flow and financial health.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Cash flow metrics and financial health assessment
        """
        return f"""Cash Flow Analysis for {symbol}:
- Operating Cash Flow: $110B (TTM)
- Free Cash Flow: $85B (TTM)
- FCF Margin: 22.5%
- Cash & Equivalents: $65B
- Total Debt: $108B
- Net Debt: $43B
- Debt/EBITDA: 0.8x

Financial Health: STRONG
- Ample cash generation
- Manageable debt levels
- Strong liquidity position"""

    return {
        "technical": [
            get_stock_price_history,
            get_fibonacci_levels,
            get_stochastic_signals,
        ],
        "news": [search_stock_news, get_market_movers],
        "financial": [get_company_overview, get_cash_flow_analysis],
    }


# =============================================================================
# STEP 2: DEFINE SUBAGENTS (SPECIALISTS) - Using Runtime Context
# =============================================================================


def create_subagents(context: AgentContext, tools: dict):
    """
    Create subagent configurations with runtime context injected.

    Args:
        context: AgentContext with session info, dates, symbol
        tools: Dict of tool lists by category (technical, news, financial)

    Returns:
        List of subagent configuration dicts
    """

    # 1. Technical Analyst Subagent
    technical_subagent = {
        "name": "technical_analyst",
        "description": "Specialist in technical analysis, price action, chart patterns, and momentum indicators. Use for price history, Fibonacci levels, and Stochastic signals.",
        "system_prompt": f"""You are a Technical Analyst specialist.

=== SESSION CONTEXT ===
Current Date: {context.current_date}
Analysis Period: {context.six_months_ago} to {context.current_date}
Target Symbol: {context.symbol}
Session ID: {context.session_id}
======================

Your focus is ONLY on:
- Price action and chart patterns
- Support and resistance levels
- Fibonacci retracement analysis
- Momentum indicators (Stochastic, RSI)
- Volume analysis

DO NOT analyze news or fundamentals - that's not your domain.
Provide a concise technical outlook with specific price levels.""",
        "tools": tools["technical"],
    }

    # 2. News/Sentiment Analyst Subagent
    news_subagent = {
        "name": "news_analyst",
        "description": "Specialist in news sentiment, market drivers, and qualitative analysis. Use for recent news and market sentiment.",
        "system_prompt": f"""You are a News & Sentiment Analyst specialist.

=== SESSION CONTEXT ===
Current Date: {context.current_date}
Target Symbol: {context.symbol}
Session ID: {context.session_id}
======================

Your focus is ONLY on:
- Recent news and press releases
- Market sentiment and investor mood
- Sector trends and market movers
- Qualitative factors affecting the stock

DO NOT analyze charts or financials - that's not your domain.
Provide a sentiment summary with key news catalysts.""",
        "tools": tools["news"],
    }

    # 3. Financial/Fundamental Analyst Subagent
    financial_subagent = {
        "name": "financial_analyst",
        "description": "Specialist in fundamental analysis, company financials, and valuation. Use for company overview, cash flow, and earnings analysis.",
        "system_prompt": f"""You are a Fundamental Analyst specialist.

=== SESSION CONTEXT ===
Current Date: {context.current_date}
Target Symbol: {context.symbol}
Risk Tolerance: {context.risk_tolerance}
Session ID: {context.session_id}
======================

Your focus is ONLY on:
- Company financial statements
- Cash flow and earnings quality
- Valuation metrics (P/E, PEG, etc.)
- Balance sheet health
- Competitive position

DO NOT analyze charts or news - that's not your domain.
Provide a fundamental assessment with key valuation insights.""",
        "tools": tools["financial"],
    }

    return [technical_subagent, news_subagent, financial_subagent]


# =============================================================================
# STEP 3: CREATE AGENTS (with Runtime Context Support)
# =============================================================================


def create_model():
    """Create ChatTongyi model for DashScope."""
    return ChatTongyi(
        model=MODEL_NAME,
        dashscope_api_key=DASHSCOPE_API_KEY,
        temperature=0.7,
    )


def create_main_agent(
    context: AgentContext, use_store: bool = False, verbose: bool = False
):
    """
    Create the Main Deep Agent (Manager/Orchestrator) with Backend-based context.

    Args:
        context: AgentContext with session info, dates, symbol
        use_store: Enable persistent memory via StoreBackend
        verbose: Print detailed info about agent creation

    Returns:
        Tuple of (agent, initial_files) where initial_files should be passed via invoke

    Note:
        Context is injected via invoke(files={...}):
        - /context/session.md - Full session context
        - /workspace/* - Ephemeral scratch space
        - /memories/* - Persistent memories (if use_store=True)
    """
    if not DEEPAGENTS_AVAILABLE:
        raise ImportError("deepagents not installed")

    if verbose:
        print(f"\n{'='*60}")
        print("🤖 CREATING MAIN AGENT (Researcher/Orchestrator)")
        print(f"{'='*60}")

    model = create_model()
    if verbose:
        print(f"\n📊 Model: {MODEL_NAME} (ChatTongyi/DashScope)")

    tools = create_tools_with_context()
    if verbose:
        print("\n🔧 Tools created:")
        print(f"   - Technical: {[t.name for t in tools['technical']]}")
        print(f"   - News: {[t.name for t in tools['news']]}")
        print(f"   - Financial: {[t.name for t in tools['financial']]}")

    subagents = create_subagents(context, tools)
    if verbose:
        print("\n👥 Subagents configured:")
        for sa in subagents:
            print(f"   - {sa['name']}: {sa['description'][:60]}...")
            print(f"     Tools: {[t.name for t in sa['tools']]}")

    # Create backend (files will be passed via invoke)
    backend_factory, store, initial_files = create_backend_with_context(
        context, use_store=use_store, verbose=verbose
    )

    # Build system prompt - reference context file instead of hardcoding
    system_prompt = f"""You are a Senior Investment Strategist.

IMPORTANT: Read /context/session.md for full session context including:
- Current date and analysis period
- Target symbol and risk tolerance
- Session and user information

Your goal is to produce a comprehensive investment report for {context.symbol}.

You MUST delegate specific analyses to your specialized subagents:
- technical_analyst: For chart patterns, price levels, momentum signals
- news_analyst: For market sentiment, recent news, catalysts
- financial_analyst: For fundamentals, valuation, cash flow health

WORKFLOW:
1. First, read /context/session.md to understand the session parameters
2. Delegate to all 3 specialists in parallel
3. Gather their reports
4. Synthesize a FINAL INVESTMENT THESIS that combines all perspectives
5. Optionally write key findings to /workspace/report.md

Your final report should include:
- Executive Summary (Bull/Bear/Neutral stance)
- Technical Outlook (key levels, trend)
- Sentiment Assessment (news, catalysts)
- Fundamental View (valuation, financial health)
- Risk Factors
- Recommendation (Buy/Hold/Sell with conviction level)"""

    agent_kwargs: dict[str, Any] = {
        "model": model,
        "system_prompt": system_prompt,
        "subagents": subagents,
        "backend": backend_factory,
    }

    # Add store if using persistent memory
    if store:
        agent_kwargs["store"] = store

    # Add context_schema if supported (langchain >= 1.2)
    if RUNTIME_AVAILABLE:
        agent_kwargs["context_schema"] = AgentContext

    if verbose:
        print("\n⚙️ Agent Configuration:")
        print(f"   - model: {MODEL_NAME}")
        print(f"   - subagents: {len(subagents)}")
        print(f"   - backend: {'CompositeBackend' if store else 'StateBackend'}")
        print(f"   - context_schema: {'AgentContext' if RUNTIME_AVAILABLE else 'None'}")
        print("\n🎯 Built-in Middleware (from deepagents):")
        print("   - TodoListMiddleware: Task planning and tracking")
        print("   - FilesystemMiddleware: Read/write files via Backend")
        print("   - SubAgentMiddleware: Delegate to specialist subagents")
        print("   - SummarizationMiddleware: Auto-summarize long conversations")
        print("   - AnthropicPromptCachingMiddleware: Optimize API usage")
        print("   - PatchToolCallsMiddleware: Fix malformed tool calls")
        print(f"{'='*60}")

    return create_deep_agent(**agent_kwargs), initial_files


def create_debater_agent(
    context: AgentContext, use_store: bool = False, verbose: bool = False
):
    """
    Create the Debater Agent (Adversary/Critic) with Backend-based context.

    Args:
        context: AgentContext with session info, dates, symbol
        use_store: Enable persistent memory via StoreBackend
        verbose: Print detailed info about agent creation

    Returns:
        Tuple of (agent, initial_files) where initial_files should be passed via invoke

    Note:
        Context is injected via invoke(files={...}).
        Debater can read /context/session.md for session parameters.
    """
    if not DEEPAGENTS_AVAILABLE:
        raise ImportError("deepagents not installed")

    if verbose:
        print(f"\n{'='*60}")
        print("⚔️ CREATING DEBATER AGENT (Adversary/Critic)")
        print(f"{'='*60}")

    model = create_model()
    tools = create_tools_with_context()

    if verbose:
        print(f"\n📊 Model: {MODEL_NAME} (ChatTongyi/DashScope)")
        print(f"\n🔧 Tools: {[t.name for t in tools['news']]}")
        print("   (Debater uses news tools to find counter-evidence)")

    # Create backend (files will be passed via invoke)
    backend_factory, store, initial_files = create_backend_with_context(
        context, use_store=use_store, verbose=verbose
    )

    # Build system prompt - reference context file
    system_prompt = f"""You are a Short Seller and Contrarian Debater.

IMPORTANT: Read /context/session.md for session context if needed.
Target Symbol: {context.symbol}

You will receive an investment thesis for {context.symbol}. Your job is to TEAR IT APART.

Your approach:
1. Find holes in the technical analysis
2. Identify negative news or risks not mentioned
3. Challenge valuation assumptions
4. Highlight bear case scenarios
5. Question the conviction level

Be AGGRESSIVE but FAIR in your critique.
Use your tools to search for contradictory evidence.
You can write your findings to /workspace/critique.md if helpful.

Your output should include:
- Key Weaknesses in the Thesis
- Counter-Evidence Found
- Risk Factors Overlooked
- Bear Case Scenario
- Final Verdict: How confident should the investor really be?

IMPORTANT: If you have thoroughly reviewed the thesis and genuinely have no remaining concerns,
respond with exactly: "{TERMINATION_SIGNAL}" to end the debate."""

    agent_kwargs: dict[str, Any] = {
        "model": model,
        "system_prompt": system_prompt,
        "tools": tools["news"],  # Debater uses news tools to find counter-evidence
        "backend": backend_factory,
    }

    # Add store if using persistent memory
    if store:
        agent_kwargs["store"] = store

    # Add context_schema if supported
    if RUNTIME_AVAILABLE:
        agent_kwargs["context_schema"] = AgentContext

    if verbose:
        print("\n⚙️ Agent Configuration:")
        print(f"   - model: {MODEL_NAME}")
        print("   - tools: news (for counter-evidence)")
        print(f"   - backend: {'CompositeBackend' if store else 'StateBackend'}")
        print(f"{'='*60}")

    return create_deep_agent(**agent_kwargs), initial_files


# =============================================================================
# STEP 4: LANGGRAPH ORCHESTRATION (RESEARCH ↔ DEBATE CYCLE)
# =============================================================================

# Verbose mode flag (set by run_experiment)
_verbose_mode = False


class DebateState(TypedDict):
    """State for the debate workflow with message accumulation and context."""

    # Messages accumulate the debate history (Report -> Critique -> Defense -> ...)
    messages: Annotated[list[BaseMessage], operator.add]
    round_count: int
    symbol: str
    # Runtime context (serialized for state passing)
    context_dict: dict[str, Any]


# Global agent instances (created once per experiment run with context)
_main_agent = None
_main_agent_files: dict[str, str] | None = None
_debater_agent = None
_debater_agent_files: dict[str, str] | None = None
_current_context: AgentContext | None = None


def _get_main_agent(context: AgentContext):
    """Get or create the main research agent (singleton per run)."""
    global _main_agent, _main_agent_files, _current_context, _verbose_mode
    if _main_agent is None or _current_context != context:
        _main_agent, _main_agent_files = create_main_agent(
            context, verbose=_verbose_mode
        )
        _current_context = context
    return _main_agent, _main_agent_files


def _get_debater_agent(context: AgentContext):
    """Get or create the debater agent (singleton per run)."""
    global _debater_agent, _debater_agent_files, _current_context, _verbose_mode
    if _debater_agent is None or _current_context != context:
        _debater_agent, _debater_agent_files = create_debater_agent(
            context, verbose=_verbose_mode
        )
        _current_context = context
    return _debater_agent, _debater_agent_files


def _context_from_state(state: DebateState) -> AgentContext:
    """Reconstruct AgentContext from state dict."""
    ctx_dict = state.get("context_dict", {})
    return AgentContext(
        session_id=ctx_dict.get("session_id", str(uuid.uuid4())[:8]),
        user_id=ctx_dict.get("user_id", "anonymous"),
        symbol=ctx_dict.get("symbol", state.get("symbol", "AAPL")),
        current_date=ctx_dict.get("current_date", datetime.now().strftime("%Y-%m-%d")),
        six_months_ago=ctx_dict.get(
            "six_months_ago",
            (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d"),
        ),
        max_debate_rounds=ctx_dict.get("max_debate_rounds", MAX_DEBATE_ROUNDS),
        risk_tolerance=ctx_dict.get("risk_tolerance", "moderate"),
    )


def run_researcher(state: DebateState) -> dict[str, Any]:
    """
    The Main Deep Agent (Researcher) with runtime context.

    First turn: Researches and produces initial report.
    Subsequent turns: Addresses critique and defends/adjusts thesis.
    Can re-invoke subagents to verify Debater's claims.
    """
    global _verbose_mode
    messages = state["messages"]
    current_round = state.get("round_count", 0)
    context = _context_from_state(state)
    symbol = context.symbol

    print(f"\n{'='*60}")
    if current_round == 0:
        print(f"🔍 RESEARCH PHASE (Round {current_round + 1}): Analyzing {symbol}")
        print(f"   Session: {context.session_id} | Date: {context.current_date}")
    else:
        print(
            f"🔄 REBUTTAL PHASE (Round {current_round + 1}): Defending thesis for {symbol}"
        )
    print(f"{'='*60}")

    try:
        main_agent, initial_files = _get_main_agent(context)

        # Build invoke kwargs with context files
        invoke_kwargs: dict[str, Any] = {
            "config": {
                "configurable": {"thread_id": f"research-{symbol}-r{current_round}"}
            },
        }

        # Add context if runtime supports it
        if RUNTIME_AVAILABLE:
            invoke_kwargs["context"] = context

        # Build input with files for StateBackend
        if current_round > 0:
            # Rebuttal: Address the critique, can re-invoke subagents to verify claims
            rebuttal_prompt = HumanMessage(
                content="Review the critique above. Call your sub-agents to verify "
                "the counter-arguments if needed, then provide your rebuttal or updated thesis."
            )
            input_data = {
                "messages": messages + [rebuttal_prompt],
                "files": initial_files,  # Pass context files via invoke
            }
        else:
            # First run: Initial research
            input_data = {
                "messages": messages,
                "files": initial_files,  # Pass context files via invoke
            }

        if _verbose_mode:
            print(f"\n{'─'*60}")
            print("📤 INVOKE MAIN AGENT")
            print(f"{'─'*60}")
            print(f"   thread_id: research-{symbol}-r{current_round}")
            print(f"   messages: {len(input_data['messages'])} messages")
            print(f"   files: {list(initial_files.keys())}")
            if RUNTIME_AVAILABLE:
                print(
                    f"   context: AgentContext(session={context.session_id}, symbol={symbol})"
                )
            print("\n   📨 Input message preview:")
            last_msg = input_data["messages"][-1]
            preview = (
                last_msg.content[:200] + "..."
                if len(last_msg.content) > 200
                else last_msg.content
            )
            print(f'   "{preview}"')
            print("\n   ⏳ Invoking agent (this calls LLM + tools + subagents)...")

        response = main_agent.invoke(input_data, **invoke_kwargs)

        # Extract the final message content
        report_content = response["messages"][-1].content

        if _verbose_mode:
            print("\n   ✅ Agent completed!")
            print(f"   📊 Response messages: {len(response['messages'])}")
            print(f"\n{'─'*60}")
            print("📜 DETAILED MESSAGE TRACE")
            print(f"{'─'*60}")

            for i, msg in enumerate(response["messages"]):
                msg_type = type(msg).__name__
                print(f"\n   ┌─ [{i}] {msg_type}")

                # Show tool calls from AI
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc.get("name", "unknown")
                        tool_args = tc.get("args", {})
                        print(f"   │  🔧 Tool Call: {tool_name}")

                        # Show todo list content
                        if tool_name == "write_todos" and "todos" in tool_args:
                            print("   │  📋 TODO LIST UPDATE:")
                            todos = tool_args["todos"]
                            if isinstance(todos, list):
                                for todo in todos[:5]:  # Show first 5
                                    status = todo.get("status", "?")
                                    content = todo.get("content", "?")[:50]
                                    icon = (
                                        "✅"
                                        if status == "completed"
                                        else "🔄" if status == "in_progress" else "⏳"
                                    )
                                    print(f"   │     {icon} [{status}] {content}")

                        # Show task (subagent) delegation
                        elif tool_name == "task":
                            agent_name = tool_args.get(
                                "name", tool_args.get("agent", "?")
                            )
                            task_desc = str(
                                tool_args.get("task", tool_args.get("prompt", "?"))
                            )[:80]
                            print(f"   │  👤 Delegating to: {agent_name}")
                            print(f"   │  📝 Task: {task_desc}...")

                        # Show file operations
                        elif tool_name == "read_file":
                            file_path = tool_args.get(
                                "file_path", tool_args.get("path", "?")
                            )
                            print(f"   │  📖 Reading: {file_path}")

                        elif tool_name == "write_file":
                            file_path = tool_args.get(
                                "file_path", tool_args.get("path", "?")
                            )
                            print(f"   │  📝 Writing: {file_path}")

                        else:
                            # Show first 100 chars of args
                            args_preview = str(tool_args)[:100]
                            print(f"   │  📦 Args: {args_preview}...")

                # Show tool results
                elif hasattr(msg, "name") and msg.name:
                    tool_name = msg.name
                    content = msg.content if hasattr(msg, "content") else ""

                    print(f"   │  🔧 Tool Result: {tool_name}")

                    # Show subagent response content
                    if tool_name == "task":
                        print(f"   │  👤 SUBAGENT RESPONSE ({len(content)} chars):")
                        # Show first 500 chars of subagent response
                        preview = content[:500] if len(content) > 500 else content
                        for line in preview.split("\n")[:10]:
                            print(f"   │     {line[:70]}")
                        if len(content) > 500:
                            print(
                                f"   │     ... [truncated, {len(content)} total chars]"
                            )

                    # Show file content that was read
                    elif tool_name == "read_file":
                        print(f"   │  📄 FILE CONTENT ({len(content)} chars):")
                        preview = content[:300] if len(content) > 300 else content
                        for line in preview.split("\n")[:8]:
                            print(f"   │     {line[:70]}")

                    # Show todo confirmation
                    elif tool_name == "write_todos":
                        print("   │  ✅ Todos updated")

                    else:
                        print(f"   │  📦 Result: {len(content)} chars")

                # Show AI response
                elif hasattr(msg, "content") and msg.content:
                    content = msg.content
                    if len(content) > 200:
                        print(f"   │  💬 Response: {content[:200]}...")
                    else:
                        print(f"   │  💬 Response: {content}")

                print("   └─")

            # Show final state files if available
            if "files" in response:
                print(f"\n{'─'*60}")
                print("📁 FILES IN STATE (after execution)")
                print(f"{'─'*60}")
                for path, file_data in response.get("files", {}).items():
                    if isinstance(file_data, dict) and "content" in file_data:
                        content = "\n".join(file_data["content"])
                        print(f"\n   📄 {path} ({len(content)} chars)")
                        preview = content[:200] if len(content) > 200 else content
                        for line in preview.split("\n")[:5]:
                            print(f"      {line}")

        print(
            f"\n📊 {'Report' if current_round == 0 else 'Rebuttal'} Generated ({len(report_content)} chars)"
        )

        return {
            "messages": [AIMessage(content=report_content, name="Researcher")],
            "round_count": current_round + 1,
        }

    except Exception as e:
        import traceback

        error_msg = f"Research failed: {str(e)}"
        print(f"❌ {error_msg}")
        print(f"Traceback:\n{traceback.format_exc()}")
        return {
            "messages": [AIMessage(content=error_msg, name="Researcher")],
            "round_count": current_round + 1,
        }


def run_debater(state: DebateState) -> dict[str, Any]:
    """
    The Adversary Agent (Debater) with runtime context.

    Reads the latest report/defense and attacks it.
    If satisfied, outputs "NO FURTHER CONCERNS" to end debate.
    """
    global _verbose_mode
    messages = state["messages"]
    current_round = state["round_count"]
    context = _context_from_state(state)
    symbol = context.symbol

    print(f"\n{'='*60}")
    print(f"⚔️ CRITIQUE PHASE (Round {current_round}): Challenging {symbol} thesis")
    print(f"{'='*60}")

    # Get the latest report/defense from the Researcher
    latest_report = messages[-1].content

    critique_prompt = f"""Review the Researcher's latest argument:

"{latest_report[:2000]}..."  # Truncated for context

If you still have valid concerns based on your analysis, list them aggressively.
If the Researcher has successfully addressed all risks and you agree with the thesis,
respond with exactly: "{TERMINATION_SIGNAL}".

Be thorough but fair. Only say "{TERMINATION_SIGNAL}" if you genuinely have no more concerns."""

    try:
        debater_agent, initial_files = _get_debater_agent(context)

        # Build invoke kwargs
        invoke_kwargs: dict[str, Any] = {
            "config": {
                "configurable": {"thread_id": f"debate-{symbol}-r{current_round}"}
            },
        }

        # Add context if runtime supports it
        if RUNTIME_AVAILABLE:
            invoke_kwargs["context"] = context

        # Build input with files for StateBackend
        input_data = {
            "messages": messages + [HumanMessage(content=critique_prompt)],
            "files": initial_files,  # Pass context files via invoke
        }

        if _verbose_mode:
            print(f"\n{'─'*60}")
            print("📤 INVOKE DEBATER AGENT")
            print(f"{'─'*60}")
            print(f"   thread_id: debate-{symbol}-r{current_round}")
            print(f"   messages: {len(input_data['messages'])} messages")
            print(f"   files: {list(initial_files.keys())}")
            print("\n   📨 Critique prompt preview:")
            preview = (
                critique_prompt[:300] + "..."
                if len(critique_prompt) > 300
                else critique_prompt
            )
            for line in preview.split("\n")[:5]:
                print(f"   {line}")
            print("\n   ⏳ Invoking debater (this calls LLM + tools)...")

        response = debater_agent.invoke(input_data, **invoke_kwargs)

        critique_content = response["messages"][-1].content

        if _verbose_mode:
            print("\n   ✅ Debater completed!")
            print(f"   📊 Response messages: {len(response['messages'])}")
            print(f"\n{'─'*60}")
            print("📜 DEBATER MESSAGE TRACE")
            print(f"{'─'*60}")

            for i, msg in enumerate(response["messages"]):
                msg_type = type(msg).__name__
                print(f"\n   ┌─ [{i}] {msg_type}")

                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc.get("name", "unknown")
                        tool_args = tc.get("args", {})
                        print(f"   │  🔧 Tool Call: {tool_name}")
                        if tool_name == "task":
                            agent_name = tool_args.get(
                                "name", tool_args.get("agent", "?")
                            )
                            task_desc = str(
                                tool_args.get("task", tool_args.get("prompt", "?"))
                            )[:80]
                            print(f"   │  👤 Delegating to: {agent_name}")
                            print(f"   │  📝 Task: {task_desc}...")
                        elif tool_name in ["search_stock_news", "get_market_movers"]:
                            print("   │  📰 Searching for counter-evidence...")

                elif hasattr(msg, "name") and msg.name:
                    tool_name = msg.name
                    content = msg.content if hasattr(msg, "content") else ""
                    print(f"   │  🔧 Tool Result: {tool_name}")
                    if tool_name == "task":
                        print(f"   │  👤 SUBAGENT RESPONSE ({len(content)} chars):")
                        preview = content[:400] if len(content) > 400 else content
                        for line in preview.split("\n")[:8]:
                            print(f"   │     {line[:70]}")
                    else:
                        print(f"   │  📦 Result: {len(content)} chars")

                elif hasattr(msg, "content") and msg.content:
                    content = msg.content
                    if len(content) > 150:
                        print(f"   │  💬 {content[:150]}...")
                    else:
                        print(f"   │  💬 {content}")

                print("   └─")

        print(f"\n🎯 Critique Generated ({len(critique_content)} chars)")

        # Check for termination signal
        if TERMINATION_SIGNAL in critique_content:
            print("✅ Debater satisfied - ending debate early")

        return {
            "messages": [AIMessage(content=critique_content, name="Debater")],
        }

    except Exception as e:
        error_msg = f"Debate failed: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "messages": [AIMessage(content=error_msg, name="Debater")],
        }


def should_continue(state: DebateState) -> str:
    """
    Conditional router: Decide whether to continue debate or end.

    Returns:
        "continue" - Loop back to researcher for rebuttal
        "end" - Finish the debate
    """
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    current_round = state["round_count"]

    # Condition 1: Max rounds reached
    if current_round >= MAX_DEBATE_ROUNDS:
        print(f"\n⏱️ Max rounds ({MAX_DEBATE_ROUNDS}) reached - ending debate")
        return "end"

    # Condition 2: Debater is satisfied
    if TERMINATION_SIGNAL in last_message:
        print("\n🤝 Consensus reached - debate concluded")
        return "end"

    # Condition 3: Continue debate
    print(f"\n🔄 Continuing to round {current_round + 1}...")
    return "continue"


def build_workflow():
    """Build the LangGraph workflow with debate cycling."""
    workflow = StateGraph(DebateState)

    # Add nodes
    workflow.add_node("researcher", run_researcher)
    workflow.add_node("debater", run_debater)

    # Start -> Researcher
    workflow.add_edge(START, "researcher")

    # Researcher -> Debater (always)
    workflow.add_edge("researcher", "debater")

    # Debater -> Conditional Router
    workflow.add_conditional_edges(
        "debater",
        should_continue,
        {
            "continue": "researcher",  # Loop back for rebuttal
            "end": END,  # Finish debate
        },
    )

    return workflow.compile()


# =============================================================================
# MAIN EXECUTION
# =============================================================================


def reset_agents():
    """Reset global agent instances for fresh experiment run."""
    global _main_agent, _main_agent_files, _debater_agent, _debater_agent_files, _current_context
    _main_agent = None
    _main_agent_files = None
    _debater_agent = None
    _debater_agent_files = None
    _current_context = None


def run_experiment(
    symbol: str = "AAPL",
    stream: bool = True,
    user_id: str = "anonymous",
    risk_tolerance: str = "moderate",
    verbose: bool = False,
):
    """
    Run the hybrid deep agent experiment with debate cycling and runtime context.

    Args:
        symbol: Stock ticker to analyze
        stream: Whether to stream output (shows each round as it happens)
        user_id: User identifier for session tracking
        risk_tolerance: Investment risk profile (conservative/moderate/aggressive)
        verbose: Show detailed logging of agent internals
    """
    global _verbose_mode
    _verbose_mode = verbose

    # Create runtime context with all session information
    context = AgentContext(
        symbol=symbol,
        user_id=user_id,
        risk_tolerance=risk_tolerance,
        max_debate_rounds=MAX_DEBATE_ROUNDS,
    )

    print(f"\n{'#'*70}")
    print("# HYBRID DEEP AGENT EXPERIMENT (with Runtime Context)")
    print(f"# Symbol: {context.symbol}")
    print(f"# Date: {context.current_date}")
    print(f"# Period: {context.six_months_ago} → {context.current_date}")
    print(f"# Session: {context.session_id}")
    print(f"# User: {context.user_id}")
    print(f"# Risk: {context.risk_tolerance}")
    print(f"# Max Rounds: {context.max_debate_rounds}")
    print(f"# Runtime Support: {'✅ Enabled' if RUNTIME_AVAILABLE else '❌ Disabled'}")
    print("# Built-in Middleware: ✅ Summarization, TodoList, Filesystem")
    print(f"# Verbose Mode: {'✅ ON' if verbose else '❌ OFF'}")
    print(f"{'#'*70}")

    if verbose:
        print(f"\n{'='*70}")
        print("📚 EXPERIMENT ARCHITECTURE OVERVIEW")
        print(f"{'='*70}")
        print(
            """
┌─────────────────────────────────────────────────────────────────────┐
│                    HYBRID DEEP AGENT ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  User Query ──► LangGraph Workflow                                  │
│                      │                                              │
│                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  RESEARCHER NODE (Main Deep Agent)                          │   │
│  │  ├─ System Prompt: Senior Investment Strategist             │   │
│  │  ├─ Backend: StateBackend (files via invoke)                │   │
│  │  ├─ Context Files: /context/session.md, symbol.txt, date.txt│   │
│  │  │                                                          │   │
│  │  │  Delegates to 3 Specialist Subagents:                    │   │
│  │  │  ┌───────────────────────────────────────────────────┐   │   │
│  │  │  │ technical_analyst: Fibonacci, Stochastic, Prices  │   │   │
│  │  │  │ news_analyst: News Sentiment, Market Movers       │   │   │
│  │  │  │ financial_analyst: Company Overview, Cash Flow    │   │   │
│  │  │  └───────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                      │                                              │
│                      ▼ (always)                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  DEBATER NODE (Adversary Deep Agent)                        │   │
│  │  ├─ System Prompt: Short Seller / Contrarian                │   │
│  │  ├─ Tools: News tools (to find counter-evidence)            │   │
│  │  └─ Output: Critique or "NO FURTHER CONCERNS"               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                      │                                              │
│                      ▼ (conditional)                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  should_continue() Router                                    │   │
│  │  ├─ "NO FURTHER CONCERNS" in output? → END                  │   │
│  │  ├─ round >= MAX_ROUNDS (5)? → END                          │   │
│  │  └─ else → CONTINUE (back to RESEARCHER for rebuttal)       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
"""
        )

    if not DEEPAGENTS_AVAILABLE:
        print("\n❌ Cannot run experiment: deepagents not installed")
        print("Run: pip install deepagents")
        return

    if not DASHSCOPE_API_KEY:
        print("\n❌ Cannot run experiment: DASHSCOPE_API_KEY not set")
        return

    # Reset agents for fresh run
    reset_agents()

    # Build workflow
    app = build_workflow()

    # Serialize context for state passing
    context_dict = {
        "session_id": context.session_id,
        "user_id": context.user_id,
        "symbol": context.symbol,
        "current_date": context.current_date,
        "six_months_ago": context.six_months_ago,
        "max_debate_rounds": context.max_debate_rounds,
        "risk_tolerance": context.risk_tolerance,
    }

    # Initial input with context
    query = f"Should I invest in {symbol} right now? Provide a comprehensive analysis."
    inputs = {
        "messages": [HumanMessage(content=query)],
        "round_count": 0,
        "symbol": symbol,
        "context_dict": context_dict,
    }

    # Collect all messages during streaming
    all_messages: list[BaseMessage] = []

    if stream:
        # Stream mode: Show each step as it happens
        print("\n" + "=" * 70)
        print("🎬 STARTING DEBATE STREAM")
        print("=" * 70)

        final_state = None
        for event in app.stream(inputs):
            for node_name, value in event.items():
                if "messages" in value and value["messages"]:
                    # Accumulate messages
                    all_messages.extend(value["messages"])

                    last_msg = value["messages"][-1]
                    agent_name = getattr(last_msg, "name", node_name.upper())

                    print(f"\n{'─'*70}")
                    print(f"📝 {agent_name}")
                    print(f"{'─'*70}")
                    # Print first 1500 chars to keep output manageable
                    content = last_msg.content
                    if len(content) > 1500:
                        print(content[:1500] + "\n... [truncated]")
                    else:
                        print(content)

                final_state = value
    else:
        # Non-stream mode: Run to completion
        final_state = app.invoke(inputs)
        if final_state and "messages" in final_state:
            all_messages = final_state["messages"]

    # Print final summary
    print(f"\n{'='*70}")
    print("📊 DEBATE SUMMARY")
    print(f"{'='*70}")

    # Count messages by agent name
    researcher_msgs = [
        m for m in all_messages if getattr(m, "name", "") == "Researcher"
    ]
    debater_msgs = [m for m in all_messages if getattr(m, "name", "") == "Debater"]

    print(f"Total Rounds: {len(researcher_msgs)}")
    print(f"Researcher Messages: {len(researcher_msgs)}")
    print(f"Debater Messages: {len(debater_msgs)}")

    # Check outcome
    if debater_msgs:
        last_critique = debater_msgs[-1].content
        if TERMINATION_SIGNAL in last_critique:
            print("Outcome: 🤝 CONSENSUS REACHED")
        else:
            print("Outcome: ⏱️ MAX ROUNDS REACHED")
    else:
        print("Outcome: ❓ NO CRITIQUE GENERATED")

    print(f"\n{'='*70}")
    print("✅ EXPERIMENT COMPLETE")
    print(f"{'='*70}")

    return final_state


def run_simple_experiment(symbol: str = "AAPL", user_id: str = "anonymous"):
    """
    Run a simplified single-round experiment (no debate loop).

    Useful for quick testing without the full debate cycle.
    """
    # Create context
    context = AgentContext(symbol=symbol, user_id=user_id)

    print(f"\n{'#'*70}")
    print("# SIMPLE EXPERIMENT (Single Round)")
    print(f"# Symbol: {context.symbol}")
    print(f"# Date: {context.current_date}")
    print(f"# Session: {context.session_id}")
    print(f"{'#'*70}")

    if not DEEPAGENTS_AVAILABLE:
        print("\n❌ Cannot run experiment: deepagents not installed")
        return

    reset_agents()

    # Just run researcher once with context
    query = f"Should I invest in {symbol} right now? Provide a comprehensive analysis."
    main_agent, initial_files = create_main_agent(context)

    # Build invoke kwargs
    invoke_kwargs: dict[str, Any] = {
        "config": {"configurable": {"thread_id": f"simple-{symbol}"}},
    }
    if RUNTIME_AVAILABLE:
        invoke_kwargs["context"] = context

    # Build input with files for StateBackend
    input_data = {
        "messages": [HumanMessage(content=query)],
        "files": initial_files,  # Pass context files via invoke
    }

    response = main_agent.invoke(input_data, **invoke_kwargs)

    print(f"\n{'='*70}")
    print("📈 RESEARCH REPORT")
    print(f"{'='*70}")
    print(response["messages"][-1].content)

    return response


if __name__ == "__main__":
    import sys

    # Check for command line args
    # Usage: python -m src.agent.experiments.exp_hybrid_deep_agent [SYMBOL] [MODE] [USER_ID] [RISK] [--verbose]
    symbol = sys.argv[1] if len(sys.argv) > 1 else "TSLA"
    mode = sys.argv[2] if len(sys.argv) > 2 else "debate"
    user_id = sys.argv[3] if len(sys.argv) > 3 else "test_user"
    risk = sys.argv[4] if len(sys.argv) > 4 else "moderate"
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    if mode == "simple":
        run_simple_experiment(symbol, user_id=user_id)
    else:
        run_experiment(
            symbol, stream=True, user_id=user_id, risk_tolerance=risk, verbose=verbose
        )
