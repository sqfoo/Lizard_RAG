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
from core.finance import Fox
from core.finance import FINANCIAL_CENTRAL_TEMPLATE, NEWS_HELPER_TEMPLATE, STOCK_HELPER_TEMPLATE, VALIDATE_TEMPLATE, REPORT_FORMATTER_TEMPLATE

EMPTY_PROMPT = ""

from core.tools import *

central_agent = Agent(
    primary_LLM=HUGGINGFACE,
    backup_LLM=HUGGINGFACE,
    tools=[duckduck_websearch, fetch_existing_data],
    sys_prompt=EMPTY_PROMPT,
    name="Centroid"
)

validate_agent = Agent(
    primary_LLM=HUGGINGFACE,
    backup_LLM=HUGGINGFACE,
    tools=[duckduck_websearch, fetch_existing_data],
    sys_prompt=EMPTY_PROMPT,
    name="Validator"
)

helpers = {
    'brief-stock': Agent(
        primary_LLM=GEMINI,
        backup_LLM=HUGGINGFACE,
        tools=[
            get_historical_prices,
            get_company_fundamentals,
            get_financial_statements,
            get_dividend_history,
            run_technical_analysis,
            upload_new_source,
            fetch_existing_data,
        ],
        sys_prompt=EMPTY_PROMPT,
        name="Stock Helper"
    ),
    'news': Agent(
        primary_LLM=HUGGINGFACE,
        backup_LLM=HUGGINGFACE,
        tools=[
            duckduck_websearch,
            visit_webpage,
            get_market_indices,
            upload_new_source,
            fetch_existing_data,
        ],
        sys_prompt=EMPTY_PROMPT,
        name="News Seeker"
    ),
    'report': Agent(
        primary_LLM=GEMINI,
        backup_LLM=HUGGINGFACE,
        tools=[
            duckduck_websearch,
            fetch_existing_data
        ],
        sys_prompt=EMPTY_PROMPT,
        name="Report Formatter"
    )
}

helper_templates = {
    'brief-stock': STOCK_HELPER_TEMPLATE,
    'news': NEWS_HELPER_TEMPLATE,
    'report': REPORT_FORMATTER_TEMPLATE
}

fox = Fox(
    central_agent=central_agent,
    helper_agents=helpers,
    validate_agent=validate_agent,
    central_template=FINANCIAL_CENTRAL_TEMPLATE,
    validate_template=VALIDATE_TEMPLATE,
    helper_template=helper_templates
)

fox.visualize()

human_msg = "Based on today's news, suggest what stocks to track and why"
resp = fox(human_msg)
print(f'Agent Response: {resp}')
print('-'*20)

fox.save_chat('chats')