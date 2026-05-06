from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_google_genai import ChatGoogleGenerativeAI

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
        "max_tokens": 512,
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