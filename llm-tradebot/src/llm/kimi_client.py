"""
Kimi 客户端实现
===============

Kimi (Moonshot AI) 使用 OpenAI 兼容 API。
"""

from .openai_client import OpenAIClient


class KimiClient(OpenAIClient):
    """
    Kimi 客户端

    使用 Moonshot 平台的 OpenAI 兼容接口。
    """

    DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"
    DEFAULT_MODEL = "moonshot-v1-8k"
    PROVIDER = "kimi"
