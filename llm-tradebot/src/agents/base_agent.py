"""
Base Agent Module
==================

Provides abstract base class for all agents with standardized interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, TypeVar, Optional
from dataclasses import dataclass

# Type variables for generic input/output
InputT = TypeVar('InputT')
OutputT = TypeVar('OutputT')


@dataclass
class AgentResult:
    """Standard result wrapper for agent outputs"""
    success: bool
    data: Any
    error: Optional[str] = None
    agent_name: str = ""
    
    def __bool__(self) -> bool:
        return self.success


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """
    Abstract base class for all agents.
    
    Provides standardized interface for:
    - Naming and identification
    - Execution with typed input/output
    - Optional agent marking
    - Input/output schema documentation
    
    Usage:
        class MyAgent(BaseAgent[MyInput, MyOutput]):
            @property
            def name(self) -> str:
                return "my_agent"
            
            async def execute(self, input_data: MyInput) -> MyOutput:
                # Implementation
                pass
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Agent name for logging and configuration.
        Should be snake_case, e.g., 'predict_agent', 'regime_detector_agent'
        """
        pass
    
    @property
    def display_name(self) -> str:
        """Human-readable agent name for UI display"""
        # Convert snake_case to Title Case
        return ' '.join(word.capitalize() for word in self.name.split('_'))
    
    @property
    def is_optional(self) -> bool:
        """
        Whether this agent can be disabled.
        Override to return False for core agents.
        """
        return True
    
    @property
    def is_core(self) -> bool:
        """Inverse of is_optional for clarity"""
        return not self.is_optional
    
    @abstractmethod
    async def execute(self, input_data: InputT) -> OutputT:
        """
        Execute agent logic.
        
        Args:
            input_data: Typed input for the agent
            
        Returns:
            Typed output from the agent
        """
        pass
    
    def execute_sync(self, input_data: InputT) -> OutputT:
        """
        Synchronous wrapper for execute.
        Uses asyncio.run() for compatibility with sync code.
        """
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # If already in async context, create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.execute(input_data))
                return future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(self.execute(input_data))
    
    def get_input_schema(self) -> Dict[str, Any]:
        """
        Return expected input schema for documentation.
        Override in subclass to provide schema.
        """
        return {"description": "No schema defined"}
    
    def get_output_schema(self) -> Dict[str, Any]:
        """
        Return expected output schema for documentation.
        Override in subclass to provide schema.
        """
        return {"description": "No schema defined"}
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, optional={self.is_optional})>"
