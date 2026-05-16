---
title: Financial Agent Architecture Design
status: shipped
version: backend@0.7.0+
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/src/agent/
  - backend/src/api/chat/streaming/
---

# Financial Agent Architecture Design

## 12-Factor Agent Implementation

### Factor 1: Own Your Configuration
```python
# Environment-based configuration
from pydantic_settings import BaseSettings

class AgentConfig(BaseSettings):
    mongodb_url: str
    redis_url: str
    dashscope_api_key: str

    class Config:
        env_file = ".env"
```

### Factor 2: Own Your Prompts
```python
# Local prompt management
from langchain_core.prompts import ChatPromptTemplate

# Prompts defined locally and version-controlled in this repo
PROMPTS = {
    "system": ChatPromptTemplate.from_messages([
        ("system", "You are a financial analysis assistant..."),
        ("human", "{input}")
    ]),
    "fibonacci_analyzer": ChatPromptTemplate.from_template(
        "Analyze Fibonacci levels for {symbol}..."
    )
}
# Note: Prompt versions are tracked via git; structlog adds run-time context
```

### Factor 3: External Dependencies as Services
```python
# Clean service interfaces
from abc import ABC, abstractmethod

class MarketDataService(ABC):
    @abstractmethod
    async def get_stock_data(self, symbol: str, period: str) -> dict: ...

class ChartStorageService(ABC):
    @abstractmethod
    async def upload_chart(self, chart_data: bytes) -> str: ...

class AIAnalysisService(ABC):
    @abstractmethod
    async def interpret_chart(self, chart_url: str, context: dict) -> str: ...
```

### Factor 5: Unified State Management
```python
from dataclasses import dataclass
from typing import Optional, List, Dict
from langgraph.graph import Graph

@dataclass
class FinancialAgentState:
    """Unified state object passed through entire agent graph"""
    # Conversation context
    messages: List[Dict[str, str]]
    user_id: str
    session_id: str

    # Analysis context
    current_symbol: Optional[str] = None
    analysis_type: Optional[str] = None
    timeframe: str = "6mo"

    # Results
    fibonacci_data: Optional[Dict] = None
    chart_url: Optional[str] = None
    ai_interpretation: Optional[str] = None

    # Control flow
    intent: Optional[str] = None
    confidence_score: float = 0.0
    error_count: int = 0
    human_approval_needed: bool = False

    # Audit trail
    tools_executed: List[str] = None
    execution_time: float = 0.0

    def __post_init__(self):
        if self.tools_executed is None:
            self.tools_executed = []
```

### Factor 6 & 7: Pause/Resume & Human-in-the-Loop
```python
class FinancialAgentGraph:
    def create_graph(self) -> Graph:
        graph = Graph()

        # Standard analysis flow
        graph.add_node("classify_intent", self.classify_intent)
        graph.add_node("fibonacci_analysis", self.fibonacci_analysis)
        graph.add_node("generate_chart", self.generate_chart)
        graph.add_node("ai_interpretation", self.ai_interpretation)
        graph.add_node("synthesize_response", self.synthesize_response)

        # Human-in-the-loop nodes
        graph.add_node("human_approval", self.wait_for_human_approval)
        graph.add_node("escalate_to_human", self.escalate_to_human)

        # Conditional edges with explicit control flow
        graph.add_conditional_edges(
            "fibonacci_analysis",
            self.check_analysis_confidence,
            {
                "high_confidence": "generate_chart",
                "low_confidence": "human_approval",
                "error": "escalate_to_human"
            }
        )

        return graph

    def check_analysis_confidence(self, state: FinancialAgentState) -> str:
        """Factor 8: Own Your Control Flow"""
        if state.error_count > 2:
            return "error"
        elif state.confidence_score < 0.7:
            return "low_confidence"
        else:
            return "high_confidence"

    async def wait_for_human_approval(self, state: FinancialAgentState) -> FinancialAgentState:
        """Factor 6: Pause capability - persist state and wait"""
        state.human_approval_needed = True
        # Persist state to MongoDB
        await self.state_store.save_state(state.session_id, state)
        return state

    async def resume_from_approval(self, session_id: str, approval: bool) -> FinancialAgentState:
        """Factor 7: Resume capability - reload state and continue"""
        state = await self.state_store.load_state(session_id)
        state.human_approval_needed = False

        if approval:
            # Continue with chart generation
            return await self.generate_chart(state)
        else:
            # Escalate to human
            return await self.escalate_to_human(state)
```

### Factor 8: Own Your Control Flow
```python
class IntentClassifier:
    """Factor 8: Explicit control flow decisions"""

    @traceable
    async def classify_intent(self, state: FinancialAgentState) -> FinancialAgentState:
        latest_message = state.messages[-1]["content"]

        # Use LLM to classify intent with structured output
        classification = await self.llm.ainvoke(
            PROMPTS["intent_classifier"].format(
                message=latest_message,
                conversation_history=state.messages[-5:]  # Last 5 messages for context
            )
        )

        # Explicit mapping of intents to next actions
        intent_mapping = {
            "fibonacci_analysis": "fibonacci_analysis",
            "market_structure": "market_structure_analysis",
            "macro_analysis": "macro_analysis",
            "chart_only": "generate_chart",
            "general_question": "financial_qa",
            "unclear": "clarification_request"
        }

        state.intent = classification.intent
        state.confidence_score = classification.confidence

        return state
```

### Factor 9: Error Handling & Observability
```python
import structlog

logger = structlog.get_logger()

class FinancialAnalysisTool:
    async def analyze_fibonacci(self, state: FinancialAgentState) -> FinancialAgentState:
        try:
            # Reuse existing CLI analyzer
            analyzer = FibonacciAnalyzer()

            with structlog.contextvars.bound_contextvars(
                user_id=state.user_id,
                symbol=state.current_symbol,
                analysis_type="fibonacci"
            ):
                logger.info("Starting Fibonacci analysis")

                result = await analyzer.analyze_async(
                    state.current_symbol,
                    state.timeframe
                )

                state.fibonacci_data = result
                state.confidence_score = result.get("confidence", 0.0)
                state.tools_executed.append("fibonacci_analysis")

                logger.info("Fibonacci analysis completed",
                           confidence=state.confidence_score)

        except Exception as e:
            state.error_count += 1
            logger.error("Fibonacci analysis failed",
                        error=str(e),
                        error_count=state.error_count)

            # Circuit breaker pattern
            if state.error_count >= 3:
                state.human_approval_needed = True

        return state
```

### Factor 10: Small Agents (Composable Tools)
```python
from langchain.tools import tool
from langchain_core.runnables import RunnablePassthrough

# Small, focused tools using LCEL
@tool
def fibonacci_retracement_tool(symbol: str, timeframe: str = "6mo") -> dict:
    """Calculate Fibonacci retracement levels for a stock symbol."""
    analyzer = FibonacciAnalyzer()
    return analyzer.analyze(symbol, timeframe)

@tool
def market_structure_tool(symbol: str, timeframe: str = "6mo") -> dict:
    """Analyze market structure and swing points."""
    analyzer = MarketStructureAnalyzer()
    return analyzer.analyze(symbol, timeframe)

@tool
def macro_sentiment_tool() -> dict:
    """Analyze overall market macro sentiment."""
    analyzer = MacroAnalyzer()
    return analyzer.get_market_sentiment()

# Compose tools into chains using LCEL
fibonacci_chain = (
    RunnablePassthrough.assign(
        fibonacci_data=fibonacci_retracement_tool
    )
    | RunnablePassthrough.assign(
        market_structure=market_structure_tool
    )
    | chart_generation_tool
)
```

### Factor 11 & 12: Triggerable & Stateless Service
```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer

app = FastAPI(title="Financial Agent API")
security = HTTPBearer()

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    chart_url: Optional[str] = None
    analysis_data: Optional[Dict] = None
    session_id: str
    requires_approval: bool = False

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    token: str = Depends(security),
    agent: FinancialAgent = Depends(get_agent)
) -> ChatResponse:
    """Factor 11: Triggerable - HTTP endpoint triggers agent execution"""

    # Factor 12: Stateless - load state from external store
    user_id = await validate_token(token)
    session_id = request.session_id or generate_session_id()

    # Load existing state or create new
    try:
        state = await agent.state_store.load_state(session_id)
    except StateNotFoundError:
        state = FinancialAgentState(
            messages=[],
            user_id=user_id,
            session_id=session_id
        )

    # Add new message to state
    state.messages.append({
        "role": "user",
        "content": request.message,
        "timestamp": datetime.utcnow().isoformat()
    })

    # Process through agent graph
    result_state = await agent.process(state)

    # Save updated state
    await agent.state_store.save_state(session_id, result_state)

    # Return stateless response
    return ChatResponse(
        response=result_state.messages[-1]["content"],
        chart_url=result_state.chart_url,
        analysis_data=result_state.fibonacci_data,
        session_id=session_id,
        requires_approval=result_state.human_approval_needed
    )

@app.post("/api/approve/{session_id}")
async def approve_analysis(
    session_id: str,
    approval: bool,
    token: str = Depends(security)
):
    """Factor 6/7: Human approval endpoint for pause/resume"""
    user_id = await validate_token(token)

    # Resume agent execution from approval
    result_state = await agent.resume_from_approval(session_id, approval)

    return ChatResponse(
        response=result_state.messages[-1]["content"],
        chart_url=result_state.chart_url,
        session_id=session_id,
        requires_approval=False
    )
```

## Tool Registry Pattern
```python
class FinancialToolRegistry:
    """Central registry for all financial analysis tools"""

    def __init__(self):
        self.tools = {
            "fibonacci": FibonacciTool(),
            "market_structure": MarketStructureTool(),
            "macro": MacroAnalysisTool(),
            "chart": ChartGenerationTool(),
            "fundamentals": FundamentalsTool()
        }

    def get_tool(self, tool_name: str) -> BaseTool:
        if tool_name not in self.tools:
            raise ToolNotFoundError(f"Tool {tool_name} not registered")
        return self.tools[tool_name]

    def list_available_tools(self) -> List[str]:
        return list(self.tools.keys())
```

This architecture ensures the financial agent follows all 12 factors while maintaining sophisticated analysis capabilities, enhanced with conversational AI and production-ready observability.
