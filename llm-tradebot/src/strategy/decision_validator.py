"""
决策验证器
验证 LLM 决策的合法性和安全性
"""

from typing import Dict, List, Tuple, Optional
from src.utils.logger import log
from src.utils.action_protocol import normalize_action, VALID_ACTIONS, OPEN_ACTIONS


class DecisionValidator:
    """
    决策验证器
    
    验证规则：
    1. 必填字段检查
    2. 数值范围检查
    3. 止损方向检查
    4. 风险回报比检查
    5. 数值格式检查
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # 默认配置
        self.max_leverage = self.config.get('max_leverage', 5)
        self.max_position_pct = self.config.get('max_position_pct', 30.0)
        self.min_confidence = self.config.get('min_confidence', 0)
        self.max_confidence = self.config.get('max_confidence', 100)
        self.min_risk_reward_ratio = self.config.get('min_risk_reward_ratio', 2.0)
        
    def validate(self, decision: Dict) -> Tuple[bool, List[str]]:
        """
        验证决策
        
        Args:
            decision: 决策字典
            
        Returns:
            (is_valid, errors)
            - is_valid: 是否通过验证
            - errors: 错误列表
        """
        errors = []
        
        # 1. 必填字段检查（所有 action 类型都需要）
        required_fields = ['symbol', 'action', 'reasoning']
        for field in required_fields:
            if field not in decision:
                errors.append(f"缺少必填字段: {field}")
        
        # 如果基本字段缺失，直接返回
        if errors:
            return False, errors
        
        # 2. action 合法性检查（统一动作协议）
        decision['action'] = normalize_action(
            decision.get('action'),
            position_side=decision.get('position_side')
        )
        if decision['action'] not in VALID_ACTIONS:
            errors.append(f"无效的 action: {decision['action']}")
        
        # 3. confidence 检查（如果存在）
        if 'confidence' in decision:
            confidence = decision.get('confidence', 0)
            if not (self.min_confidence <= confidence <= self.max_confidence):
                errors.append(f"confidence 超出范围 [{self.min_confidence}, {self.max_confidence}]: {confidence}")
        
        # 4. 格式验证（所有字段）
        format_errors = self._validate_format(decision)
        errors.extend(format_errors)
        
        # 5. 开仓操作的额外检查
        if decision['action'] in OPEN_ACTIONS:
            # 5.1 开仓必填字段
            open_required = ['leverage', 'position_size_usd', 'stop_loss', 'take_profit']
            for field in open_required:
                if field not in decision or decision[field] is None:
                    errors.append(f"开仓操作缺少必填字段: {field}")
            
            # 如果缺少开仓字段，跳过后续检查
            if any('开仓操作缺少必填字段' in e for e in errors):
                return False, errors
            
            # 5.2 杠杆范围检查
            leverage = decision.get('leverage', 1)
            if not (1 <= leverage <= self.max_leverage):
                errors.append(f"leverage 超出范围 [1, {self.max_leverage}]: {leverage}")
            
            # 5.3 仓位大小检查（如果有 position_size_pct）
            if 'position_size_pct' in decision:
                position_pct = decision['position_size_pct']
                if not (0 <= position_pct <= self.max_position_pct):
                    errors.append(f"position_size_pct 超出范围 [0, {self.max_position_pct}]: {position_pct}")
            
            # 5.4 数值格式检查（不能是字符串公式）
            numeric_fields = ['leverage', 'position_size_usd', 'stop_loss', 'take_profit', 'risk_usd']
            for field in numeric_fields:
                if field in decision:
                    value = decision[field]
                    if isinstance(value, str):
                        errors.append(f"{field} 不能是字符串（可能包含公式）: {value}")
                    elif not isinstance(value, (int, float)):
                        errors.append(f"{field} 必须是数字: {value}")
            
            # 5.5 止损方向检查
            if not self.validate_stop_loss_direction(decision):
                action = decision['action']
                entry = decision.get('entry_price', decision.get('current_price', 0))
                stop_loss = decision.get('stop_loss', 0)
                if action == 'open_long':
                    errors.append(f"做多止损方向错误: stop_loss ({stop_loss}) 必须 < entry_price ({entry})")
                elif action == 'open_short':
                    errors.append(f"做空止损方向错误: stop_loss ({stop_loss}) 必须 > entry_price ({entry})")
            
            # 5.6 风险回报比检查
            if not self.validate_risk_reward_ratio(decision):
                ratio = self.calculate_risk_reward_ratio(decision)
                errors.append(f"风险回报比不足: {ratio:.2f} < {self.min_risk_reward_ratio}")
        
        return len(errors) == 0, errors
    
    def _validate_format(self, decision: Dict) -> List[str]:
        """
        验证数值格式
        
        检查规则：
        1. 禁止范围符号 ~
        2. 禁止千位分隔符 ,
        
        Args:
            decision: 决策字典
            
        Returns:
            错误列表
        """
        errors = []
        
        for key, value in decision.items():
            if isinstance(value, str):
                # 检查范围符号
                if '~' in value:
                    errors.append(f"字段 {key} 包含禁止的范围符号 '~': {value}")
                
                # 检查千位分隔符（在数字上下文中）
                import re
                if re.match(r'^\d{1,3}(,\d{3})+(\.\d+)?$', value):
                    errors.append(f"字段 {key} 包含禁止的千位分隔符 ',': {value}")
        
        return errors
    
    def validate_stop_loss_direction(self, decision: Dict) -> bool:
        """
        验证止损方向
        
        规则：
        - 做多: stop_loss < entry_price
        - 做空: stop_loss > entry_price
        
        Args:
            decision: 决策字典
            
        Returns:
            True if valid, False otherwise
        """
        action = normalize_action(
            decision.get('action'),
            position_side=decision.get('position_side')
        )
        
        # 只检查开仓操作
        if action not in OPEN_ACTIONS:
            return True
        
        # 获取价格
        entry_price = decision.get('entry_price') or decision.get('current_price')
        stop_loss = decision.get('stop_loss')
        
        # 如果缺少价格信息，无法验证
        if entry_price is None or stop_loss is None:
            return True
        
        # 验证方向
        if action == 'open_long':
            return stop_loss < entry_price
        elif action == 'open_short':
            return stop_loss > entry_price
        
        return True
    
    def validate_risk_reward_ratio(self, decision: Dict) -> bool:
        """
        验证风险回报比
        
        要求: (take_profit - entry) / (entry - stop_loss) >= min_ratio
        
        Args:
            decision: 决策字典
            
        Returns:
            True if valid, False otherwise
        """
        ratio = self.calculate_risk_reward_ratio(decision)
        
        if ratio is None:
            return True  # 无法计算时不拦截
        
        return ratio >= self.min_risk_reward_ratio
    
    def calculate_risk_reward_ratio(self, decision: Dict) -> Optional[float]:
        """
        计算风险回报比
        
        Args:
            decision: 决策字典
            
        Returns:
            风险回报比，如果无法计算返回 None
        """
        action = normalize_action(
            decision.get('action'),
            position_side=decision.get('position_side')
        )
        
        # 只计算开仓操作
        if action not in OPEN_ACTIONS:
            return None
        
        # 获取价格
        entry_price = decision.get('entry_price') or decision.get('current_price')
        stop_loss = decision.get('stop_loss')
        take_profit = decision.get('take_profit')
        
        # 如果缺少价格信息，无法计算
        if None in [entry_price, stop_loss, take_profit]:
            return None
        
        # 计算风险和收益
        if action == 'open_long':
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
        elif action == 'open_short':
            risk = abs(stop_loss - entry_price)
            reward = abs(entry_price - take_profit)
        else:
            return None
        
        # 避免除零
        if risk == 0:
            return None
        
        return reward / risk
    
    def get_validation_summary(self, decision: Dict) -> str:
        """
        获取验证摘要（用于日志）
        
        Args:
            decision: 决策字典
            
        Returns:
            验证摘要字符串
        """
        is_valid, errors = self.validate(decision)
        
        if is_valid:
            summary = f"✅ 决策验证通过: {decision.get('action', 'unknown')}"
            
            # 添加关键信息
            if decision.get('action') in OPEN_ACTIONS:
                ratio = self.calculate_risk_reward_ratio(decision)
                if ratio:
                    summary += f", 风险回报比: {ratio:.2f}"
        else:
            summary = f"❌ 决策验证失败: {len(errors)} 个错误\n"
            for i, error in enumerate(errors, 1):
                summary += f"  {i}. {error}\n"
        
        return summary


# 测试代码
if __name__ == '__main__':
    validator = DecisionValidator()
    
    # 测试用例 1: 有效的做多决策
    test1 = {
        'symbol': 'BTCUSDT',
        'action': 'open_long',
        'confidence': 75,
        'leverage': 2,
        'position_size_usd': 200.0,
        'entry_price': 86000.0,
        'stop_loss': 84710.0,  # 正确：低于入场价
        'take_profit': 88580.0,  # 正确：高于入场价
        'risk_usd': 30.0
    }
    
    is_valid, errors = validator.validate(test1)
    print("测试 1 - 有效的做多决策:")
    print(f"  验证结果: {'通过' if is_valid else '失败'}")
    if errors:
        print(f"  错误: {errors}")
    ratio = validator.calculate_risk_reward_ratio(test1)
    print(f"  风险回报比: {ratio:.2f}")
    print()
    
    # 测试用例 2: 止损方向错误
    test2 = {
        'symbol': 'BTCUSDT',
        'action': 'open_long',
        'confidence': 75,
        'leverage': 2,
        'position_size_usd': 200.0,
        'entry_price': 86000.0,
        'stop_loss': 87000.0,  # 错误：高于入场价
        'take_profit': 88580.0,
        'risk_usd': 30.0
    }
    
    is_valid, errors = validator.validate(test2)
    print("测试 2 - 止损方向错误:")
    print(f"  验证结果: {'通过' if is_valid else '失败'}")
    if errors:
        print(f"  错误: {errors}")
    print()
    
    # 测试用例 3: 风险回报比不足
    test3 = {
        'symbol': 'BTCUSDT',
        'action': 'open_long',
        'confidence': 75,
        'leverage': 2,
        'position_size_usd': 200.0,
        'entry_price': 86000.0,
        'stop_loss': 84000.0,
        'take_profit': 87000.0,  # 风险回报比 = 1000/2000 = 0.5 < 2.0
        'risk_usd': 30.0
    }
    
    is_valid, errors = validator.validate(test3)
    print("测试 3 - 风险回报比不足:")
    print(f"  验证结果: {'通过' if is_valid else '失败'}")
    if errors:
        print(f"  错误: {errors}")
    ratio = validator.calculate_risk_reward_ratio(test3)
    print(f"  风险回报比: {ratio:.2f}")
