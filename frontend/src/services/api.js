/**
 * Centralized API service for making requests to the AlSign backend
 */

import { supabase } from './supabaseClient';

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL || '';
const normalizedBaseUrl = rawBaseUrl === '/' ? '' : rawBaseUrl.replace(/\/+$/, '');
export const API_BASE_URL = normalizedBaseUrl;

async function getAccessToken() {
  const { data } = await supabase.auth.getSession();
  return data?.session?.access_token || null;
}

export async function getAuthHeaders(extraHeaders = {}) {
  const token = await getAccessToken();
  return {
    ...extraHeaders,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/**
 * Base fetch wrapper with error handling
 */
async function fetchAPI(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;

  const authHeaders = await getAuthHeaders(options.headers);

  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
    },
  };

  const mergedOptions = { ...defaultOptions, ...options };

  try {
    const response = await fetch(url, mergedOptions);

    // Handle non-JSON responses (e.g., 204 No Content)
    if (response.status === 204) {
      return null;
    }

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || data.error?.message || `HTTP ${response.status}`);
    }

    return data;
  } catch (error) {
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
}

/**
 * GET request
 */
export async function get(endpoint, params = {}) {
  const queryString = new URLSearchParams(params).toString();
  const url = queryString ? `${endpoint}?${queryString}` : endpoint;

  return fetchAPI(url, { method: 'GET' });
}

/**
 * POST request
 */
export async function post(endpoint, body = {}, params = {}) {
  const queryString = new URLSearchParams(params).toString();
  const url = queryString ? `${endpoint}?${queryString}` : endpoint;

  return fetchAPI(url, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * PUT request
 */
export async function put(endpoint, body = {}) {
  return fetchAPI(endpoint, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

/**
 * DELETE request
 */
export async function del(endpoint) {
  return fetchAPI(endpoint, {
    method: 'DELETE',
  });
}

/**
 * Health check endpoint
 */
export async function checkHealth() {
  return get('/health');
}

export default {
  get,
  post,
  put,
  del,
  checkHealth,
  API_BASE_URL,
};
