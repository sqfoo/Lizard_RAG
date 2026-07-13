import time
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openrouter import ChatOpenRouter
from langchain_core.runnables import Runnable
from langchain_core.messages import AIMessage

BASE_WAIT = 5

HUGGINGFACE = {
    'type': 'huggingface',
    'param':{
        'repo_id': "Qwen/Qwen2.5-7B-Instruct",
        'task': 'text-generation',
        'max_new_tokens': 2048,
        'do_sample': False,
        'repetition_penalty': 1.03,
        'provider': 'auto',
    },
    'model': 'huggingface:Qwen2.5-7B-Instruct',
}

HUGGINGFACE_LARGE = {
    'type': 'huggingface',
    'param':{
        'repo_id': "Qwen/Qwen2.5-14B-Instruct",
        'task': 'text-generation',
        'max_new_tokens': 2048,
        'do_sample': False,
        'repetition_penalty': 1.03,
        'provider': 'auto',
    },
    'model': 'huggingface:Qwen2.5-14B-Instruct',
}


HUGGINGFACE_LITE = {
    'type': 'huggingface-lite',
    'param':{
        'repo_id': "Qwen/Qwen2.5-1.5B-Instruct",
        'task': 'text-generation',
        'max_new_tokens': 2048,
        'do_sample': False,
        'repetition_penalty': 1.03,
        'provider': 'auto',
    },
    'model': 'huggingface:Qwen2.5-1.5B-Instruct',
}

GEMINI = {
    "type": "gemini",
    "param": {
        "model": "gemini-2.5-flash",
        "max_tokens": 8192,
        "max_retries": 0,
        "disable_streaming": True
    }
}

GEMINI_LITE = {
    "type": "gemini-lite",
    "param": {
        "model": "gemini-2.5-flash-lite",
        "max_tokens": 8192,
        "max_retries": 0,
    }
}

OPEN_ROUTE_SONNET = {
    "type": "open_router-free",
    "param": {
        # "model": "anthropic/claude-sonnet-4.5",
        "model": "openrouter/free",
        "temperature": 0,
        "max_tokens": 8192,
        "max_retries": 0,
    }
}

valid_LLM = [HUGGINGFACE_LARGE, GEMINI, GEMINI_LITE, HUGGINGFACE, HUGGINGFACE_LITE, OPEN_ROUTE_SONNET]

def setup_model(config: dict, callbacks=None):
    if config['type'].startswith('huggingface'):
        llm = HuggingFaceEndpoint(**config['param'])
        model = ChatHuggingFace(
            llm=llm, 
            callbacks=callbacks
        )
    elif config['type'].startswith('gemini'):
        model = ChatGoogleGenerativeAI(
            **config['param'], 
            callbacks=callbacks
        )
    elif config['type'].startswith('open_router'):
        model = ChatOpenRouter(
            **config['param'], 
            callbacks=callbacks
        )
    else:
        model = None
    return model


class FailoverLLM(Runnable):
    def __init__(self, primary, backup, retry, exceptions=(Exception,)):
        self.primary = primary
        self.backup = backup
        self.exceptions = exceptions
        self.retry = retry

    def invoke(self, input, config=None, **kwargs):

        try:
            print('Befor Invoke')
            resp = self.primary.invoke(
                input,
                config=config,
                **kwargs
            )
        except self.exceptions as e:
            print("After invoke")
            print(f"Primary failed: {type(e).__name__}, Now we redirect to Backup LLM")


            for attempt in range(1, self.retry+1):
                try:
                    resp = self.backup.invoke(
                        input,
                        config=config,
                        **kwargs
                    )
                except Exception as e:
                    sleep_time = BASE_WAIT * (2 ** attempt)
                    
                    if attempt < self.retry - 1:
                        print(f"Backup failed with error: {str(e)}")
                        print(f"Attempt {attempt + 1} failed. Retrying in {sleep_time} seconds...")
                        time.sleep(sleep_time)
                    else:
                        return f"Error processing query after {self.retry} attempts: {str(e)}"
        
        return get_content(resp)

        
def get_content(response):
    if isinstance(response, AIMessage):
        return response.content
    elif isinstance(response, str):
        return response
    
    return response