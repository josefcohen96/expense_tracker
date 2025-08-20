export const by = (id) => document.getElementById(id);
export const labels = (arr, key='month') => arr.map(x => x[key]);
export const values = (arr, key='expenses') => arr.map(x => x[key]);
export function readJSONScript(id) {
  const el = by(id);
  return el ? JSON.parse(el.textContent) : null;
}
