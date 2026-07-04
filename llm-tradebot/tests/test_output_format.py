#!/usr/bin/env python
"""
Test script for LLM output parser and decision validator
"""

import sys
sys.path.insert(0, '/Users/yunxuanhan/Documents/workspace/ai/LLM-TradeBot')

from src.strategy.llm_parser import LLMOutputParser
from src.strategy.decision_validator import DecisionValidator

def test_parser():
    print("=" * 60)
    print("Testing LLMOutputParser")
    print("=" * 60)
    
    parser = LLMOutputParser()
    
    # Test 1: Standard array format with ```json
    test1 = '''
<reasoning>
1h: EMA12 > EMA26, uptrend confirmed
15m: Break above resistance
5m: RSI pullback entry
</reasoning>

<decision>
```json
[{
  "symbol": "BTCUSDT",
  "action": "open_long",
  "leverage": 2,
  "position_size_usd": 200.0,
  "stop_loss": 84710.0,
  "take_profit": 88580.0,
  "confidence": 75,
  "reasoning": "Triple timeframe bullish alignment"
}]
```
</decision>
'''
    result1 = parser.parse(test1)
    print("\nTest 1 - Array format with ```json:")
    print(f"  Action: {result1['decision'].get('action')}")
    print(f"  Reasoning: {result1['decision'].get('reasoning')}")
    assert result1['decision'].get('action') == 'open_long', "Action should be open_long"
    print("  ✅ PASSED")
    
    # Test 2: Range symbol removal
    test2 = '<decision>[{"symbol": "BTCUSDT", "action": "wait", "stop_loss": "85000~86000", "reasoning": "test"}]</decision>'
    result2 = parser.parse(test2)
    print("\nTest 2 - Range symbol removal:")
    print(f"  stop_loss: {result2['decision'].get('stop_loss')}")
    assert result2['decision'].get('stop_loss') == "85000", "Range should be reduced to first value"
    print("  ✅ PASSED")
    
    # Test 3: Thousand separator removal
    test3 = '<decision>[{"symbol": "BTCUSDT", "action": "wait", "position_size_usd": "1,000", "reasoning": "test"}]</decision>'
    result3 = parser.parse(test3)
    print("\nTest 3 - Thousand separator removal:")
    print(f"  position_size_usd: {result3['decision'].get('position_size_usd')}")
    assert result3['decision'].get('position_size_usd') == "1000", "Thousand separator should be removed"
    print("  ✅ PASSED")
    
    # Test 4: Fallback on parse failure
    test4 = 'invalid json here'
    result4 = parser.parse(test4)
    print("\nTest 4 - Fallback on parse failure:")
    print(f"  Action: {result4['decision'].get('action')}")
    print(f"  Reasoning: {result4['decision'].get('reasoning')}")
    assert result4['decision'].get('action') == 'wait', "Should fallback to wait"
    print("  ✅ PASSED")
    
    # Test 5: Format validation
    print("\nTest 5 - Format validation:")
    is_valid1, err1 = parser.validate_format('[{"symbol": "BTC"}]')
    print(f"  Array format: {is_valid1}")
    assert is_valid1 == True, "Array format should be valid"
    
    is_valid2, err2 = parser.validate_format('{"symbol": "BTC"}')
    print(f"  Object format: {is_valid2}, error: {err2}")
    assert is_valid2 == False, "Object format should be invalid"
    
    is_valid3, err3 = parser.validate_format('[{"stop_loss": "85000~86000"}]')
    print(f"  Range symbol: {is_valid3}, error: {err3}")
    assert is_valid3 == False, "Range symbol should be invalid"
    print("  ✅ PASSED")

def test_validator():
    print("\n" + "=" * 60)
    print("Testing DecisionValidator")
    print("=" * 60)
    
    validator = DecisionValidator()
    
    # Test 1: Valid open_long decision
    test1 = {
        'symbol': 'BTCUSDT',
        'action': 'open_long',
        'leverage': 2,
        'position_size_usd': 200.0,
        'entry_price': 86000.0,
        'stop_loss': 84710.0,
        'take_profit': 88580.0,
        'confidence': 75,
        'reasoning': 'Triple timeframe bullish alignment'
    }
    is_valid, errors = validator.validate(test1)
    print("\nTest 1 - Valid open_long:")
    print(f"  Valid: {is_valid}")
    if errors:
        print(f"  Errors: {errors}")
    assert is_valid == True, f"Should be valid, got errors: {errors}"
    print("  ✅ PASSED")
    
    # Test 2: Missing reasoning field
    test2 = {
        'symbol': 'BTCUSDT',
        'action': 'wait',
        'confidence': 45
    }
    is_valid, errors = validator.validate(test2)
    print("\nTest 2 - Missing reasoning:")
    print(f"  Valid: {is_valid}")
    print(f"  Errors: {errors}")
    assert is_valid == False, "Should be invalid without reasoning"
    assert "reasoning" in str(errors), "Error should mention reasoning"
    print("  ✅ PASSED")
    
    # Test 3: Valid close_long (no open fields needed)
    test3 = {
        'symbol': 'BTCUSDT',
        'action': 'close_long',
        'confidence': 80,
        'reasoning': 'Take profit at target'
    }
    is_valid, errors = validator.validate(test3)
    print("\nTest 3 - Valid close_long:")
    print(f"  Valid: {is_valid}")
    if errors:
        print(f"  Errors: {errors}")
    assert is_valid == True, f"Should be valid, got errors: {errors}"
    print("  ✅ PASSED")
    
    # Test 4: Range symbol in field
    test4 = {
        'symbol': 'BTCUSDT',
        'action': 'wait',
        'confidence': 45,
        'reasoning': 'test',
        'stop_loss': '85000~86000'
    }
    is_valid, errors = validator.validate(test4)
    print("\nTest 4 - Range symbol detection:")
    print(f"  Valid: {is_valid}")
    print(f"  Errors: {errors}")
    assert is_valid == False, "Should be invalid with range symbol"
    assert "~" in str(errors), "Error should mention range symbol"
    print("  ✅ PASSED")

if __name__ == '__main__':
    try:
        test_parser()
        test_validator()
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
