/**
 * API calls for customers and their dues.
 *
 * Every call goes through `apiRequest` from `client.js`, so the bearer token
 * and the error normalisation are handled in one place and never duplicated
 * here.
 *
 * The outstanding due is computed by the server on every read: it is never
 * stored on the customers table and never recomputed in the browser.
 */

import { apiRequest } from './client';

/**
 * List customers.
 */
export async function getCustomers(params = {}) {
  const cleanParams = {};
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      cleanParams[k] = v;
    }
  });
  const qs = new URLSearchParams(cleanParams).toString();
  return apiRequest(`/api/v1/customers${qs ? `?${qs}` : ''}`);
}

/**
 * Create a customer.
 */
export async function createCustomer(payload) {
  return apiRequest('/api/v1/customers', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Get one customer profile.
 */
export async function getCustomer(customerId) {
  return apiRequest(`/api/v1/customers/${customerId}`);
}

/**
 * List every customer that has a ledger, with their outstanding due.
 *
 * Customers with no credit sales and no payments are omitted by the server.
 */
export async function getCustomerDues() {
  return apiRequest('/api/v1/customers/due');
}

/**
 * Get one customer's due breakdown: credit sales, paid, and current due.
 */
export async function getCustomerDue(customerId) {
  return apiRequest(`/api/v1/customers/${customerId}/due`);
}

/**
 * Get one customer's profile with their recent activity.
 *
 * The `sales` and `payments` lists this endpoint returns are still empty on
 * the server, so the profile page reads the two histories from
 * `getCustomerSales()` and `getCustomerPayments()` instead.
 */
export async function getCustomerHistory(customerId, limit = 20) {
  return apiRequest(`/api/v1/customers/${customerId}/history?limit=${limit}`);
}

/**
 * Get one customer's sales history, newest first.
 */
export async function getCustomerSales(customerId, page = 1, pageSize = 20) {
  return apiRequest(
    `/api/v1/sales?customer_id=${customerId}&page=${page}&page_size=${pageSize}`
  );
}

/**
 * Get one customer's payment history, newest first.
 */
export async function getCustomerPayments(customerId, page = 1, pageSize = 20) {
  return apiRequest(
    `/api/v1/payments?customer_id=${customerId}&page=${page}&page_size=${pageSize}`
  );
}
