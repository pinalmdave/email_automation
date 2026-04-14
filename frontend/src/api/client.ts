const BASE = import.meta.env.VITE_API_BASE_URL || '';

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  // Ensure path ends with / to avoid 307 trailing-slash redirects on Azure
  const normalizedPath = path.includes('?') ? path : (path.endsWith('/') ? path : path + '/');
  const res = await fetch(`${BASE}${normalizedPath}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export { BASE as API_BASE };

