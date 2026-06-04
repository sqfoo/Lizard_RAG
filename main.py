from dotenv import load_dotenv
import time
from datetime import datetime


load_dotenv(dotenv_path="../.env") # Remove this when git push

import os
# 1. Silence the 'absl' logging warning
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

# 2. Silence gRPC internal error messages 
os.environ['GRPC_VERBOSITY'] = 'ERROR'

# 3. Prevent the 'init.cc' timeout message from showing
os.environ['GLOG_minloglevel'] = '2'

from agent import Agent
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
    And also suggests three possible follow-up steps to the current task if the task is open.

    Always wrap your final answer in the exact JSON format: {"FINAL ANSWER": "YOUR WORD", "SUGGESTION": "YOUR SUGGESTION"}
"""

agent = Agent(tools=TOOLBOX, sys_prompt=SYS_PROMT)
agent.visualize()

keep = True
while keep:
    keep = input("Keep Running?") in ['Y', 'y', 'Yes', 'yes']
    input_message = input("Human Message:")

    resp = agent(input_message)
    print(resp)
    print('=================================')

print("\n>>>>>----------------------<<<<<\n")

chat_history = agent.get_chat_history()

with open('ctx.txt', 'a') as f:
    # 1. Get the current epoch timestamp (float)
    timestamp = time.time()

    # 2. Convert to a readable string (e.g., "2026-06-02 21:33:58")
    readable_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

    f.write(f'Chat saved at {readable_time}\n')
    print('Saving the chat content')
    for message in chat_history:
        # Determine the sender type (HumanMessage, AIMessage, SystemMessage)
        sender = message.__class__.__name__.replace("Message", "")
        
        # Write to the file
        f.write(f"=== {sender} ===\n")
        f.write(f"{message.content}\n\n")

database.save()