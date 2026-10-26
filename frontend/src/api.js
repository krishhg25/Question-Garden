let token = sessionStorage.getItem('qg-token') || '';
export function setToken(value) {
  token = value;
  if (value) sessionStorage.setItem('qg-token', value);
  else sessionStorage.removeItem('qg-token');
}
export function hasToken() { return Boolean(token); }

export async function api(path, options = {}) {
  const { raw, ...init } = options;
  const headers = { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers };
  if (init.body && !(init.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(init.body);
  }
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) {
    let message = 'The request failed. Please try again.';
    try {
      const body = await response.json();
      message = typeof body.detail === 'string' ? body.detail : body.detail?.map(e => e.msg).join('; ') || message;
    } catch { /* proxy may return a non-JSON error */ }
    if (response.status === 401) {
      setToken('');
      window.dispatchEvent(new Event('qg-signout'));
    }
    throw new Error(message);
  }
  return raw ? response : response.json();
}

export async function download(path, filename) {
  const response = await api(path, { raw: true });
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function requestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
