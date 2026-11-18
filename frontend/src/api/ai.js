/**
 * API calls for the AI Bangla entry feature.
 *
 * Owner: Zahid. Module 3.
 *
 * Every call goes through `apiRequest` from `client.js`, so the bearer token
 * and the error normalisation are handled in one place and never duplicated
 * here.
 */

import { apiRequest } from './client';

/**
 * Parse one Bangla sentence into a sale proposal.
 *
 * The server answers 200 with the proposal, 429 when the daily limit is
 * reached, 422 when the AI's answer did not match the fixed shape and 503
 * when the AI service is unavailable.
 */
export async function parseSale(text) {
  return apiRequest('/api/v1/ai/parse', {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

/**
 * Return how many AI requests are left today for the current user.
 */
export async function getTodayUsage() {
  return apiRequest('/api/v1/ai/requests/today');
}

/**
 * Return one of the current user's own AI requests.
 */
export async function getRequest(requestId) {
  return apiRequest(`/api/v1/ai/requests/${requestId}`);
}

/**
 * Confirm a proposal and record the sale.
 *
 * `proposal` is the proposal as the user changed it in the review form.
 */
export async function confirmRequest(requestId, proposal) {
  return apiRequest(`/api/v1/ai/requests/${requestId}/confirm`, {
    method: 'POST',
    body: JSON.stringify(proposal),
  });
}

/**
 * Discard a proposal. Nothing is saved.
 */
export async function rejectRequest(requestId) {
  return apiRequest(`/api/v1/ai/requests/${requestId}/reject`, {
    method: 'POST',
  });
}

/**
 * List the customers, so the user can pick one in the review form.
 */
export async function getCustomers() {
  return apiRequest('/api/v1/customers?limit=100&is_active=true');
}

/**
 * List the products, so the user can pick one per line in the review form.
 */
export async function getProducts() {
  return apiRequest('/api/v1/products?limit=100');
}

/**
 * Record a sale by hand, for the manual entry form.
 *
 * This is the ordinary sale endpoint, so it works with no AI key at all.
 */
export async function createManualSale(sale) {
  return apiRequest('/api/v1/sales', {
    method: 'POST',
    body: JSON.stringify(sale),
  });
}
