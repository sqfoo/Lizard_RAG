
FINANCIAL_CENTRAL_TEMPLATE =  """
The Available helpers for you: {helpers}

User request: {user_request}

WORLD News: {news}

STOCK Analysis: {stock_analysis}

History
{history}

Latest helper output: {helper_output}

Latest validation: {validation_output}

Decide ONE action.

Return EXACTLY in this JSON format.

{{"NEXT"=<helper_name>, "TASK"=<task>}}

or

{{"NEXT"="END", "ANSWER"=<final answer>}}
"""

FINANCIAL_HELPER_TEMPLATE =  """
WORLD News: {news}

STOCK Analysis: {stock_analysis}

Based on the additional information above, perform the Current Task: {current_task}
"""

VALIDATE_TEMPLATE = """
Validate the following information based on the given task:

Task: {current_task}
Response: {helper_output}

Identify:
- mistakes
- unsupported claims
- inconsistencies
- confidence

Return EXACTLY in this JSON format:

{{"VALID": true}}

or

{{"VALID": false, "REASON": "<one short sentence>"}}
"""