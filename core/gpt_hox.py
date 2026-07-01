"""
              ┌──────────────┐
              │   Planner    │
              └──────┬───────┘
                     │
     ┌───────────────┼────────────────┐
     ▼               ▼                ▼
 Research        Direct Solve       Tool Use
     ▼               ▼                ▼
     └──────┬────────┴────────┬───────┘
            ▼                 ▼
          Coder ←────────── Research fix loop
            │
            ▼
         Critic
       ┌────┴─────┐
       ▼          ▼
     END      back to coder

"""

from typing import TypedDict, Annotated, List, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, SystemMessage

from core.agent import Agent
from core.llm import GEMINI_LITE, HUGGINGFACE_LITE

from core.prompts import (
    PLANNER_PROMPT,
    RESEARCHER_PROMPT,
    CODER_PROMPT,
    CRITIC_PROMPT
)

from core.tools import *


# ============================================================
# STATE (DYNAMIC DAG)
# ============================================================

class MultiAgentState(TypedDict):
    task: str

    messages: Annotated[List[AnyMessage], add_messages]

    plan: str

    needs_research: bool
    needs_coding: bool
    needs_tools: bool
    needs_review: bool

    research_output: str
    coding_output: str
    tool_output: str

    final_answer: str

    next_agent: Literal[
        "planner",
        "researcher",
        "coder",
        "tools",
        "critic",
        "end"
    ]


# ============================================================
# SYSTEM
# ============================================================

class DynamicMultiAgentSystem:

    def __init__(self):

        # -------------------------
        # AGENTS (reusing your class)
        # -------------------------

        self.planner = Agent(
            primary_LLM=GEMINI_LITE,
            backup_LLM=HUGGINGFACE_LITE,
            tools=[],
            sys_prompt=PLANNER_PROMPT,
            keywords=[],
            extract=False,
            name="planner"
        )

        self.researcher = Agent(
            primary_LLM=GEMINI_LITE,
            backup_LLM=HUGGINGFACE_LITE,
            tools=[
                duckduck_websearch,
                visit_webpage,
                wiki_search,
                youtube_viewer
            ],
            sys_prompt=RESEARCHER_PROMPT,
            keywords=[],
            extract=False,
            name="researcher"
        )

        self.coder = Agent(
            primary_LLM=GEMINI_LITE,
            backup_LLM=HUGGINGFACE_LITE,
            tools=[
                run_python,
                add,
                subtract,
                multiply,
                divide
            ],
            sys_prompt=CODER_PROMPT,
            keywords=[],
            extract=False,
            name="coder"
        )

        self.critic = Agent(
            primary_LLM=GEMINI_LITE,
            backup_LLM=HUGGINGFACE_LITE,
            tools=[
                duckduck_websearch,
                visit_webpage
            ],
            sys_prompt=CRITIC_PROMPT,
            keywords=[],
            extract=False,
            name="critic"
        )

        self.graph = self._build_graph()

    # ========================================================
    # PLANNER (DECIDES FLOW)
    # ========================================================

    def planner_node(self, state: MultiAgentState):

        prompt = f"""
TASK:
{state['task']}

Decide which capabilities are needed.

Return STRICT JSON:

{{
  "needs_research": true/false,
  "needs_coding": true/false,
  "needs_tools": true/false,
  "needs_review": true/false,
  "plan": "short plan"
}}
"""

        result = self.planner(prompt)

        # NOTE: we assume Agent returns parsed string or JSON text
        import json
        data = json.loads(result)

        return {
            "plan": data["plan"],
            "needs_research": data["needs_research"],
            "needs_coding": data["needs_coding"],
            "needs_tools": data["needs_tools"],
            "needs_review": data["needs_review"],
            "next_agent": self._first_step(data)
        }

    def _first_step(self, data):
        if data["needs_research"]:
            return "researcher"
        if data["needs_coding"]:
            return "coder"
        if data["needs_tools"]:
            return "tools"
        return "critic"

    # ========================================================
    # RESEARCHER
    # ========================================================

    def researcher_node(self, state: MultiAgentState):

        prompt = f"""
TASK: {state['task']}
PLAN: {state['plan']}
"""

        output = self.researcher(prompt)

        return {
            "research_output": output,
            "next_agent": "coder" if state["needs_coding"] else "critic"
        }

    # ========================================================
    # CODER
    # ========================================================

    def coder_node(self, state: MultiAgentState):

        prompt = f"""
TASK: {state['task']}
PLAN: {state['plan']}
RESEARCH: {state['research_output']}
"""

        output = self.coder(prompt)

        return {
            "coding_output": output,
            "next_agent": "tools" if state["needs_tools"] else "critic"
        }

    # ========================================================
    # TOOL NODE
    # ========================================================

    def tool_node(self, state: MultiAgentState):

        # Tool execution is handled inside Agent automatically
        output = "tools executed via agent"

        return {
            "tool_output": output,
            "next_agent": "critic"
        }

    # ========================================================
    # CRITIC (CAN LOOP BACK)
    # ========================================================

    def critic_node(self, state: MultiAgentState):

        prompt = f"""
TASK: {state['task']}

PLAN:
{state['plan']}

RESEARCH:
{state['research_output']}

CODE:
{state['coding_output']}

TOOLS:
{state['tool_output']}

Decide:
1. Is this correct?
2. If not, specify what is missing.
3. If yes, return FINAL ANSWER only.
"""

        review = self.critic(prompt)

        # simple heuristic routing
        if "FINAL ANSWER" in review or "correct" in review.lower():
            return {
                "final_answer": review,
                "next_agent": "end"
            }

        # fallback loop (self-healing system)
        if "research" in review.lower():
            return {"next_agent": "researcher"}

        if "code" in review.lower():
            return {"next_agent": "coder"}

        return {
            "final_answer": review,
            "next_agent": "end"
        }

    # ========================================================
    # ROUTER
    # ========================================================

    def router(self, state: MultiAgentState):
        return state["next_agent"]

    # ========================================================
    # GRAPH
    # ========================================================

    def _build_graph(self):

        builder = StateGraph(MultiAgentState)

        builder.add_node("planner", self.planner_node)
        builder.add_node("researcher", self.researcher_node)
        builder.add_node("coder", self.coder_node)
        builder.add_node("tools", self.tool_node)
        builder.add_node("critic", self.critic_node)

        builder.add_edge(START, "planner")

        builder.add_conditional_edges(
            "planner",
            self.router,
            {
                "researcher": "researcher",
                "coder": "coder",
                "tools": "tools",
                "critic": "critic"
            }
        )

        builder.add_conditional_edges(
            "researcher",
            self.router,
            {
                "coder": "coder",
                "critic": "critic"
            }
        )

        builder.add_conditional_edges(
            "coder",
            self.router,
            {
                "tools": "tools",
                "critic": "critic"
            }
        )

        builder.add_edge("tools", "critic")

        builder.add_conditional_edges(
            "critic",
            self.router,
            {
                "researcher": "researcher",
                "coder": "coder",
                "end": END
            }
        )

        return builder.compile(checkpointer=MemorySaver())

    # ========================================================
    # ENTRYPOINT
    # ========================================================

    def __call__(self, task: str):

        state = {
            "task": task,
            "messages": [],
            "plan": "",

            "needs_research": False,
            "needs_coding": False,
            "needs_tools": False,
            "needs_review": False,

            "research_output": "",
            "coding_output": "",
            "tool_output": "",

            "final_answer": "",
            "next_agent": "planner"
        }

        result = self.graph.invoke(state)

        return result["final_answer"]