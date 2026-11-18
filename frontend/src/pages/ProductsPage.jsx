import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Filters
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');

  // Modals
  const [showProductModal, setShowProductModal] = useState(false);
  const [showCategoryModal, setShowCategoryModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);

  // Product Form State
  const [formData, setFormData] = useState({
    name: '',
    category_id: '',
    unit: 'kg',
    purchase_price: '',
    sale_price: '',
    current_stock: '0',
    low_stock_threshold: '5',
  });
  const [formError, setFormError] = useState('');
  const [formSubmitting, setFormSubmitting] = useState(false);

  // Category Form State
  const [newCatName, setNewCatName] = useState('');
  const [catError, setCatError] = useState('');
  const [catSubmitting, setCatSubmitting] = useState(false);

  // Load products & categories
  const fetchData = async () => {
    try {
      setLoading(true);
      setError('');
      const [prodRes, catRes] = await Promise.all([
        api.getProducts({
          name: search.trim() || undefined,
          category_id: selectedCategory || undefined,
        }),
        api.getCategories(),
      ]);
      setProducts(prodRes?.items || []);
      setTotal(prodRes?.total || 0);
      setCategories(catRes?.items || catRes || []);
    } catch (err) {
      setError(err.message || 'Failed to load products');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [selectedCategory]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    fetchData();
  };

  const openAddModal = () => {
    setEditingProduct(null);
    setFormData({
      name: '',
      category_id: categories[0]?.id || '',
      unit: 'kg',
      purchase_price: '0.00',
      sale_price: '',
      current_stock: '0',
      low_stock_threshold: '5',
    });
    setFormError('');
    setShowProductModal(true);
  };

  const openEditModal = (prod) => {
    setEditingProduct(prod);
    setFormData({
      name: prod.name,
      category_id: prod.category_id || '',
      unit: prod.unit,
      purchase_price: prod.purchase_price,
      sale_price: prod.sale_price,
      current_stock: prod.current_stock,
      low_stock_threshold: prod.low_stock_threshold,
    });
    setFormError('');
    setShowProductModal(true);
  };

  const handleSaveProduct = async (e) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setFormError('Product name is required.');
      return;
    }
    if (!formData.sale_price || parseFloat(formData.sale_price) <= 0) {
      setFormError('Sale price must be greater than 0.');
      return;
    }

    try {
      setFormSubmitting(true);
      setFormError('');

      if (editingProduct) {
        // Update product
        await api.updateProduct(editingProduct.id, {
          name: formData.name.trim(),
          category_id: formData.category_id ? parseInt(formData.category_id) : null,
          unit: formData.unit.trim(),
          purchase_price: parseFloat(formData.purchase_price || 0),
          sale_price: parseFloat(formData.sale_price),
          low_stock_threshold: parseFloat(formData.low_stock_threshold || 0),
        });
      } else {
        // Create product
        await api.createProduct({
          name: formData.name.trim(),
          category_id: formData.category_id ? parseInt(formData.category_id) : null,
          unit: formData.unit.trim(),
          purchase_price: parseFloat(formData.purchase_price || 0),
          sale_price: parseFloat(formData.sale_price),
          current_stock: parseFloat(formData.current_stock || 0),
          low_stock_threshold: parseFloat(formData.low_stock_threshold || 0),
        });
      }

      setShowProductModal(false);
      fetchData();
    } catch (err) {
      setFormError(err.message || 'Failed to save product');
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleDeleteProduct = async (prod) => {
    if (!window.confirm(`Are you sure you want to deactivate product "${prod.name}"?`)) {
      return;
    }
    try {
      await api.deleteProduct(prod.id);
      fetchData();
    } catch (err) {
      alert(err.message || 'Failed to delete product');
    }
  };

  const handleAddCategory = async (e) => {
    e.preventDefault();
    if (!newCatName.trim()) {
      setCatError('Category name is required.');
      return;
    }
    try {
      setCatSubmitting(true);
      setCatError('');
      await api.createCategory({ name: newCatName.trim() });
      setNewCatName('');
      setShowCategoryModal(false);
      fetchData();
    } catch (err) {
      setCatError(err.message || 'Failed to create category');
    } finally {
      setCatSubmitting(false);
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">Products &amp; Inventory</h1>
          <p className="page-subtitle">Module 1 (Azaz - 237): Manage shop catalog, pricing, units, and categories.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn btn-secondary" onClick={() => setShowCategoryModal(true)}>
            + Manage Categories
          </button>
          <button className="btn btn-primary" onClick={openAddModal}>
            + Add Product
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <form onSubmit={handleSearchSubmit} className="filter-bar">
        <div className="form-group" style={{ flex: 1, minWidth: '200px' }}>
          <label className="form-label">Search Product</label>
          <input
            type="text"
            className="form-input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Type product name and hit enter..."
          />
        </div>

        <div className="form-group" style={{ minWidth: '180px' }}>
          <label className="form-label">Category Filter</label>
          <select
            className="form-select"
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
          >
            <option value="">All Categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <button type="submit" className="btn btn-primary">
          Filter
        </button>
        {search && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setSearch('');
              setSelectedCategory('');
              api.getProducts().then((res) => {
                setProducts(res?.items || []);
                setTotal(res?.total || 0);
              });
            }}
          >
            Reset
          </button>
        )}
      </form>

      {error && <div className="error-banner">{error}</div>}

      {/* Main Table */}
      {loading ? (
        <div className="state-box">
          <div className="spinner" />
          <p>Loading products...</p>
        </div>
      ) : products.length === 0 ? (
        <div className="state-box">
          <h3>No products found</h3>
          <p>Start by clicking "+ Add Product" to create your first catalog item.</p>
        </div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Product Name</th>
                <th>Category</th>
                <th>Unit</th>
                <th>Cost (BDT)</th>
                <th>Sale Price (BDT)</th>
                <th>Stock Balance</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => {
                const isLow = parseFloat(p.current_stock) <= parseFloat(p.low_stock_threshold || 5);
                const categoryObj = categories.find((c) => c.id === p.category_id);
                return (
                  <tr key={p.id}>
                    <td>#{p.id}</td>
                    <td>
                      <strong>{p.name}</strong>
                    </td>
                    <td>{categoryObj ? categoryObj.name : '—'}</td>
                    <td>{p.unit}</td>
                    <td>৳{parseFloat(p.purchase_price || 0).toFixed(2)}</td>
                    <td>
                      <strong style={{ color: 'var(--primary)' }}>
                        ৳{parseFloat(p.sale_price).toFixed(2)}
                      </strong>
                    </td>
                    <td>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.35rem',
                          padding: '0.2rem 0.5rem',
                          borderRadius: '4px',
                          fontSize: '0.85rem',
                          fontWeight: 600,
                          backgroundColor: isLow ? '#fee2e2' : '#ecfdf5',
                          color: isLow ? '#b91c1c' : '#047857',
                        }}
                      >
                        {p.current_stock} {p.unit}
                        {isLow && ' (Low)'}
                      </span>
                    </td>
                    <td>
                      <span
                        style={{
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          color: p.is_active ? 'var(--success)' : 'var(--danger)',
                        }}
                      >
                        {p.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem', marginRight: '0.5rem' }}
                        onClick={() => openEditModal(p)}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn-secondary"
                        style={{
                          padding: '0.25rem 0.6rem',
                          fontSize: '0.8rem',
                          color: 'var(--danger)',
                          borderColor: '#fecaca',
                        }}
                        onClick={() => handleDeleteProduct(p)}
                      >
                        Deactivate
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ padding: '0.75rem 1rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Showing {products.length} of {total} products
          </div>
        </div>
      )}

      {/* Product Modal */}
      {showProductModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h2 style={{ marginBottom: '1rem' }}>
              {editingProduct ? 'Edit Product' : 'Add New Product'}
            </h2>

            {formError && <div className="error-banner">{formError}</div>}

            <form onSubmit={handleSaveProduct}>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Product Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. মিনিকেট চাল (Miniket Rice)"
                  required
                  autoFocus
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Category</label>
                  <select
                    className="form-select"
                    value={formData.category_id}
                    onChange={(e) => setFormData({ ...formData, category_id: e.target.value })}
                  >
                    <option value="">No Category</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Unit of Measure *</label>
                  <input
                    type="text"
                    className="form-input"
                    value={formData.unit}
                    onChange={(e) => setFormData({ ...formData, unit: e.target.value })}
                    placeholder="kg, pcs, litre"
                    required
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Purchase Price (Cost) BDT</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    className="form-input"
                    value={formData.purchase_price}
                    onChange={(e) => setFormData({ ...formData, purchase_price: e.target.value })}
                    placeholder="0.00"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Sale Price BDT *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    className="form-input"
                    value={formData.sale_price}
                    onChange={(e) => setFormData({ ...formData, sale_price: e.target.value })}
                    placeholder="0.00"
                    required
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                {!editingProduct && (
                  <div className="form-group">
                    <label className="form-label">Opening Initial Stock</label>
                    <input
                      type="number"
                      step="0.001"
                      min="0"
                      className="form-input"
                      value={formData.current_stock}
                      onChange={(e) => setFormData({ ...formData, current_stock: e.target.value })}
                    />
                  </div>
                )}

                <div className="form-group">
                  <label className="form-label">Low Stock Alert Threshold</label>
                  <input
                    type="number"
                    step="0.001"
                    min="0"
                    className="form-input"
                    value={formData.low_stock_threshold}
                    onChange={(e) => setFormData({ ...formData, low_stock_threshold: e.target.value })}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowProductModal(false)}
                  disabled={formSubmitting}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={formSubmitting}>
                  {formSubmitting ? 'Saving...' : editingProduct ? 'Save Changes' : 'Create Product'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Category Manager Modal */}
      {showCategoryModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '480px' }}>
            <h2 style={{ marginBottom: '1rem' }}>Product Categories</h2>

            {catError && <div className="error-banner">{catError}</div>}

            <form onSubmit={handleAddCategory} style={{ marginBottom: '1.5rem' }}>
              <div className="form-group" style={{ marginBottom: '0.75rem' }}>
                <label className="form-label">New Category Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={newCatName}
                  onChange={(e) => setNewCatName(e.target.value)}
                  placeholder="e.g. চাল (Rice), মশলা (Spices)"
                  required
                />
              </div>
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={catSubmitting}>
                {catSubmitting ? 'Adding...' : '+ Add Category'}
              </button>
            </form>

            <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem', color: 'var(--text-muted)' }}>Existing Categories</h3>
            <div style={{ maxHeight: '200px', overflowY: 'auto', border: '1px solid var(--border)', borderRadius: '6px' }}>
              {categories.length === 0 ? (
                <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)' }}>No categories yet</div>
              ) : (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {categories.map((c) => (
                    <li
                      key={c.id}
                      style={{
                        padding: '0.5rem 1rem',
                        borderBottom: '1px solid var(--border)',
                        display: 'flex',
                        justifyContent: 'space-between',
                      }}
                    >
                      <span>{c.name}</span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>#{c.id}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div style={{ marginTop: '1.5rem', textAlign: 'right' }}>
              <button className="btn btn-secondary" onClick={() => setShowCategoryModal(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
