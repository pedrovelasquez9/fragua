// The figure of a stat card at `grow` (0 → 1) of its count-up, written the way
// the author typed it. A single "." or "," followed by 1-2 digits is a decimal
// separator ("1.4%", "1,4 %"); anything else is thousands grouping ("30.000").
// Kept free of imports so test_pipeline.py can run it with plain Node.
export const countUp = (raw: string, grow: number): string => {
  const numeric = raw.match(/^(\D*)(\d[\d.,]*)(\D*)$/);
  if (!numeric) return raw;
  const [, before, figure, after] = numeric;
  const decimal = figure.match(/^(\d+)([.,])(\d{1,2})$/);
  if (decimal) {
    const [, whole, separator, fraction] = decimal;
    const value = (Number(`${whole}.${fraction}`) * grow).toFixed(fraction.length);
    return `${before}${value.replace(".", separator)}${after}`;
  }
  const grouping = figure.match(/[.,]/)?.[0];
  const value = Math.round(Number(figure.replace(/[.,]/g, "")) * grow);
  const text = grouping
    ? String(value).replace(/\B(?=(\d{3})+$)/g, grouping)
    : value.toLocaleString("es-ES");
  return `${before}${text}${after}`;
};
