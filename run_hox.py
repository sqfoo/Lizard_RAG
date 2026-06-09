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

from core.hox import HOX
from core.tools import *
from core.database import database

agent = HOX()
agent.visualize()

keep = True

while keep:
    keep = input("Keep Running?") in ['Y', 'y', 'Yes', 'yes']
    input_message = input("Human Message: ")

    resp = agent(input_message)
    verify = f'TASK: {input_message}; RESPONSE: {resp}'
    print(f'Agent Response: {resp}')
    print('-'*20)
    

chat_history = agent.get_hox_chat_history()
print('*'*20)

with open('chats/hox_ctx.txt', 'a') as f:
    # 1. Get the current epoch timestamp (float)
    timestamp = time.time()

    # 2. Convert to a readable string (e.g., "2026-06-02 21:33:58")
    readable_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

    f.write(f'Chat saved at {readable_time}\n')
    print('Saving the chat content')

    for chat in chat_history:
        role, timestamp, task, response = chat.values()
        f.write(f'\n======= {role} Message =======\n')
        f.write(f'at {timestamp}\n')
        f.write(f'To Do: {task}\n')
        f.write(f'Response: {response}\n')

database.save()
