import re
import time
import uuid
import json
from typing import TypedDict, Annotated, Optional

from langgraph.graph import END, StateGraph, START
from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from core.llm import GEMINI, HUGGINGFACE, setup_model, HUGGINGFACE_LITE
from core.utils import FallbackLoggingHandler

# Settings for Exponential Retry
MAX_RETRIES = 5
BASE_WAIT = 10

class AgentState(TypedDict):
    """Agent state for the graph."""
    input_file: Optional[str]
    messages: Annotated[list[AnyMessage], add_messages]

class TriggerRAG(BaseModel):
    """Call this when you need to retrieve document context or use RAG."""
    query: str = Field(description="The search query for the knowledge base")

class Agent:
    def __init__(self, tools, sys_prompt, keywords, extract=True, name=''):
        print('Setting up the primary LLM as Gemini and backup LLM as Qwen')
        primary_llm = setup_model(GEMINI, callbacks=[FallbackLoggingHandler()])
        backup_llm = setup_model(HUGGINGFACE)
        self.llm  = primary_llm.with_fallbacks(
            fallbacks=[backup_llm],
        )

        self.tools = ToolNode(tools)
        self.llm_with_tools = self.llm.bind_tools(tools)
        self.sys_prompt = sys_prompt
        
        print('Building the agent ... ...')
        self.graph = self._graph_compile_()
        self.thread_id = str(uuid.uuid4())
        
        self.keywords = keywords
        self.extract = extract
        self.name = name

    def _graph_compile_(self):
        builder = StateGraph(AgentState)
        builder.add_node("tools", self.tools)
        builder.add_node("assistant", self._assistant_)
        builder.add_node("rag", self._rag_)

        builder.add_edge(START, "assistant")
        builder.add_conditional_edges(
            "assistant",
            self.rag_router,
            {
                "tools": "tools",
                "rag": "rag",
                END: END
            },
        )
        builder.add_edge("tools", "assistant")
        builder.add_edge("rag", "assistant")

        graph = builder.compile(checkpointer=MemorySaver())
        return graph
    
    def rag_router(self, state: AgentState):
        last_message = state["messages"][-1]
        
        if not last_message.tool_calls:
            return END # No tools called? The agent is done. Stop immediately.
        
        # Check if the specific RAG tool was called
        if last_message.tool_calls[0]["name"] == "TriggerRAG":
            return "rag"
            
        return "tools" # Otherwise, it's a normal tool

    def _assistant_(self, state: AgentState) -> dict: # -> Call models
        sys_msg = SystemMessage(content=self.sys_prompt)
        response = self.llm_with_tools.invoke([sys_msg] + state["messages"])
        return {
            "messages": [response], 
            "input_file": state.get("input_file", None)
        }

    def _rag_(self, state) -> dict:
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
        return {
            "messages": [response],
            "input_file": state.get("input_file", None)
        }
    
    def extract_after_final_answer(self, text: str) -> str:
        # re.findall finds every instance of { ... }
        # [^}]* ensures we don't accidentally skip over nested structures
        matches = re.findall(r'(\{.*?\})', text, re.DOTALL)
        if not matches:
            return None
        
        # We take the last match [-1]
        last_json_str = matches[-1]
        
        if not self.extract:
            return last_json_str

        try:
            # Replace single quotes with double quotes for valid JSON
            valid_json_str = last_json_str.replace("'", '"')
            data = json.loads(valid_json_str)
            output = ""
            for keyword in self.keywords:
                output += f"{keyword}: {data.get(keyword, "Nothing mentioned HERE")}"
            return output
        except json.JSONDecodeError:
            print(f'Could not fetch the keywords: {self.keywords} with the given response: {text}')
            return None

    def __call__(self, human_message: str) -> str:
        # Formulate the payload exactly how your StateGraph expects it
        payload = {
            "messages": [{"role": "user", "content": human_message}]
        }

        for attempt in range(MAX_RETRIES):
            try:
                # Invoke the graph
                response = self.graph.invoke(payload, config={"configurable": {"thread_id": self.thread_id}})
                
                # Extract the text content safely from the final state messgae
                final_message_content = response['messages'][-1].content
                final_ans = self.extract_after_final_answer(final_message_content) if self.extract else final_message_content
                return final_ans
            
            except Exception as e:
                # Exponential backoff calculation: 2s, 4s, 8s, 16s...
                sleep_time = BASE_WAIT * (2 ** attempt) 
                
                if attempt < MAX_RETRIES - 1:
                    print(f"Error: {str(e)}")
                    print(f"Attempt {attempt + 1} failed. Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    return f"Error processing query after {MAX_RETRIES} attempts: {str(e)}"

    def visualize(self):
        print('Visualise the agent workflow and saved it in workflow.png')
        self.graph.get_graph().draw_mermaid_png(output_file_path="workflow.png")

    def get_chat_history(self) -> list[str]:
        config = {"configurable": {"thread_id": self.thread_id}}
        return self.graph.get_state(config).values["messages"]
    
    def set_thread(self, thread_id: str):
        self.thread_id = thread_id