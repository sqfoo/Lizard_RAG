import time
import uuid
from abc import ABC
from typing import TypedDict, Annotated, Optional, Literal, List

from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from langchain_core.messages import AnyMessage, SystemMessage

from core.llm import setup_model, valid_LLM
from core.utils import FallbackLoggingHandler

MAX_RETRIES = 5
BASE_WAIT = 10

# =========================
# STATE
# =========================
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    input_file: Optional[str]


# =========================
# AGENT
# =========================
class Agent(ABC):
    def __init__(
        self,
        primary_LLM: dict,
        backup_LLM: dict,
        tools: list,
        sys_prompt: str,
        extract: bool = True,
        name: str = ""
    ):
        assert primary_LLM in valid_LLM
        assert backup_LLM in valid_LLM

        print(
            f"Setting up {primary_LLM['type']} as primary, "
            f"{backup_LLM['type']} as backup"
        )

        primary_llm = setup_model(primary_LLM, callbacks=[FallbackLoggingHandler()])
        backup_llm = setup_model(backup_LLM)

        self.llm = primary_llm.with_fallbacks([backup_llm])

        self.tools = ToolNode(tools)
        self.llm_with_tools = self.llm.bind_tools(tools)

        self.sys_prompt = sys_prompt
        self.extract = extract
        self.name = name

        print(f"Building the agent named {name} ... ... ")
        self.graph = self._build_graph()
        self.thread_id = str(uuid.uuid4())

    # =========================
    # GRAPH
    # =========================
    def _build_graph(self):
        builder = StateGraph(AgentState)

        builder.add_node("assistant", self._assistant)
        builder.add_node("tools", self.tools)

        builder.add_edge(START, "assistant")

        builder.add_conditional_edges(
            "assistant",
            self._route_tools,
            {
                "tools": "tools",
                "__end__": END,
            },
        )

        builder.add_edge("tools", "assistant")

        return builder.compile(checkpointer=MemorySaver())

    # =========================
    # ROUTER
    # =========================
    def _route_tools(self, state: AgentState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]

        tool_calls = getattr(last, "tool_calls", None)

        if not tool_calls:
            return "__end__"

        return "tools"

    # =========================
    # ASSISTANT NODE
    # =========================
    def _assistant(self, state: AgentState) -> dict:
        sys_msg = SystemMessage(content=self.sys_prompt)

        response = self.llm_with_tools.invoke(
            [sys_msg] + state["messages"]
        )

        return {
            "messages": [response],
            "input_file": state.get("input_file")
        }

    # =========================
    # CALL ENTRYPOINT
    # =========================
    def __call__(self, human_message: str) -> str:
        payload = {
            "messages": [
                {"role": "user", "content": human_message}
            ]
        }

        for attempt in range(MAX_RETRIES):
            try:
                result = self.graph.invoke(
                    payload,
                    config={"configurable": {"thread_id": self.thread_id}},
                )

                final_msg = result["messages"][-1]
                output = final_msg.content

                return output

            except Exception as e:
                sleep_time = BASE_WAIT * (2 ** attempt)

                if attempt < MAX_RETRIES - 1:
                    print(f"[Agent Error] {e}")
                    print(f"Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    return f"Failed after retries: {str(e)}"

    # =========================
    # HISTORY
    # =========================
    def get_chat_history(self) -> List[AnyMessage]:
        config = {"configurable": {"thread_id": self.thread_id}}
        return self.graph.get_state(config).values.get("messages", [])

    # =========================
    # VISUALIZE
    # =========================
    def visualize(self, filepath='workflow.png'):
        print(f'Visualise the agent workflow and saved it in {filepath}')
        self.graph.get_graph().draw_mermaid_png(
            output_file_path=filepath
        )

    # =========================
    # THREAD CONTROL
    # =========================
    def set_thread(self, thread_id: str):
        self.thread_id = thread_id