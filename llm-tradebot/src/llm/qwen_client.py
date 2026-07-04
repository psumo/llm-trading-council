"""
通义千问 (Qwen) 客户端实现
=========================

Qwen 使用 OpenAI 兼容 API (DashScope)。
"""

from .openai_client import OpenAIClient


class QwenClient(OpenAIClient):
    """
    通义千问客户端
    
    使用阿里云 DashScope 的 OpenAI 兼容模式。
    """
    
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_MODEL = "qwen-turbo"
    PROVIDER = "qwen"
