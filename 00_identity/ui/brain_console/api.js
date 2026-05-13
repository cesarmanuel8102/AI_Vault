export async function getJson(url) {
  const r = await fetch(url, { headers: { "Accept": "application/json" } });
  let data = null;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) {
    throw new Error((data && (data.detail || data.error)) || `HTTP ${r.status}`);
  }
  return data;
}

export async function postJson(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    body: JSON.stringify(body || {})
  });
  let data = null;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) {
    throw new Error((data && (data.detail || data.error)) || `HTTP ${r.status}`);
  }
  return data;
}