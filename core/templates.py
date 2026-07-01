CENTRAL_TEMPLATE = """
The Available helpers for you: {helpers}

User request: {user_request}

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