export function computeZ(
  value: number,
  mean: number,
  std: number,
): number | null {
  if (std === 0) return null;
  return (value - mean) / std;
}
