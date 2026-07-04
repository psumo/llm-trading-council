"""
GLM 客户端实现
==============

智谱 GLM 使用 OpenAI 兼容 API。
"""

from .openai_client import OpenAIClient


class GLMClient(OpenAIClient):
    """
    GLM 客户端

    使用智谱开放平台的 OpenAI 兼容接口。
    """

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    DEFAULT_MODEL = "glm-4-flash"
    PROVIDER = "glm"
