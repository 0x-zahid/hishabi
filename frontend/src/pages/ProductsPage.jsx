import React, { useEffect, useState } from 'react';
import { createProduct, getProducts, updateProduct } from '../api/products';

/**
 * Product management page.
 *
 * The list shows every live product with its unit, both prices and the stock
 * on hand. A product whose stock is at or below its low-stock threshold gets a
 * LOW STOCK marker.
 *
 * Two forms sit under the table: one creates a product, the other edits the
 * one the user picked. Stock is not editable here: it only moves through
 * sales, purchases and stock movements.
 */

const EMPTY_PRODUCT = {
  name: '',
  unit: '',
  sale_price: '',
  purchase_price: '',
  current_stock: '',
  low_stock_threshold: '',
};

export default function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [search, setSearch] = useState('');
  const limit = 20;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Create form
  const [form, setForm] = useState(EMPTY_PRODUCT);
  const [saving, setSaving] = useState(false);

  // Edit form
  const [editing, setEditing] = useState(null);
  const [editForm, setEditForm] = useState(EMPTY_PRODUCT);
  const [updating, setUpdating] = useState(false);

  const fetchProducts = async (currentSkip = 0, currentSearch = '') => {
    try {
      setLoading(true);
      setError('');
      const res = await getProducts({
        skip: currentSkip,
        limit,
        search: currentSearch,
      });
      setProducts(res?.items || []);
      setTotal(res?.total || 0);
      setSkip(currentSkip);
    } catch (err) {
      setError(err.message || 'Failed to load products.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProducts(0);
  }, []);

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!form.name.trim() || !form.unit.trim() || !form.sale_price) {
      setError('Name, unit and sale price are required.');
      return;
    }
    try {
      setSaving(true);
      setError('');
      setSuccess('');
      const created = await createProduct({
        name: form.name.trim(),
        unit: form.unit.trim(),
        sale_price: form.sale_price,
        purchase_price: form.purchase_price || '0',
        current_stock: form.current_stock || '0',
        low_stock_threshold: form.low_stock_threshold || '0',
      });
      setSuccess(`Product "${created.name}" was created.`);
      setForm(EMPTY_PRODUCT);
      fetchProducts(0);
    } catch (err) {
      setError(err.message || 'Failed to create the product.');
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (product) => {
    setEditing(product);
    setError('');
    setSuccess('');
    setEditForm({
      name: product.name,
      unit: product.unit,
      sale_price: product.sale_price,
      purchase_price: product.purchase_price,
      current_stock: product.current_stock,
      low_stock_threshold: product.low_stock_threshold,
    });
  };

  const handleUpdate = async (event) => {
    event.preventDefault();
    if (!editing) return;
    if (!editForm.name.trim() || !editForm.unit.trim() || !editForm.sale_price) {
      setError('Name, unit and sale price are required.');
      return;
    }
    try {
      setUpdating(true);
      setError('');
      setSuccess('');
      const updated = await updateProduct(editing.id, {
        name: editForm.name.trim(),
        unit: editForm.unit.trim(),
        sale_price: editForm.sale_price,
        purchase_price: editForm.purchase_price,
        low_stock_threshold: editForm.low_stock_threshold,
      });
      setSuccess(`Product "${updated.name}" was updated.`);
      setEditing(null);
      fetchProducts(skip);
    } catch (err) {
      setError(err.message || 'Failed to update the product.');
    } finally {
      setUpdating(false);
    }
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(skip / limit) + 1;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Products</h1>
        <p className="page-subtitle">Items you sell, their prices and the stock on hand</p>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {success && <div className="success-banner">{success}</div>}

      {/* Filter Bar */}
      <div className="filter-bar">
        <div className="form-group">
          <label className="form-label">Search</label>
          <input
            type="text"
            className="form-input"
            style={{ width: '220px' }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Product name"
          />
        </div>

        <button
          onClick={() => fetchProducts(0, search)}
          className="btn btn-primary"
          disabled={loading}
        >
          {loading ? 'Filtering...' : 'Search'}
        </button>
      </div>

      {/* Table */}
      <div className="table-container">
        {loading ? (
          <div className="state-box">
            <div className="spinner"></div>
            <p>Loading products...</p>
          </div>
        ) : products.length === 0 ? (
          <div className="state-box">No products found. Add your first product below.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Unit</th>
                <th>Sale Price</th>
                <th>Purchase Price</th>
                <th>Current Stock</th>
                <th>Low Stock At</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {products.map((product) => {
                const isLow =
                  Number(product.current_stock) <= Number(product.low_stock_threshold);
                return (
                  <tr key={product.id}>
                    <td style={{ fontWeight: 600 }}>{product.name}</td>
                    <td>{product.unit}</td>
                    <td>BDT {product.sale_price}</td>
                    <td>BDT {product.purchase_price}</td>
                    <td
                      style={{
                        color: isLow ? 'var(--danger)' : 'var(--text)',
                        fontWeight: isLow ? 700 : 400,
                      }}
                    >
                      {product.current_stock}
                    </td>
                    <td>{product.low_stock_threshold}</td>
                    <td>
                      {isLow ? (
                        <span
                          style={{
                            background: '#fef2f2',
                            color: '#b91c1c',
                            padding: '0.2rem 0.5rem',
                            borderRadius: 4,
                            fontSize: '0.75rem',
                            fontWeight: 600,
                          }}
                        >
                          LOW STOCK
                        </span>
                      ) : (
                        <span
                          style={{
                            background: '#ecfdf5',
                            color: '#065f46',
                            padding: '0.2rem 0.5rem',
                            borderRadius: 4,
                            fontSize: '0.75rem',
                            fontWeight: 600,
                          }}
                        >
                          IN STOCK
                        </span>
                      )}
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '0.2rem 0.6rem', fontSize: '0.8rem' }}
                        onClick={() => startEdit(product)}
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Showing {skip + 1}–{Math.min(skip + limit, total)} of {total} products
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              disabled={skip === 0 || loading}
              onClick={() => fetchProducts(Math.max(0, skip - limit), search)}
            >
              Previous
            </button>
            <span style={{ display: 'flex', alignItems: 'center', padding: '0 0.5rem', fontSize: '0.9rem' }}>
              Page {currentPage} of {totalPages}
            </span>
            <button
              className="btn btn-secondary"
              disabled={skip + limit >= total || loading}
              onClick={() => fetchProducts(skip + limit, search)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Edit Form */}
      {editing && (
        <div className="card" style={{ marginBottom: '2rem' }}>
          <div className="card-title">Edit product #{editing.id}</div>
          <p className="card-subtext" style={{ marginBottom: '1rem' }}>
            Current stock is {editing.current_stock} {editing.unit}. Stock is changed by sales,
            purchases and stock movements, not from here.
          </p>

          <form onSubmit={handleUpdate}>
            <div
              style={{
                display: 'flex',
                gap: '1rem',
                flexWrap: 'wrap',
                alignItems: 'flex-end',
                marginBottom: '1rem',
              }}
            >
              <div className="form-group">
                <label className="form-label">Name</label>
                <input
                  type="text"
                  className="form-input"
                  style={{ width: '220px' }}
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Unit</label>
                <input
                  type="text"
                  className="form-input"
                  style={{ width: '100px' }}
                  value={editForm.unit}
                  onChange={(e) => setEditForm({ ...editForm, unit: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Sale price</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  style={{ width: '130px' }}
                  value={editForm.sale_price}
                  onChange={(e) => setEditForm({ ...editForm, sale_price: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Purchase price</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  style={{ width: '130px' }}
                  value={editForm.purchase_price}
                  onChange={(e) => setEditForm({ ...editForm, purchase_price: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Low stock at</label>
                <input
                  type="number"
                  step="0.001"
                  className="form-input"
                  style={{ width: '120px' }}
                  value={editForm.low_stock_threshold}
                  onChange={(e) =>
                    setEditForm({ ...editForm, low_stock_threshold: e.target.value })
                  }
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button type="submit" className="btn btn-primary" disabled={updating}>
                {updating ? 'Saving...' : 'Save changes'}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setEditing(null)}
                disabled={updating}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Create Form */}
      <div className="card">
        <div className="card-title">Add a product</div>
        <p className="card-subtext" style={{ marginBottom: '1rem' }}>
          Name, unit and sale price are required. The prices and the stock can be left at zero and
          corrected later.
        </p>

        <form onSubmit={handleCreate}>
          <div
            style={{
              display: 'flex',
              gap: '1rem',
              flexWrap: 'wrap',
              alignItems: 'flex-end',
              marginBottom: '1rem',
            }}
          >
            <div className="form-group">
              <label className="form-label">Name</label>
              <input
                type="text"
                className="form-input"
                style={{ width: '220px' }}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. চাল"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Unit</label>
              <input
                type="text"
                className="form-input"
                style={{ width: '100px' }}
                value={form.unit}
                onChange={(e) => setForm({ ...form, unit: e.target.value })}
                placeholder="kg"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Sale price</label>
              <input
                type="number"
                step="0.01"
                className="form-input"
                style={{ width: '130px' }}
                value={form.sale_price}
                onChange={(e) => setForm({ ...form, sale_price: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Purchase price</label>
              <input
                type="number"
                step="0.01"
                className="form-input"
                style={{ width: '130px' }}
                value={form.purchase_price}
                onChange={(e) => setForm({ ...form, purchase_price: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Current stock</label>
              <input
                type="number"
                step="0.001"
                className="form-input"
                style={{ width: '120px' }}
                value={form.current_stock}
                onChange={(e) => setForm({ ...form, current_stock: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Low stock at</label>
              <input
                type="number"
                step="0.001"
                className="form-input"
                style={{ width: '120px' }}
                value={form.low_stock_threshold}
                onChange={(e) => setForm({ ...form, low_stock_threshold: e.target.value })}
              />
            </div>
          </div>

          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Creating...' : 'Create product'}
          </button>
        </form>
      </div>
    </div>
  );
}
