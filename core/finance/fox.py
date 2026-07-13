import re
import uuid
import json
import time
import random
from datetime import datetime
from typing import TypedDict, Literal, Annotated, List, Dict, Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from core.agent import Agent

# ============================================================
# STATE
# ============================================================

class ValidationOutput(TypedDict):
    valid: bool
    reason: str


class AgentArtifact(TypedDict):
    agent: str
    type: str
    data: Any
    validation: ValidationOutput | None
    iteration: int

class FinalReport(TypedDict):
    title: str
    content: str

class WorkflowState(TypedDict):
    user_request: str
    current_task: str
    next_node: str
    iteration: int
    final_report: FinalReport

class FoxState(TypedDict):
    workflow: WorkflowState
    memory: Dict[str, List[AgentArtifact]]
    history: List[str]


# ============================================================
# FOX ENGINE
# ============================================================

BASE_WAIT = 10

class Fox:
    def __init__(
        self,
        central_agent: Agent,
        helper_agents: dict[str, Agent],
        validate_agent: Agent,
        central_template: str,
        helper_template: dict,
        validate_template: str,
        max_iterations: int = 10,
    ):
        self.central = central_agent
        self.helpers = helper_agents
        self.validator = validate_agent

        self.central_template = central_template
        self.helper_template = helper_template
        self.validate_template = validate_template

        self.max_iterations = max_iterations

        self.graph = self._build_graph()
        self.history = []
        self.thread_id = str(uuid.uuid4())

    # --------------------------------------------------------
    # GRAPH
    # --------------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(FoxState)

        graph.add_node("central", self.central_node)
        graph.add_node("helper", self.helper_node)
        graph.add_node("validate", self.validate_node)

        graph.add_edge(START, "central")

        graph.add_conditional_edges(
            "central",
            self.route,
            {"helper": "helper", "end": END},
        )

        graph.add_edge("helper", "validate")
        graph.add_edge("validate", "central")

        return graph.compile(checkpointer=MemorySaver())

    # --------------------------------------------------------
    # CENTRAL
    # --------------------------------------------------------

    def central_node(self, state: FoxState):
        memory = state["memory"]
        workflow = state["workflow"]

        prompt = self.central_template.format(
            user_request=workflow["user_request"],
            memory=json.dumps(memory, indent=2),
            history="\n".join(state["history"][-5:]),
            last_called=workflow.get("next_node", "")
        )

        response = self.central(prompt)

        print(f"Central Node's Response: {response}")
        result = self._parse_json(response)

        next_node = result.get("NEXT", "END")
        task = result.get("TASK", "")
        answer = result.get("final_report", {}) or workflow.get("final_report", {}) # Need to fix this
        workflow["iteration"] += 1

        state["history"].append(response)
        self.add_msg(
            'central',
            datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
            response
        )

        if next_node.upper() == "END":
            workflow["final_report"] = answer
            workflow["next_node"] = "end"

            return {
                "workflow": workflow,
                "history": state["history"],
                "final_report": answer
            }

        workflow["next_node"] = next_node
        workflow["current_task"] = task

        time.sleep(BASE_WAIT * random.uniform(0, 1.0))
        return {
            "workflow": workflow,
            "history": state["history"],
        }

    # --------------------------------------------------------
    # HELPER
    # --------------------------------------------------------
    def helper_node(self, state: FoxState):

        workflow = state["workflow"]
        helper_name = workflow["next_node"].lower()
        helper = self.helpers[helper_name]

        if "report" in helper_name:
            prompt = self.helper_template[helper_name].format(
                memory=json.dumps(state["memory"], indent=2),
                current_task=workflow["current_task"],
                history='\n'.join(state['history'])
            )
        else:
            prompt = self.helper_template[helper_name].format(
                memory=json.dumps(state["memory"], indent=2),
                current_task=workflow["current_task"]
            )

        raw = helper(prompt)

        print(f"Helper-{helper_name}'s response: {raw}")
        self.add_msg(
            f'Helper-{helper_name}',
            datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
            raw
        )
        result = self._parse_json(raw)

        if 'stock' in helper_name:
            print(f'Reducing the memory context for executive purpose with Helper-{helper_name} ... ...')
            stocks = result["data"].get("stocks", [])
            ctx = [
                {
                    "stock": s,
                    "executive_summary": s["executive_summary"],
                }
                for s in stocks
            ]
            result = {
                'type': helper_name,
                'data': ctx
            }


        artifact = AgentArtifact(
            agent=helper_name,
            type=result.get("type", "unknown"),
            data=result.get("data", result),
            validation=None,
            iteration=workflow["iteration"],
        )

        memory = state["memory"]
        memory.setdefault(helper_name, []).append(artifact)

        state["history"].append(raw)
        workflow["final_report"] = result.get("data", {}) if "report" in helper_name else workflow["final_report"]

        time.sleep(BASE_WAIT * random.uniform(0, 1.0))
        return {
            "memory": memory,
            "history": state["history"],
            "workflow": workflow
        }

    # --------------------------------------------------------
    # VALIDATOR
    # --------------------------------------------------------

    def validate_node(self, state: FoxState):

        workflow = state["workflow"]
        memory = state["memory"]

        last_agent = workflow["next_node"]
        latest = memory[last_agent][-1]

        prompt = self.validate_template.format(
            task=workflow["current_task"],
            output=json.dumps(latest["data"])
        )

        raw = self.validator(prompt)
        self.add_msg(
            'Validator',
            datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'),
            raw
        )

        result = self._parse_json(raw)

        latest["validation"] = result
        print(f"Validator Node's Response: {result.get("valid", "false")} because {result.get("reason", "Failed to give")}")


        state["history"].append(raw)

        time.sleep(BASE_WAIT * random.uniform(0, 1.0))
        return {
            "memory": memory,
            "history": state["history"],
        }

    # --------------------------------------------------------
    # ROUTING
    # --------------------------------------------------------

    def route(self, state: FoxState) -> Literal["helper", "end"]:

        if state["workflow"]["iteration"] >= self.max_iterations:
            return "end"

        if state["workflow"].get("next_node") == "end":
            return "end"

        return "helper"

    # --------------------------------------------------------
    # JSON PARSER
    # --------------------------------------------------------

    def _parse_json(self, text: str) -> dict:
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(text)
        except Exception as e:
            print(f'Failed to convert text into JSON format, {str(e)}')
            return {}

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    def __call__(self, user_request: str) -> dict:

        state: FoxState = {
            "workflow": {
                "user_request": user_request,
                "current_task": "",
                "next_node": "",
                "iteration": 0,
                "final_report": {},
            },
            "memory": {},
            "history": [],
        }

        result = self.graph.invoke(
            state,
            config={"configurable": {"thread_id": self.thread_id}},
        )

        return result["workflow"].get("final_report", {})
    
    # =========================
    # VISUALIZE
    # =========================
    def visualize(self):
        print('Visualise the agent workflow and saved it in fox.png')
        self.graph.get_graph().draw_mermaid_png(
            output_file_path="fox.png"
        )

    def get_fox_chat_history(self):
        return self.history
    
    def save_chat(self, dir: str):
        with open(f'{dir}/fox_{self.thread_id}.txt', 'a') as f:
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
        print(f'Save all chats in {dir}/fox_{self.thread_id}.txt')

    def add_msg(self, role, timestamp, msg):
        self.history.append(
            {
                'role': role,
                'timestamp': timestamp,
                'response': msg
            }
        )
        print(f'Saved the response from {role}')