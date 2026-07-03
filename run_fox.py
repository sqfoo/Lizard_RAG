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
from core.prompts import FINANCIAL_COORDINATOR_PROMPT, FINANCIAL_VALIDATOR_PROMPT, ANALYST_PROMPT, NEWS_PROMPT

central_agent = Agent(
    primary_LLM=GEMINI,
    backup_LLM=HUGGINGFACE,
    tools=[duckduck_websearch,],
    sys_prompt=FINANCIAL_COORDINATOR_PROMPT
)

validate_agent = Agent(
    primary_LLM=GEMINI,
    backup_LLM=HUGGINGFACE,
    tools=[duckduck_websearch, fetch_existing_data],
    sys_prompt=FINANCIAL_VALIDATOR_PROMPT
)

helpers = {
    'Financial Analyst': Agent(
        primary_LLM=GEMINI,
        backup_LLM=HUGGINGFACE,
        tools=[
            duckduck_websearch,
            visit_webpage,
            get_historical_prices,
            get_company_fundamentals,
            get_financial_statements,
            get_dividend_history,
            run_technical_analysis,
            upload_new_source,
            fetch_existing_data,
            stock_news,
        ],
        sys_prompt=ANALYST_PROMPT
    ),
    'News Seeker': Agent(
        primary_LLM=GEMINI,
        backup_LLM=HUGGINGFACE,
        tools=[
            duckduck_websearch,
            visit_webpage,
            get_market_indices,
            # fetch_news,
            upload_new_source,
            fetch_existing_data,
        ],
        sys_prompt=NEWS_PROMPT
    ),
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

human_msg = "Based on today's news, suggest what stocks to track and why"
resp = hox(human_msg)
print(f'Agent Response: {resp}')
print('-'*20)

hox.save_chat('chats')

database.save()
