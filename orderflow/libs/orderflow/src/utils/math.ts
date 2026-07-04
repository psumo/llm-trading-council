type MathOperators = '+' | '-' | 'min' | 'max';

/**
 * Perform a math operation on a property shared by two objects.
 * This assumes that property is always a number!
 */
export function doMathOnProp<TLeftObj, TRightObj extends TLeftObj>(
  leftObject: TLeftObj,
  rightObject: TRightObj,
  prop: keyof TLeftObj,
  operator: MathOperators
): number {
  const left = leftObject[prop] as number;
  const right = rightObject[prop] as number;
  switch (operator) {
    case '+':
      return left + right;
    case '-':
      return left - right;
    case 'max':
      return Math.max(left, right);
    case 'min':
      return Math.min(left, right);
    default: {
      throw new Error('unhandled operator');
    }
  }
}
