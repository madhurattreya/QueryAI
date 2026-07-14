import os
import json
import urllib.request
import urllib.error
import time
from typing import List, Optional
import backend.config as config

class LLMManager:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LLMManager, cls).__new__(cls, *args, **kwargs)
            cls._instance.opener = urllib.request.build_opener()
        return cls._instance

    def call_model(self, model: str, prompt: str, temperature: float = 0.0) -> str:
        """
        Sends query directly to the specified model.
        """
        if "gemini" in model.lower():
            api_key = config.GEMINI_API_KEY
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set in .env. Please configure it to use Gemini.")
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            data = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": temperature
                }
            }
            req_data = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            # Set a standard timeout of 10s
            with self.opener.open(req, timeout=10) as res:
                response = json.loads(res.read().decode("utf-8"))
                return response["candidates"][0]["content"]["parts"][0]["text"]
        else:
            # Use local Ollama
            from ollama import chat
            response = chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": temperature}
            )
            return response["message"]["content"]

    def call_llm_with_fallback(self, prompt: str, primary_model: str, temperature: float = 0.0, fallback_list: Optional[List[str]] = None) -> tuple:
        """
        Runs LLM call with a fallback chain.
        Returns a tuple: (response_text, final_model_used)
        """
        if fallback_list is None:
            # Fallback list builder
            fallback_list = [primary_model]
            if "gemini" in primary_model.lower():
                fallback_list.extend(["qwen2.5:7b", "llama3:8b", "llama3.2", "qwen"])
            else:
                fallback_list.extend(["llama3:8b", "llama3.2", "qwen"])
                
        # Clean duplicates while keeping order
        seen = set()
        clean_fallback = [m for m in fallback_list if not (m in seen or seen.add(m))]
        
        last_error = None
        for model in clean_fallback:
            try:
                res = self.call_model(model, prompt, temperature)
                return res, model
            except Exception as e:
                print(f"[LLM FALLBACK WARNING] Model '{model}' failed: {str(e)}. Retrying next model...")
                last_error = e
                time.sleep(0.2)
                
        raise last_error or RuntimeError("All models in the fallback chain failed.")

# Main legacy entry point wrapper for backwards compatibility
def call_llm(prompt: str) -> str:
    model = config.settings.get("model", "qwen2.5:7b")
    manager = LLMManager()
    res, _ = manager.call_llm_with_fallback(prompt, model)
    return res
