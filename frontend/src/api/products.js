/**
 * API calls for products.
 *
 * Every call goes through `apiRequest` from `client.js`, so the bearer token
 * and the error normalisation are handled in one place and never duplicated
 * here.
 *
 * Note: `ProductUpdate` has no `current_stock` field. Stock only moves through
 * sales, purchases and stock movements, so the edit call never sends it.
 */

import { apiRequest } from './client';

/**
 * List products.
 *
 * `is_active` defaults to true on the server, so only live products come back.
 */
export async function getProducts(params = {}) {
  const cleanParams = {};
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      cleanParams[k] = v;
    }
  });
  const qs = new URLSearchParams(cleanParams).toString();
  return apiRequest(`/api/v1/products${qs ? `?${qs}` : ''}`);
}

/**
 * Create a product.
 */
export async function createProduct(payload) {
  return apiRequest('/api/v1/products', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update a product. Only the fields sent are changed.
 */
export async function updateProduct(productId, payload) {
  return apiRequest(`/api/v1/products/${productId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}
