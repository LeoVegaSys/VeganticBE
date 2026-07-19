import os
import requests
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from mcp_config import STEP_LLMS

load_dotenv()

class LLMManager:
    def __init__(self):
        # self.llm = ChatOpenAI(model="gpt-4o", temperature=0)
        self._llms_map = {}
        self._register_llms()
        # self.llm = ChatOllama(model="llama3.2", temperature=0)

    def _register_llms(self):
        try:
            for step, model_name in STEP_LLMS:
                _llm = ChatOllama(model=model_name)
                self._llms_map[step] = _llm
        except Exception as e:
            print(f"Error encountered while instatiating LLM : {str(e)}")

    def invoke(self, prompt: ChatPromptTemplate, step_name: str, **kwargs) -> str:
        messages = prompt.format_messages(**kwargs)
        response = self._llms_map[step_name].invoke(messages)
        return response.content
    

class LLMManager_REST:
    def __init__(self, user_url: str = ""):
        self._stream: bool = False
        self._keep_alive: str = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
        self._timeout: int = int(os.environ.get("QA_TIMEOUT", 180))
        self._host:str = os.environ.get("OLLAMA_HOST", "localhost")
        self._port:int = int(os.environ.get("OLLAMA_PORT", 11434))
        self._url:str = user_url if user_url else f"http://{self._host}:{self._port}/api/generate"
        self._model:str = os.environ.get("QA_MODEL")

    def call(
            self,
            url:str = None,
            model: str = None,
            prompt: str = None,
            stream: bool = False,
            keep_alive: str = None,
            temperature: float = 0.0,
            timeout: int = 0,
            warmup: bool = False,
    ):
        req_url = url if url else self._url
        req_timeout = timeout if timeout else self._timeout
        
        log_model = model if model else self._model
        action_type = "warmup" if warmup else "request"

        req_json = {}
        req_json["model"] = log_model
        req_json["prompt"] = prompt if prompt else "ok"
        req_json["stream"] = stream if stream else self._stream
        req_json["keep_alive"] = keep_alive if keep_alive else self._keep_alive
        if temperature:
            req_json["temperature"] = temperature

        try:
            if warmup:
                requests.post(
                    url=req_url,
                    json=req_json,
                    timeout=req_timeout
                )
                print(f"Model {log_model} warmed up")
            else:
                resp = requests.post(
                    url=req_url,
                    json=req_json,
                    timeout=req_timeout
                )
                resp.raise_for_status()
                return resp.json()["response"]
        except Exception as e:
            print(f"Issue encountered during {action_type} : {e}")
            
