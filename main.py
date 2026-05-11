from dotenv import load_dotenv
load_dotenv(dotenv_path="../.env") # Remove this when git push

import os
# 1. Silence the 'absl' logging warning
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

# 2. Silence gRPC internal error messages 
os.environ['GRPC_VERBOSITY'] = 'ERROR'

# 3. Prevent the 'init.cc' timeout message from showing
os.environ['GLOG_minloglevel'] = '2'

from agent import Agent
from llm import HUGGINGFACE, GEMINI, setup_model
from tools import *
from database import database

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

LLM = setup_model(GEMINI)

SYS_PROMT = """
    You are a helpful assistant tasked with answering questions using a set of tools. When given a question, follow these steps:
    1. Create a clear, step-by-step plan to solve the question.
    2. If a tool is necessary, select the most appropriate tool based on its functionality. If one tool isn't working, use another with similar functionality.
    3. For any real time information or up-to-date information, just use the web search tools.
    4. Execute your plan and provide the response in the following format:

    FINAL ANSWER: [YOUR FINAL ANSWER]

    Your final answer should be:

    - A number (without commas or units unless explicitly requested),
    - A short string (avoid articles, abbreviations, and use plain text for digits unless otherwise specified),
    - A comma-separated list (apply the formatting rules above for each element, with exactly one space after each comma).

    Ensure that your answer is concise and follows the task instructions strictly. If the answer is more complex, break it down in a way that follows the format.
    Begin your response with "FINAL ANSWER: " followed by the answer, and nothing else.

    And also suggests three possible follow-up steps to the current task by starting with: "SUGGESTION: ".
"""

agent = Agent(llm=LLM, tools=TOOLBOX, sys_prompt=SYS_PROMT)
agent.visualize()

# Specify an ID for the thread
config = {"configurable": {"thread_id": "abc123"}}

keep = True
while keep:
    keep = input("Keep Running?") in ['Y', 'y', 'Yes', 'yes']
    input_message = input("Human Message:")

    resp = agent(input_message)
    print(resp)
    print('=================================')

print("\n>>>>>----------------------<<<<<\n")
chat_history = agent.graph.get_state(config).values["messages"]

with open('ctx.txt', 'w') as f:
    for message in chat_history:
        message.pretty_print()

database.save()