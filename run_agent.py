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

from core.agent import Agent
from core.tools import *
from core.database import database
from core.prompts import GENERAL_PROMPT
from core.llm import GEMINI, GEMINI_LITE, HUGGINGFACE, HUGGINGFACE_LITE

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

agent = Agent(primary_LLM=GEMINI_LITE, backup_LLM=HUGGINGFACE_LITE, tools=TOOLBOX, sys_prompt=GENERAL_PROMPT, keywords=["FINAL ANSWER"], extract=True)
agent.visualize()

keep = True

while keep:
    keep = input("Keep Running?") in ['Y', 'y', 'Yes', 'yes']
    input_message = input("Human Message: ")

    resp = agent(input_message)
    verify = f'TASK: {input_message}; RESPONSE: {resp}'
    print(f'Agent Response: {resp}')
    print('-'*20)
    

chat_history = agent.get_chat_history()

with open('chats/ctx.txt', 'a') as f:
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