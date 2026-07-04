"""
DeepSeek 客户端实现
==================

DeepSeek 使用 OpenAI 兼容 API，只需修改默认配置。
"""

from .openai_client import OpenAIClient


class DeepSeekClient(OpenAIClient):
    """
    DeepSeek 客户端
    
    继承 OpenAI 客户端，使用 OpenAI 兼容 API。
    """
    
    DEFAULT_BASE_URL = "https://api.deepseek.com"
    DEFAULT_MODEL = "deepseek-chat"
    PROVIDER = "deepseek"
