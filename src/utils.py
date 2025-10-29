import time
import os
from typing import Dict

def load_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def render_prompt(template: str, article: str, extras: Dict = None) -> str:
    text = template.replace("{{ARTICLE}}", article)
    if extras:
        for k, v in extras.items():
            text = text.replace(f"{{{{{k}}}}}", str(v))
    return text

def retry_backoff(func, max_retries=5, base=1.0, exceptions=(Exception,), **kwargs):
    """Simple backoff wrapper: calls func(**kwargs) with retries on exception.
    Returns func result or raises last exception.
    """
    last_exc = None
    for i in range(max_retries):
        try:
            return func(**kwargs)
        except exceptions as e:
            last_exc = e
            wait = base * (2 ** i)
            time.sleep(wait)
    raise last_exc
