"""
OpenAI 客户端实现
================

支持 OpenAI API 及所有兼容 OpenAI API 格式的提供商。
"""

from typing import Dict, Any, List
from .base import BaseLLMClient, LLMConfig, ChatMessage, LLMResponse


class OpenAIClient(BaseLLMClient):
    """
    OpenAI 客户端
    
    也可作为兼容 OpenAI API 的其他提供商的基类。
    """
    
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "gpt-4o"
    PROVIDER = "openai"
    
    def _build_headers(self) -> Dict[str, str]:
        """构建 OpenAI 认证头"""
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }
    
    def _build_request_body(
        self, 
        messages: List[ChatMessage],
        **kwargs
    ) -> Dict[str, Any]:
        """构建 OpenAI 请求体"""
        return {
            "model": self.model,
            "messages": self._messages_to_list(messages),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens)
        }
    
    def _parse_response(self, response: Dict[str, Any]) -> LLMResponse:
        """解析 OpenAI 响应"""
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        
        return LLMResponse(
            content=message.get("content", ""),
            model=response.get("model", self.model),
            provider=self.PROVIDER,
            usage=response.get("usage", {}),
            raw_response=response
        )
