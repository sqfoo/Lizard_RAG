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

from core.llm import *
from core.agent import Agent
from core.hox import Hox
from core.tools import *
from core.database import database
from core.templates import CENTRAL_TEMPLATE, VALIDATE_TEMPLATE
from core.prompts import COORDINATOR_PROMPT, VALIDATE_PROMPT, HELPER_PROMPT

central_agent = Agent(
    primary_LLM=GEMINI,
    backup_LLM=HUGGINGFACE,
    tools=[duckduck_websearch,],
    sys_prompt=COORDINATOR_PROMPT
)

validate_agent = Agent(
    primary_LLM=GEMINI,
    backup_LLM=HUGGINGFACE,
    tools=[duckduck_websearch, run_python, multiply, add, subtract, divide, fetch_existing_data],
    sys_prompt=VALIDATE_PROMPT
)

helpers = {
    'assistant': Agent(
        primary_LLM=GEMINI,
        backup_LLM=HUGGINGFACE,
        tools=[
            duckduck_websearch,
            visit_webpage,
            youtube_viewer,
            image_caption,
            run_python,
            multiply,
            add,
            subtract,
            divide,
            upload_new_source,
            fetch_existing_data
        ],
        sys_prompt=HELPER_PROMPT
    )
}

hox = Hox(
    central_agent=central_agent,
    helper_agents=helpers,
    validate_agent=validate_agent,
    central_template=CENTRAL_TEMPLATE,
    validate_template=VALIDATE_TEMPLATE
)
hox.visualize()

keep = True

while keep:
    keep = input("Keep Running?") in ['Y', 'y', 'Yes', 'yes']
    input_message = input("Human Message: ")

    resp = hox(input_message)
    print(f'Agent Response: {resp}')
    print('-'*20)

hox.save_chat('chats')

database.save()
