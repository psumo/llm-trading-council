"""
Agent Configuration Module
===========================

Provides centralized configuration for optional agents.
Core agents (DataSyncAgent, QuantAnalystAgent, RiskAuditAgent) are always enabled.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Any


def _default_timeouts() -> Dict[str, float]:
    """Default timeout policy (seconds) for runtime agent tasks."""
    return {
        'quant_analyst': 25.0,
        'predict_agent': 30.0,
        'reflection_agent': 45.0,
        'semantic_agent': 35.0,
        'llm_perspective': 45.0,
    }


@dataclass
class AgentConfig:
    """
    Configuration for optional agents.
    
    Core agents are always enabled and not configurable:
    - DataSyncAgent: Market data fetching
    - QuantAnalystAgent: Technical analysis
    - RiskAuditAgent: Risk control
    
    Optional agents can be enabled/disabled via config.
    """
    
    # ML/AI Prediction Layer
    predict_agent: bool = True              # PredictAgent: ML probability prediction
    ai_prediction_filter_agent: bool = True  # AIPredictionFilterAgent: AI veto mechanism
    
    # Market Analysis
    regime_detector_agent: bool = True       # RegimeDetectorAgent: Market state detection
    position_analyzer_agent: bool = False    # PositionAnalyzerAgent: Price position analysis
    
    # Trigger Detection
    trigger_detector_agent: bool = True      # TriggerDetectorAgent: 5m pattern detection
    
    # LLM Semantic Analysis (expensive, disabled by default)
    trend_agent_llm: bool = False            # TrendAgentLLM: 1h trend LLM analysis
    setup_agent_llm: bool = False            # SetupAgentLLM: 15m setup LLM analysis
    trigger_agent_llm: bool = False          # TriggerAgentLLM: 5m trigger LLM analysis
    
    # Local Semantic Analysis (no LLM)
    trend_agent_local: bool = True           # TrendAgent: 1h trend rule-based analysis
    setup_agent_local: bool = True           # SetupAgent: 15m setup rule-based analysis
    trigger_agent_local: bool = True         # TriggerAgent: 5m trigger rule-based analysis
    
    # Trading Retrospection
    reflection_agent_llm: bool = False       # ReflectionAgentLLM: Trade reflection via LLM
    reflection_agent_local: bool = True      # ReflectionAgent: Rule-based reflection
    
    # Symbol Selection
    symbol_selector_agent: bool = True       # SymbolSelectorAgent: AUTO3/AUTO1 selection
    
    # Runtime policy
    timeouts: Dict[str, float] = field(default_factory=_default_timeouts)
    
    def __post_init__(self):
        """Validate dependencies between agents"""
        # AIPredictionFilterAgent requires PredictAgent
        if self.ai_prediction_filter_agent and not self.predict_agent:
            self.ai_prediction_filter_agent = False
        self.timeouts = self._normalize_timeouts(self.timeouts)

    @staticmethod
    def _normalize_timeouts(raw: Any) -> Dict[str, float]:
        """Normalize timeout config to a positive-float map."""
        normalized = _default_timeouts()
        if not isinstance(raw, dict):
            return normalized
        for key, value in raw.items():
            if key is None:
                continue
            name = str(key).strip()
            if not name:
                continue
            try:
                timeout_val = float(value)
            except (TypeError, ValueError):
                continue
            if timeout_val > 0:
                normalized[name] = timeout_val
        return normalized
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'AgentConfig':
        """
        Create AgentConfig from a dictionary (e.g., from config.yaml)
        
        Environment variables take priority over config values.
        Use AGENT_<NAME>=true/false to override, e.g., AGENT_PREDICT_AGENT=false
        
        Args:
            config: Dictionary with agent enable/disable settings
            
        Returns:
            AgentConfig instance
        """
        import os
        agents_config = config.get('agents', {})
        if not isinstance(agents_config, dict):
            agents_config = {}

        def get_value_optional(key: str) -> Optional[bool]:
            """Get value from env var (priority) or config or None if unset"""
            env_key = f"AGENT_{key.upper()}"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                return env_val.lower() in ('true', '1', 'yes', 'on')
            if key in agents_config:
                return agents_config.get(key)
            return None

        def resolve_flag(key: str, default: bool) -> bool:
            val = get_value_optional(key)
            if val is None:
                return default
            return bool(val)

        def resolve_llm_flag(new_key: str, legacy_key: str, default: bool) -> bool:
            val = get_value_optional(new_key)
            if val is not None:
                return bool(val)
            legacy_val = get_value_optional(legacy_key)
            if legacy_val is not None:
                return bool(legacy_val)
            return default

        def resolve_timeouts() -> Dict[str, float]:
            configured = agents_config.get('timeouts', {})
            merged = cls._normalize_timeouts(configured)
            keys = set(merged.keys()) | set((configured or {}).keys())
            for key in keys:
                env_key = f"AGENT_TIMEOUT_{str(key).upper()}"
                env_val = os.environ.get(env_key)
                if env_val is None:
                    continue
                try:
                    parsed = float(env_val)
                except (TypeError, ValueError):
                    continue
                if parsed > 0:
                    merged[str(key)] = parsed
            return merged
        
        # Map config keys to dataclass fields
        return cls(
            predict_agent=resolve_flag('predict_agent', True),
            ai_prediction_filter_agent=resolve_flag('ai_prediction_filter_agent', True),
            regime_detector_agent=resolve_flag('regime_detector_agent', True),
            position_analyzer_agent=resolve_flag('position_analyzer_agent', False),
            trigger_detector_agent=resolve_flag('trigger_detector_agent', True),
            trend_agent_llm=resolve_llm_flag('trend_agent_llm', 'trend_agent', False),
            setup_agent_llm=resolve_llm_flag('setup_agent_llm', 'setup_agent', False),
            trigger_agent_llm=resolve_llm_flag('trigger_agent_llm', 'trigger_agent', False),
            trend_agent_local=resolve_flag('trend_agent_local', True),
            setup_agent_local=resolve_flag('setup_agent_local', True),
            trigger_agent_local=resolve_flag('trigger_agent_local', True),
            reflection_agent_llm=resolve_llm_flag('reflection_agent_llm', 'reflection_agent', False),
            reflection_agent_local=resolve_flag('reflection_agent_local', True),
            symbol_selector_agent=resolve_flag('symbol_selector_agent', True),
            timeouts=resolve_timeouts(),
        )
    
    def is_enabled(self, agent_name: str) -> bool:
        """
        Check if an agent is enabled by name.
        
        Args:
            agent_name: Agent name (e.g., 'predict_agent', 'regime_detector_agent')
            
        Returns:
            True if enabled, False otherwise
        """
        # Convert CamelCase to snake_case if needed
        if not agent_name.endswith('_agent') and any(c.isupper() for c in agent_name):
            name = ''.join(['_' + c.lower() if c.isupper() else c for c in agent_name]).lstrip('_')
        else:
            name = agent_name
            
        return getattr(self, name, False)
    
    def get_enabled_agents(self) -> Dict[str, bool]:
        """Get dictionary of all agent enabled states"""
        return {
            'predict_agent': self.predict_agent,
            'ai_prediction_filter_agent': self.ai_prediction_filter_agent,
            'regime_detector_agent': self.regime_detector_agent,
            'position_analyzer_agent': self.position_analyzer_agent,
            'trigger_detector_agent': self.trigger_detector_agent,
            'trend_agent_llm': self.trend_agent_llm,
            'setup_agent_llm': self.setup_agent_llm,
            'trigger_agent_llm': self.trigger_agent_llm,
            'trend_agent_local': self.trend_agent_local,
            'setup_agent_local': self.setup_agent_local,
            'trigger_agent_local': self.trigger_agent_local,
            'reflection_agent_llm': self.reflection_agent_llm,
            'reflection_agent_local': self.reflection_agent_local,
            'symbol_selector_agent': self.symbol_selector_agent,
        }
    
    def __str__(self) -> str:
        enabled = [k for k, v in self.get_enabled_agents().items() if v]
        disabled = [k for k, v in self.get_enabled_agents().items() if not v]
        return f"AgentConfig(enabled={enabled}, disabled={disabled}, timeouts={self.timeouts})"

    def get_timeout(self, key: str, default: float) -> float:
        """Get normalized timeout for a runtime task."""
        try:
            val = float((self.timeouts or {}).get(key, default))
            if val > 0:
                return val
        except (TypeError, ValueError):
            pass
        return float(default)
