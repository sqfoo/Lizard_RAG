import re
import json
import uuid
import time
from datetime import datetime
from typing import Literal, TypedDict, Annotated
from langgraph.graph import END, StateGraph, START
from langchain_core.messages import AnyMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages

from core.agent import Agent, AgentState
from core.prompts import GENERAL_PROMPT, CORE_PROMPT
from core.tools import *

TOOLBOX = [
    duckduck_websearch,
    visit_webpage,
    wiki_search,
    youtube_viewer,
    image_caption,
    run_python,
    multiply,
    add,
    subtract,
    divide,
    upload_new_source,
    fetch_existing_data
]

# Settings for Exponential Retry
MAX_RETRIES = 5
BASE_WAIT = 10

class AgentState(TypedDict):
    task: str                         # The main overall task
    helper_instruction: str           # Coordinator writes this for the helper
    helper_response: str              # Helper writes its output here
    messages: Annotated[list[AnyMessage], add_messages]    # (Optional) Global chat history
    final_decision: str               # Determine helper or end


class HOX:
    def __init__(self):
        print('Setting up the Core Agent ...')
        self.core = Agent(
            tools=[duckduck_websearch, visit_webpage, upload_new_source, fetch_existing_data], 
            sys_prompt=CORE_PROMPT, 
            keywords=["FINAL ANSWER", "SUGGESTION"],
            extract=False,
            name='core'
        )
        self.core_prompt = "[TASK]: {TASK} \n[RESPONSE]: {RESPONSE}"

        print('Setting up the Helper Agent ...')
        self.helper = Agent(
            tools=TOOLBOX,
            sys_prompt=GENERAL_PROMPT,
            keywords=["FINAL ANSWER"],
            extract=False,
            name='helper'
        )

        print('Building the system')
        self.graph = self._compile_()
        self.thread_id = str(uuid.uuid4())
        self.set_thread(self.thread_id)

        self.chat_history = []

    def _core_(self, state: AgentState):
        # 1. Check if this is the FIRST run or a SUBSEQUENT run
        helper_reply = state.get("helper_response", )
        
        if not helper_reply:
            # --- INITIALIZATION MODE ---
            # The helper hasn't run yet. Format the prompt for Workflow A (New Task)
            print(f'⚙️ [Core] Initializing Mode. Task: {state["task"]}')
            prompt_input = {
                "TASK": state["task"],
                "RESPONSE": ""  # Leave blank so the LLM knows it's initializing
            }
        else:
            # --- COORDINATION MODE ---
            # The helper just finished a subtask. Format for Workflow B (Evaluation)
            print(f'⚙️ [Core] Evaluating Helper Response.')
            prompt_input = {
                "TASK": state["helper_instruction"],
                "RESPONSE": helper_reply
            }
        
        # 2. Invoke your Coordinator LLM using the formatted prompt input
        # (Assuming you are using a LangChain PromptTemplate or string formatting)
        formatted_prompt = self.core_prompt.format(**prompt_input)
        llm_output = self.core(formatted_prompt)
        print(f'[Core LLM Raw Reply]: {llm_output}')

        # 3. Safe JSON parsing with fallback protection
        result = {"FINAL ANSWER": "FALSE", "SUGGESTION": ""}
        
        if not llm_output:
            # Fallback if the agent called a tool or returned None
            print("⚠️ [Core] Warning: Received empty response or tool execution. Forcing helper assignment.")
            result["SUGGESTION"] = f"Please process this task directly: {state['task']}"
        else:
            try:
                # Strip markdown code blocks if the LLM added them
                clean_content = str(llm_output).replace("```json", "").replace("```", "").strip()
                result = json.loads(clean_content)
            except Exception as e:
                print(f"❌ [Core] Failed to parse LLM JSON: {e}")
                # Fallback logic so simple math tasks like (1+1) get pushed to helper instead of crashing
                if not helper_reply:
                    result["SUGGESTION"] = f"Please solve this task: {state['task']}"
                else:
                    result["SUGGESTION"] = "The supervisor instruction was corrupt. Please continue updating."

        self.chat_history.append({
            'role': self.core.name,
            'timestamp': datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
            'task': f'[TASK]: {prompt_input["TASK"]} with helper response of {prompt_input["RESPONSE"]}',
            'response': f'[FINAL DECISION]: {str(result.get("FINAL ANSWER", "FALSE")).upper().strip()} with helper instruction of {result.get("SUGGESTION", "")}'
        })
        
        return {
            "helper_instruction": result.get("SUGGESTION", ""),
            "final_decision": str(result.get("FINAL ANSWER", "FALSE")).upper().strip()
        }
    
    def _helper_(self, state: AgentState):
        # CRITICAL: The helper must execute the SUBTASK, not the main task
        current_subtask = state["helper_instruction"]
        print(f'🤖 [Helper] Working on Subtask: {current_subtask}')
        
        # Run helper LLM or Tool logic using 'current_subtask'
        response = self.helper(current_subtask)
        print(f'🤖 [Helper] Completed work and respond {response}.')
        
        self.chat_history.append({
            'role': self.helper.name,
            'timestamp': datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
            'task': f'Subtask: {current_subtask}',
            'response': response
        })

        # Return the response back to the state
        return {
            "helper_instruction": current_subtask,
            "helper_response": response
        }
    
    def router_condition(self, state: AgentState) -> Literal["helper", "__end__"]:
        # Check the decision made by the core node
        if state.get("final_decision", "FALSE") == "TRUE":
            print("\n✅ [System]: Task complete. Exiting workflow...\n")
            return "__end__"
        
        print("\n🔄 [System]: Writer requested more info. Routing back to helper ...\n")
        return "helper"

    def _compile_(self):
        builder = StateGraph(AgentState)
        builder.add_node('core', self._core_)
        builder.add_node('helper', self._helper_)

        builder.add_edge(START, 'core')
        builder.add_conditional_edges(
            'core',
            self.router_condition,
            {'helper': 'helper', '__end__': END}
        )
        builder.add_edge('helper', 'core')

        graph = builder.compile(checkpointer=MemorySaver())
        return graph

    def extract_after_final_answer(self, text: str) -> str:
        # re.findall finds every instance of { ... }
        # [^}]* ensures we don't accidentally skip over nested structures
        matches = re.findall(r'(\{.*?\})', text, re.DOTALL)
        if not matches:
            return None
        
        # We take the last match [-1]
        last_json_str = matches[-1].strip()
        
        try:
            # Replace single quotes with double quotes for valid JSON
            data = json.loads(last_json_str)
            output = ""
            for keyword in self.keywords:
                output += f"{keyword}: {data.get(keyword, "Nothing mentioned HERE")}\n"
            return output
        except json.JSONDecodeError:
            print(f'Could not fetch the keywords: {self.keywords} with the given response: {text}')
            return None
    
    def __call__(self, human_message: str) -> str:
        # Formulate the payload exactly how your StateGraph expects it
        payload = {
            "messages": [{"role": "user", "content": human_message}], 
            "task": human_message,
            "helper_response": "",
            "final_decision": "FALSE"
        }

        self.chat_history.append({
            'role': 'User/Human',
            'timestamp': datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
            'task': f'Main Task: {human_message}',
            'response': ''
        })

        for attempt in range(MAX_RETRIES):
            try:
                # Invoke the graph
                response = self.graph.invoke(payload, config={"configurable": {"thread_id": self.thread_id}})
                
                # # Extract the text content safely from the final state messgae
                # final_message_content = response['messages'][-1].content
                # final_ans = self.extract_after_final_answer(final_message_content)
                # return final_ans
                if response.get("final_decision") == "TRUE":
                    return f"### Final Task Output:\n{response.get('helper_instruction')}"
                else:
                    return f"System exited without completion. Last Suggestion: {response.get('helper_instruction')}"
            

            except Exception as e:
                # Exponential backoff calculation: 2s, 4s, 8s, 16s...
                sleep_time = BASE_WAIT * (2 ** attempt) 
                
                if attempt < MAX_RETRIES - 1:
                    print(f"Error: {str(e)}")
                    print(f"Attempt {attempt + 1} failed. Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    return f"Error processing query after {MAX_RETRIES} attempts: {str(e)}"

    def set_thread(self, thread_id):
        self.thread_id = thread_id
        self.core.set_thread(thread_id)
        self.helper.set_thread(thread_id)

    def visualize(self):
        print('Visualise the setup of HOX and saved it in hox.png')
        self.graph.get_graph().draw_mermaid_png(output_file_path="hox.png")

    def get_hox_chat_history(self) -> List[dict]:
        return self.chat_history
    