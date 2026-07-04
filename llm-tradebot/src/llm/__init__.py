"""
LLM 模块
========

提供统一的多 LLM 提供商接口。

支持的提供商：
- OpenAI (GPT-4, GPT-3.5)
- DeepSeek (deepseek-chat, deepseek-coder)
- Claude (Anthropic)
- Qwen (通义千问)
- Gemini (Google)
- Kimi (Moonshot)
- MiniMax
- GLM (智谱)

使用示例：

    from src.llm import create_client, LLMConfig

    # 创建 DeepSeek 客户端
    config = LLMConfig(api_key="sk-xxx", model="deepseek-chat")
    client = create_client("deepseek", config)
    
    # 发送请求
    response = client.chat(
        system_prompt="You are a helpful assistant",
        user_prompt="Hello!"
    )
    print(response.content)
"""

from .base import LLMConfig, BaseLLMClient, ChatMessage, LLMResponse
from .factory import create_client, get_supported_providers, register_provider

# 导出具体客户端类（便于类型检查和直接实例化）
from .openai_client import OpenAIClient
from .deepseek_client import DeepSeekClient
from .claude_client import ClaudeClient
from .qwen_client import QwenClient
from .gemini_client import GeminiClient
from .kimi_client import KimiClient
from .minimax_client import MiniMaxClient
from .glm_client import GLMClient

__all__ = [
    # 核心接口
    "LLMConfig",
    "BaseLLMClient",
    "ChatMessage",
    "LLMResponse",
    "create_client",
    "get_supported_providers",
    "register_provider",
    # 具体客户端
    "OpenAIClient",
    "DeepSeekClient",
    "ClaudeClient",
    "QwenClient",
    "GeminiClient",
    "KimiClient",
    "MiniMaxClient",
    "GLMClient",
]
