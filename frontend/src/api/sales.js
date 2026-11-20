/**
 * API calls for sales.
 *
 * Every call goes through `apiRequest` from `client.js`, so the bearer token
 * and the error normalisation are handled in one place and never duplicated
 * here.
 *
 * Sales are immutable: there is no update and no delete. The list endpoint
 * supports a date range and a payment type filter.
 */

import { apiRequest } from './client';

/**
 * List sales newest first.
 *
 * `start_date` and `end_date` are inclusive and formatted YYYY-MM-DD.
 */
export async function getSales(params = {}) {
  const cleanParams = {};
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      cleanParams[k] = v;
    }
  });
  const qs = new URLSearchParams(cleanParams).toString();
  return apiRequest(`/api/v1/sales${qs ? `?${qs}` : ''}`);
}

/**
 * Get one sale with its items and payments.
 */
export async function getSale(saleId) {
  return apiRequest(`/api/v1/sales/${saleId}`);
}
