/**
 * Centralized API client for Hishabi frontend.
 *
 * All network calls go through this client to ensure consistent:
 * - Authorization Bearer token attachment
 * - Standard error normalization
 * - File streaming downloads
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'hishabi_token';
const USER_KEY = 'hishabi_user';

export const authStorage = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  getUser: () => {
    try {
      const u = localStorage.getItem(USER_KEY);
      return u ? JSON.parse(u) : null;
    } catch {
      return null;
    }
  },
  setAuth: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clearAuth: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

/**
 * Standard API request wrapper
 */
export async function apiRequest(endpoint, options = {}) {
  const token = authStorage.getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    authStorage.clearAuth();
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg =
      data?.error?.message || data?.detail?.message || data?.detail || 'Request failed';
    const err = new Error(errorMsg);
    err.status = response.status;
    err.code = data?.error?.code || 'ERROR';
    throw err;
  }

  return data;
}

/**
 * In-memory file download helper using Blob and browser trigger
 */
export async function downloadFile(endpoint, defaultFilename) {
  const token = authStorage.getToken();
  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, { headers });

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.error?.message || 'Download failed');
  }

  let filename = defaultFilename;
  const disposition = response.headers.get('Content-Disposition');
  if (disposition && disposition.includes('filename=')) {
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
  }

  const blob = await response.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(blobUrl);
}

// ---------------------------------------------------------------------------
// Dedicated API functions
// ---------------------------------------------------------------------------

export const api = {
  // Auth
  async login(username, password) {
    const res = await apiRequest('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    // Check user profile to confirm role
    const profile = await apiRequest('/api/v1/users/me', {
      headers: { Authorization: `Bearer ${res.access_token}` },
    });
    authStorage.setAuth(res.access_token, profile);
    return profile;
  },

  logout() {
    authStorage.clearAuth();
  },

  // Dashboard
  getDashboardSummary() {
    return apiRequest('/api/v1/dashboard/summary');
  },

  // Reports
  getDailyReport(dateStr) {
    return apiRequest(`/api/v1/reports/daily?date=${dateStr}`);
  },

  getMonthlyReport(year, month) {
    return apiRequest(`/api/v1/reports/monthly?year=${year}&month=${month}`);
  },

  getDuesReport() {
    return apiRequest('/api/v1/reports/dues');
  },

  getProfitReport(start, end) {
    return apiRequest(`/api/v1/reports/profit?start=${start}&end=${end}`);
  },

  exportReport(reportType, format, params = {}) {
    const qs = new URLSearchParams({ format, ...params }).toString();
    const defaultExt = format === 'pdf' ? 'pdf' : 'xlsx';
    return downloadFile(
      `/api/v1/reports/${reportType}/export?${qs}`,
      `${reportType}_report.${defaultExt}`
    );
  },

  // Audit Logs
  getAuditLogs(params = {}) {
    const cleanParams = {};
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        cleanParams[k] = v;
      }
    });
    const qs = new URLSearchParams(cleanParams).toString();
    return apiRequest(`/api/v1/audit${qs ? `?${qs}` : ''}`);
  },

  getAuditDetail(id) {
    return apiRequest(`/api/v1/audit/${id}`);
  },
};
