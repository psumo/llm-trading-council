/**
 * Use with Array.sort(descendingOrder) to sort a number array descending
 */
export function descendingOrder(a: number, b: number): number {
  return Number(b) - Number(a);
}

/**
 * Merge two arrays into one and remove duplicates
 */
export function mergeDedupeArrays<TAny>(a: TAny[], b: TAny[], predicate = (a: TAny, b: TAny) => a === b): TAny[] {
  const c = structuredClone(a); // copy to avoid side effects
  // add all items from B to copy C if they're not already present
  b.forEach((bItem) => (c.some((cItem) => predicate(bItem, cItem)) ? null : c.push(bItem)));
  return c;
}
