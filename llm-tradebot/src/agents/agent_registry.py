"""
Agent Registry Module
======================

Centralized registry for agent management.
Provides lazy initialization, enable/disable control, and agent discovery.
"""

from typing import Dict, Optional, Type, Any, List
from src.agents.agent_config import AgentConfig
from src.agents.base_agent import BaseAgent
from src.utils.logger import log


class AgentRegistry:
    """
    Centralized registry for agent management.
    
    Features:
    - Lazy agent initialization
    - Enable/disable control via AgentConfig
    - Agent discovery and listing
    - Dependency-aware initialization
    
    Usage:
        config = AgentConfig.from_dict(yaml_config)
        registry = AgentRegistry(config)
        
        # Register agent classes
        registry.register_class('predict_agent', PredictAgent)
        
        # Get initialized agent (returns None if disabled)
        agent = registry.get('predict_agent')
        if agent:
            result = await agent.execute(input_data)
    """
    
    def __init__(self, config: AgentConfig):
        """
        Initialize registry with configuration.
        
        Args:
            config: AgentConfig instance with enable/disable settings
        """
        self.config = config
        self._agent_classes: Dict[str, Type[BaseAgent]] = {}
        self._agent_instances: Dict[str, BaseAgent] = {}
        self._init_args: Dict[str, Dict[str, Any]] = {}
    
    def register_class(
        self, 
        name: str, 
        agent_class: Type[BaseAgent],
        init_args: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register an agent class for lazy initialization.
        
        Args:
            name: Agent name (snake_case, e.g., 'predict_agent')
            agent_class: Agent class to instantiate
            init_args: Optional initialization arguments
        """
        self._agent_classes[name] = agent_class
        if init_args:
            self._init_args[name] = init_args
        log.debug(f"Registered agent class: {name}")
    
    def register_instance(self, name: str, agent: BaseAgent) -> None:
        """
        Register an already-initialized agent instance.
        
        Args:
            name: Agent name
            agent: Agent instance
        """
        self._agent_instances[name] = agent
        log.debug(f"Registered agent instance: {name}")
    
    def is_enabled(self, name: str) -> bool:
        """
        Check if an agent is enabled in configuration.
        
        Args:
            name: Agent name
            
        Returns:
            True if enabled, False otherwise
        """
        return self.config.is_enabled(name)
    
    def get(self, name: str) -> Optional[BaseAgent]:
        """
        Get an agent by name.
        
        Returns None if:
        - Agent is disabled in config
        - Agent is not registered
        
        Args:
            name: Agent name
            
        Returns:
            Agent instance or None
        """
        # Check if enabled
        if not self.is_enabled(name):
            log.debug(f"Agent '{name}' is disabled in config")
            return None
        
        # Check if already instantiated
        if name in self._agent_instances:
            return self._agent_instances[name]
        
        # Lazy initialize
        if name in self._agent_classes:
            return self._initialize_agent(name)
        
        log.warning(f"Agent '{name}' is not registered")
        return None
    
    def _initialize_agent(self, name: str) -> Optional[BaseAgent]:
        """
        Initialize an agent from registered class.
        
        Args:
            name: Agent name
            
        Returns:
            Initialized agent instance or None on error
        """
        try:
            agent_class = self._agent_classes[name]
            init_args = self._init_args.get(name, {})
            agent = agent_class(**init_args)
            self._agent_instances[name] = agent
            log.info(f"✅ Initialized agent: {name}")
            return agent
        except Exception as e:
            log.error(f"Failed to initialize agent '{name}': {e}")
            return None
    
    def initialize_all(self) -> Dict[str, bool]:
        """
        Initialize all enabled agents.
        
        Returns:
            Dict of agent names to initialization success status
        """
        results = {}
        for name in self._agent_classes:
            if self.is_enabled(name):
                agent = self._initialize_agent(name)
                results[name] = agent is not None
            else:
                results[name] = False  # Disabled
                log.info(f"⏭️ Skipped disabled agent: {name}")
        return results
    
    def list_agents(self, enabled_only: bool = False) -> List[str]:
        """
        List registered agent names.
        
        Args:
            enabled_only: If True, only return enabled agents
            
        Returns:
            List of agent names
        """
        all_agents = list(set(self._agent_classes.keys()) | set(self._agent_instances.keys()))
        if enabled_only:
            return [name for name in all_agents if self.is_enabled(name)]
        return all_agents
    
    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all registered agents.
        
        Returns:
            Dict with agent status information
        """
        status = {}
        for name in self.list_agents():
            status[name] = {
                'enabled': self.is_enabled(name),
                'initialized': name in self._agent_instances,
                'class_registered': name in self._agent_classes,
            }
        return status
    
    def __contains__(self, name: str) -> bool:
        """Check if agent is registered"""
        return name in self._agent_classes or name in self._agent_instances
    
    def __len__(self) -> int:
        """Return number of registered agents"""
        return len(self.list_agents())
    
    def __repr__(self) -> str:
        enabled = len(self.list_agents(enabled_only=True))
        total = len(self)
        return f"<AgentRegistry(enabled={enabled}/{total})>"
