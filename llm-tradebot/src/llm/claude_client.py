"""
Claude 客户端实现
================

Anthropic Claude 使用不同的 API 格式，需要单独实现。
"""

from typing import Dict, Any, List
from .base import BaseLLMClient, LLMConfig, ChatMessage, LLMResponse


class ClaudeClient(BaseLLMClient):
    """
    Claude 客户端 (Anthropic API)
    
    Claude 使用不同的 API 格式：
    - 认证使用 x-api-key 而非 Bearer token
    - 端点是 /messages 而非 /chat/completions
    - system prompt 是独立字段
    """
    
    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
    PROVIDER = "claude"
    
    ANTHROPIC_VERSION = "2023-06-01"
    
    def _build_headers(self) -> Dict[str, str]:
        """构建 Anthropic 认证头"""
        return {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json"
        }
    
    def _build_url(self) -> str:
        """Claude 使用 /messages 端点"""
        return f"{self.base_url}/messages"
    
    def _build_request_body(
        self, 
        messages: List[ChatMessage],
        **kwargs
    ) -> Dict[str, Any]:
        """
        构建 Claude 请求体
        
        Claude 的 system prompt 是独立字段，不在 messages 中
        """
        # 提取 system message
        system_content = ""
        user_messages = []
        
        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                user_messages.append({"role": msg.role, "content": msg.content})
        
        body = {
            "model": self.model,
            "messages": user_messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens)
        }
        
        if system_content:
            body["system"] = system_content
        
        # Claude 不支持 temperature=0，最小值是 0.1
        temperature = kwargs.get("temperature", self.config.temperature)
        if temperature > 0:
            body["temperature"] = max(0.1, temperature)
        
        return body
    
    def _parse_response(self, response: Dict[str, Any]) -> LLMResponse:
        """解析 Claude 响应"""
        content = ""
        for block in response.get("content", []):
            if block.get("type") == "text":
                content = block.get("text", "")
                break
        
        return LLMResponse(
            content=content,
            model=response.get("model", self.model),
            provider=self.PROVIDER,
            usage=response.get("usage", {}),
            raw_response=response
        )
