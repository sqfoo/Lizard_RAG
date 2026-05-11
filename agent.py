from typing import TypedDict, Annotated, Optional

from langgraph.graph import END, StateGraph, START
from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

class AgentState(TypedDict):
    """Agent state for the graph."""
    input_file: Optional[str]
    messages: Annotated[list[AnyMessage], add_messages]

class Agent:
    def __init__(self, llm, tools, sys_prompt):
        self.llm = llm
        self.tools = ToolNode(tools)
        self.llm_with_tools = self.llm.bind_tools(tools)
        self.sys_prompt = sys_prompt
        
        self.graph = self._graph_compile_()

    def _graph_compile_(self):
        builder = StateGraph(AgentState)
        builder.add_node("tools", self.tools)
        builder.add_node("assistant", self._assistant_)
        builder.add_node("generate", self._generate_)

        builder.set_entry_point("assistant")
        builder.add_conditional_edges(
            "assistant",
            tools_condition,
            {END: "generate", "tools": "tools"},
        )
        builder.add_edge("tools", "assistant")
        builder.add_edge("generate", END)

        graph = builder.compile(checkpointer=MemorySaver())
        return graph

    def _assistant_(self, state):
        sys_msg = SystemMessage(
            content=self.sys_prompt
        )
        return {
            "messages": [self.llm_with_tools.invoke([sys_msg] + state["messages"])],
            "input_file": state.get("input_file", None)
        }

    def _generate_(self, state):
        """Generate answer."""
        # Get generated ToolMessages
        recent_tool_messages = []
        for message in reversed(state["messages"]):
            if message.type == "tool":
                recent_tool_messages.append(message)
            else:
                break
        tool_messages = recent_tool_messages[::-1]

        # Format into prompt
        docs_content = "\n\n".join(doc.content for doc in tool_messages)
        system_message_content = (
            f"{self.sys_prompt}"
            "Use the following pieces of retrieved context to answer "
            "the question. If you don't know the answer, say that you "
            "don't know. Use three sentences maximum and keep the "
            "answer concise."
            "\n\n"
            f"{docs_content}"
        )
        conversation_messages = [
            message
            for message in state["messages"]
            if message.type in ("human", "system")
            or (message.type == "ai" and not message.tool_calls)
        ]
        prompt = [SystemMessage(system_message_content)] + conversation_messages

        # Run
        response = self.llm_with_tools.invoke(prompt)
        return {"messages": [response]}
    
    def __call__(self, human_message):
        for step in self.graph.stream(
            {"messages": [{"role": "user", "content": human_message}]},
            stream_mode="values",
            config={"configurable": {"thread_id": "abc123"}}
        ):
            step["messages"][-1].pretty_print()

    
    def visualize(self):
        self.graph.get_graph().draw_mermaid_png(output_file_path="workflow.png")