export function roundToTickSize(price: number, tickSize: string): number {
  const tick = parseFloat(tickSize);
  const decimals = (tickSize.split('.')[1] || '').length;
  const roundedPrice = Math.round(price / tick) * tick;
  return parseFloat(roundedPrice.toFixed(decimals));
}

export function getLowestUnit(assetPrice: number): string {
  const decimalPlaces = assetPrice.toString().split('.')[1]?.length || 0;
  return (1 / Math.pow(10, decimalPlaces)).toString();
}
