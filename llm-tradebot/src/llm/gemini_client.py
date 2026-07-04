"""
Google Gemini 客户端实现
=======================

Gemini 使用 Google AI API，格式与 OpenAI 不同。
"""

from typing import Dict, Any, List
from .base import BaseLLMClient, LLMConfig, ChatMessage, LLMResponse


class GeminiClient(BaseLLMClient):
    """
    Google Gemini 客户端
    
    Gemini API 特点：
    - 使用 API key 作为 URL 参数
    - 消息格式使用 parts 而非 content
    - 端点结构不同
    """
    
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    DEFAULT_MODEL = "gemini-1.5-flash"
    PROVIDER = "gemini"
    
    def _build_headers(self) -> Dict[str, str]:
        """Gemini 使用简单的 Content-Type 头"""
        return {
            "Content-Type": "application/json"
        }
    
    def _build_url(self) -> str:
        """Gemini API URL 包含 model 和 api_key"""
        return f"{self.base_url}/models/{self.model}:generateContent?key={self.config.api_key}"
    
    def _build_request_body(
        self, 
        messages: List[ChatMessage],
        **kwargs
    ) -> Dict[str, Any]:
        """
        构建 Gemini 请求体
        
        Gemini 格式：
        - contents: [{role: "user", parts: [{text: "..."}]}]
        - systemInstruction: {parts: [{text: "..."}]}
        """
        contents = []
        system_instruction = None
        
        for msg in messages:
            if msg.role == "system":
                system_instruction = {
                    "parts": [{"text": msg.content}]
                }
            else:
                # Gemini 使用 "model" 代替 "assistant"
                role = "model" if msg.role == "assistant" else msg.role
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}]
                })
        
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "maxOutputTokens": kwargs.get("max_tokens", self.config.max_tokens)
            }
        }
        
        if system_instruction:
            body["systemInstruction"] = system_instruction
        
        return body
    
    def _parse_response(self, response: Dict[str, Any]) -> LLMResponse:
        """解析 Gemini 响应"""
        content = ""
        
        candidates = response.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                content = parts[0].get("text", "")
        
        # Gemini usage 格式不同
        usage_metadata = response.get("usageMetadata", {})
        usage = {
            "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
            "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
            "total_tokens": usage_metadata.get("totalTokenCount", 0)
        }
        
        return LLMResponse(
            content=content,
            model=self.model,
            provider=self.PROVIDER,
            usage=usage,
            raw_response=response
        )
