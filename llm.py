from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_google_genai import ChatGoogleGenerativeAI
import langchain_google_genai.chat_models as google_chat_module

# Create a clean pass-through function that denies tenacity execution
def bypass_chat_retry(generation_method, **kwargs):
    return generation_method(**kwargs)

# Overwrite LangChain's internal retry function entirely
google_chat_module._chat_with_retry = bypass_chat_retry
print("🚫 Global LangChain Gemini retry mechanism deactivated.")


HUGGINGFACE = {
    'type': 'huggingface',
    'param':{
        'repo_id': "Qwen/Qwen2.5-7B-Instruct",

        'task': 'text-generation',
        'max_new_tokens': 512,
        'do_sample': False,
        'repetition_penalty': 1.03,
        'provider': 'auto',
    },
    'model': 'huggingface:Qwen2.5-7B-Instruct',
}

GEMINI = {
    "type": "gemini",
    "param": {
        "model": "gemini-2.5-flash",
        # "model": "gemini-2.5-flash-lite",
        "max_tokens": 512,
        "max_retries": 0,
        "timeout": 0.0
    }
}

def setup_model(config: dict, callbacks=None):
    if config['type'] == 'huggingface':
        llm = HuggingFaceEndpoint(**config['param'])
        model = ChatHuggingFace(llm=llm, callbacks=callbacks)
    elif config['type'] in ['gemini']:
        model = ChatGoogleGenerativeAI(**config['param'], callbacks=callbacks)
    else:
        model = None
    return model