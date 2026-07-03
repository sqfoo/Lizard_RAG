import json
import uuid 
import time
import re
import random
from datetime import datetime
from typing import TypedDict, Literal, Annotated, List

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from core.agent import Agent


# ============================================================
# STATE
# ============================================================

class HoxState(TypedDict):
    user_request: str
    current_task: str
    helper_output: str
    validation_output: str
    final_answer: str
    next_node: str
    history: Annotated[list[str], list.__add__]
    iteration: int 


# ============================================================
# MULTI AGENT SYSTEM
# ============================================================

# Settings for Exponential Retry
MAX_RETRIES = 5
BASE_WAIT = 10

class Hox:
    def __init__(
        self,
        central_agent: Agent,
        helper_agents: dict[str, Agent],
        validate_agent: Agent,
        central_template: str,
        validate_template: str,
        thread: str = None
    ):

        self.central = central_agent
        self.helpers = helper_agents
        self.validator = validate_agent

        self.central_template = central_template
        self.validate_template = validate_template

        print('Building Hox System ... ...')
        self.graph = self._build_graph()
        self.history = []
        self.set_thread(str(uuid.uuid4()) if thread is None else thread)


    # --------------------------------------------------------

    def _build_graph(self):
        builder = StateGraph(HoxState)
        
        builder.add_node("central", self.central_node)
        builder.add_node("helper", self.helper_node)
        builder.add_node("validate", self.validate_node)

        builder.add_edge(START, "central")
        builder.add_conditional_edges(
            "central",
            self.route_from_central,
            {
                "helper": "helper",
                "end": END,
            },
        )

        builder.add_edge("helper", "validate")
        builder.add_edge("validate", "central")

        return builder.compile(checkpointer=MemorySaver())

    # ========================================================
    # CENTRAL
    # ========================================================

    def central_node(self, state: HoxState):
        
        prompt = self.central_template.format(
            user_request=state["user_request"],
            history=state["history"],
            helper_output=state["helper_output"],
            validation_output=state["validation_output"],
            helpers=str(list(self.helpers.keys()))
        )

        response = self.central(prompt)
        print(f"Central Node's Response: {response}")
        history = state["history"] + [response]

        self.history.append(
            {
                'role': 'central',
                'timestamp': datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
                'response': response
            }
        )
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", response, re.DOTALL)

        if match:
            resp = json.loads(match.group(1))
        else:
            resp = json.loads(response)

        next = resp.get('NEXT', 'END')

        # End the Agent Call
        if next.upper()=='END':
            print(f'End of the Agent Workflow')
            answer = resp['ANSWER']
            return {
                "history": history,
                "next_node": "end",
                "final_answer": answer,
            }

        # Direct to Helper
        helper = next if next in self.helpers.keys() else 'END'
        task = resp.get('TASK', '')

        if helper == 'END':
            print(f'Failed to call a valid helper, so would end the process and run {task}')
        else:
            print(f'Call {helper} to run {task} ... ')
        
        time.sleep(BASE_WAIT * random.uniform(0, 1.0))
        return {
            "history": history,
            "next_node": helper,
            "current_task": task,
            "iteration": state.get('iteration', 0) + 1
        }

    # ========================================================
    # HELPER
    # ========================================================

    def helper_node(self, state: HoxState):

        helper_name = state["next_node"]
        helper = self.helpers[helper_name]
        result = helper(state["current_task"])
        print(f"Helper's response: {result}")
        self.history.append(
            {
                'role': f'Helper-{helper_name}',
                'timestamp': datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
                'response': result
            }
        )

        time.sleep(BASE_WAIT * random.uniform(0, 1.0))
        return {
            "helper_output": result,
            "history": state["history"] + [
                f"{helper_name}: {result}"
            ],
            "iteration": state.get('iteration', 0)
        }

    # ========================================================
    # VALIDATOR
    # ========================================================

    def validate_node(self, state: HoxState):
        msg = self.validate_template.format(
            current_task=state['current_task'],
            helper_output=state['helper_output']
        )

        validation = self.validator(msg)
        print(f"Validation's Result: {validation}")
        self.history.append(
            {
                'role': 'Validator',
                'timestamp': datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
                'response': validation
            }
        )
        
        time.sleep(BASE_WAIT * random.uniform(0, 1.0))
        return {
            "validation_output": validation.upper(),
            "history": state["history"] + [
                f"Validation: {validation}"
            ],
            "iteration": state.get('iteration', 0)
        }

    # ========================================================
    # ROUTER
    # ========================================================

    def route_from_central(self, state: HoxState) -> Literal["helper", "end"]:
        if state["next_node"] == "end" or state["iteration"] >= 5:
            return "end"
        return "helper"

    # ========================================================
    # RUN
    # ========================================================

    def __call__(self, user_request: str):
        payload = {
            "user_request": user_request,
            "history": [],
            "helper_output": "",
            "validation_output": "",
            "current_task": "",
            "next_node": "",
            "final_answer": "",
        }

        self.history.append(
            {
                'role': 'Human',
                'timestamp': datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
                'response': user_request
            }
        )

        for attempt in range(MAX_RETRIES):
            try:
                # Invoke the graph
                result = self.graph.invoke(
                    payload,
                    config={"configurable": {"thread_id": self.thread_id}},
                )
                return result.get("final_answer", "Failed to answer")
            
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
        self.central.set_thread(thread_id)
        self.validator.set_thread(thread_id)
        for helper in self.helpers.values():
            helper.set_thread(thread_id)


    # =========================
    # VISUALIZE
    # =========================
    def visualize(self):
        print('Visualise the agent workflow and saved it in workflow.png')
        self.graph.get_graph().draw_mermaid_png(
            output_file_path="hox.png"
        )

    def get_hox_chat_history(self):
        return self.history
    
    def save_chat(self, dir: str):
        with open(f'{dir}/hox_{self.thread_id}.txt', 'a') as f:
            # 1. Get the current epoch timestamp (float)
            timestamp = time.time()

            # 2. Convert to a readable string (e.g., "2026-06-02 21:33:58")
            readable_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

            f.write(f'Chat saved at {readable_time}\n')
            print('Saving the chat content')
            for chat in self.history:
                role, action_time, resp = chat.values()
                f.write(f'\n======= {role} Message =======\n')
                f.write(f'Timestamp: {action_time}\n')
                f.write(f'Response: {resp}\n')
        print(f'Save all chats in {dir}/hox_{self.thread_id}.txt')