"""
MiniMax 客户端实现
==================

MiniMax 使用 OpenAI 兼容 API。
"""

from .openai_client import OpenAIClient


class MiniMaxClient(OpenAIClient):
    """
    MiniMax 客户端

    使用 MiniMax 平台的 OpenAI 兼容接口。
    """

    DEFAULT_BASE_URL = "https://api.minimax.io/v1"
    DEFAULT_MODEL = "MiniMax-M2.1"
    PROVIDER = "minimax"
