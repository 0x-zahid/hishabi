/**
 * API calls for suppliers.
 *
 * Every call goes through `apiRequest` from `client.js`, so the bearer token
 * and the error normalisation are handled in one place and never duplicated
 * here.
 */

import { apiRequest } from './client';

/**
 * List suppliers.
 */
export async function getSuppliers(params = {}) {
  const cleanParams = {};
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      cleanParams[k] = v;
    }
  });
  const qs = new URLSearchParams(cleanParams).toString();
  return apiRequest(`/api/v1/suppliers${qs ? `?${qs}` : ''}`);
}

/**
 * Create a supplier.
 */
export async function createSupplier(payload) {
  return apiRequest('/api/v1/suppliers', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Get one supplier profile with its purchase statistics.
 */
export async function getSupplier(supplierId) {
  return apiRequest(`/api/v1/suppliers/${supplierId}`);
}

/**
 * List the purchases recorded for one supplier.
 */
export async function getSupplierPurchases(supplierId, params = {}) {
  const cleanParams = {};
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      cleanParams[k] = v;
    }
  });
  const qs = new URLSearchParams(cleanParams).toString();
  return apiRequest(
    `/api/v1/suppliers/${supplierId}/purchases${qs ? `?${qs}` : ''}`
  );
}
