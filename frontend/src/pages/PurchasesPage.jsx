import React, { useEffect, useState, useRef } from 'react';
import { api } from '../api/client';

/**
 * Searchable & Writable Combobox for Products.
 * Allows typing to search, selecting from live suggestions, or creating on the fly.
 */
function ProductSearchSelect({ products, selectedId, onSelect, onQuickAdd }) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);

  const selectedProduct = products.find((p) => p.id === parseInt(selectedId));

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const filtered = products.filter((p) => {
    const q = query.toLowerCase().trim();
    if (!q) return true;
    return (
      p.name.toLowerCase().includes(q) ||
      (p.unit || '').toLowerCase().includes(q) ||
      p.id.toString() === q
    );
  });

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%' }}>
      <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
        <input
          type="text"
          className="form-input"
          style={{
            width: '100%',
            fontWeight: selectedProduct && !isOpen ? 600 : 400,
            background: selectedProduct && !isOpen ? '#f8fafc' : '#ffffff',
          }}
          value={
            isOpen
              ? query
              : selectedProduct
              ? `${selectedProduct.name} (${selectedProduct.current_stock} ${selectedProduct.unit})`
              : query
          }
          placeholder="✍️ Type to search or choose product..."
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => {
            setIsOpen(true);
            setQuery('');
          }}
        />

        {selectedProduct && (
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '0.4rem 0.6rem', fontSize: '0.75rem', color: 'var(--danger)' }}
            onClick={() => {
              onSelect('');
              setQuery('');
            }}
            title="Clear product"
          >
            ✕
          </button>
        )}
      </div>

      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            zIndex: 100,
            maxHeight: '260px',
            overflowY: 'auto',
            background: '#ffffff',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.15)',
            marginTop: '4px',
          }}
        >
          {filtered.length === 0 ? (
            <div style={{ padding: '1rem', fontSize: '0.88rem', color: 'var(--text-muted)', textAlign: 'center' }}>
              <div>No existing product matches "{query}".</div>
              <button
                type="button"
                className="btn btn-primary"
                style={{ width: '100%', marginTop: '0.75rem', fontSize: '0.85rem', padding: '0.45rem' }}
                onClick={() => {
                  setIsOpen(false);
                  onQuickAdd(query);
                }}
              >
                + Create "{query}" as New Product
              </button>
            </div>
          ) : (
            filtered.map((p) => {
              const isLow = parseFloat(p.current_stock) <= parseFloat(p.low_stock_threshold || 5);
              return (
                <div
                  key={p.id}
                  style={{
                    padding: '0.6rem 0.85rem',
                    cursor: 'pointer',
                    borderBottom: '1px solid #f1f5f9',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    background: selectedProduct?.id === p.id ? '#eff6ff' : 'transparent',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    if (selectedProduct?.id !== p.id) e.currentTarget.style.background = '#f8fafc';
                  }}
                  onMouseLeave={(e) => {
                    if (selectedProduct?.id !== p.id) e.currentTarget.style.background = 'transparent';
                  }}
                  onMouseDown={() => {
                    onSelect(p.id.toString());
                    setIsOpen(false);
                    setQuery('');
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.92rem' }}>{p.name}</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      Cost: ৳{parseFloat(p.purchase_price || 0).toFixed(2)} • Sell: ৳{parseFloat(p.sale_price).toFixed(2)}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: isLow ? '#fee2e2' : '#ecfdf5',
                        color: isLow ? '#b91c1c' : '#047857',
                      }}
                    >
                      {p.current_stock} {p.unit}
                    </span>
                  </div>
                </div>
              );
            })
          )}

          <div
            style={{
              padding: '0.5rem 0.85rem',
              background: '#f8fafc',
              borderTop: '1px solid var(--border)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Showing {filtered.length} products
            </span>
            <button
              type="button"
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--primary)',
                fontSize: '0.82rem',
                cursor: 'pointer',
                fontWeight: 600,
              }}
              onClick={() => {
                setIsOpen(false);
                onQuickAdd(query);
              }}
            >
              + Quick Add Product
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PurchasesPage() {
  const [activeTab, setActiveTab] = useState('record'); // 'record' | 'suppliers' | 'history'

  // Data
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [purchases, setPurchases] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Purchase Form State
  const [selectedSupplier, setSelectedSupplier] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [purchaseItems, setPurchaseItems] = useState([
    { product_id: '', quantity: '1', unit_cost: '' },
  ]);
  const [purchaseSubmitting, setPurchaseSubmitting] = useState(false);

  // Supplier Form State (Modal)
  const [showSupplierModal, setShowSupplierModal] = useState(false);
  const [supplierForm, setSupplierForm] = useState({
    name: '',
    contact_person: '',
    phone: '',
    email: '',
    address: '',
  });
  const [supplierSubmitting, setSupplierSubmitting] = useState(false);
  const [supplierFormError, setSupplierFormError] = useState('');

  // Quick Product Modal State
  const [showQuickProductModal, setShowQuickProductModal] = useState(false);
  const [quickProductTargetIndex, setQuickProductTargetIndex] = useState(null);
  const [quickProductForm, setQuickProductForm] = useState({
    name: '',
    category_id: '',
    unit: 'kg',
    purchase_price: '0.00',
    sale_price: '0.00',
  });
  const [quickProductSubmitting, setQuickProductSubmitting] = useState(false);
  const [quickProductError, setQuickProductError] = useState('');

  // Selected Purchase for Detail Modal
  const [selectedPurchaseDetail, setSelectedPurchaseDetail] = useState(null);

  // Load initial suppliers, products & categories
  const loadInitialData = async () => {
    try {
      setLoading(true);
      setError('');
      const [supRes, prodRes, catRes] = await Promise.all([
        api.getSuppliers(),
        api.getProducts({ limit: 200 }),
        api.getCategories(),
      ]);
      const supItems = supRes?.items || [];
      const prodItems = prodRes?.items || [];
      setSuppliers(supItems);
      setProducts(prodItems);
      setCategories(catRes?.items || catRes || []);

      if (supItems.length > 0 && !selectedSupplier) {
        setSelectedSupplier(supItems[0].id.toString());
      }
    } catch (err) {
      setError(err.message || 'Failed to load initial data');
    } finally {
      setLoading(false);
    }
  };

  // Load Purchases History
  const loadPurchases = async () => {
    try {
      setLoading(true);
      const res = await api.getPurchases();
      setPurchases(res?.items || []);
    } catch (err) {
      setError(err.message || 'Failed to load purchases history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (activeTab === 'history') {
      loadPurchases();
    } else if (activeTab === 'suppliers') {
      api.getSuppliers().then((res) => setSuppliers(res?.items || []));
    }
  }, [activeTab]);

  // Line item helpers
  const handleAddItem = () => {
    setPurchaseItems([
      ...purchaseItems,
      { product_id: '', quantity: '1', unit_cost: '' },
    ]);
  };

  const handleRemoveItem = (index) => {
    if (purchaseItems.length === 1) return;
    setPurchaseItems(purchaseItems.filter((_, i) => i !== index));
  };

  const handleItemChange = (index, field, value) => {
    const updated = [...purchaseItems];
    updated[index][field] = value;

    // Auto-fill cost price when product is selected
    if (field === 'product_id') {
      const prod = products.find((p) => p.id === parseInt(value));
      if (prod) {
        updated[index].unit_cost = prod.purchase_price || '0.00';
      }
    }

    setPurchaseItems(updated);
  };

  // Open Quick Product Creator
  const handleOpenQuickProduct = (suggestedName = '', rowIndex = null) => {
    setQuickProductTargetIndex(rowIndex);
    setQuickProductForm({
      name: suggestedName || '',
      category_id: categories[0]?.id?.toString() || '',
      unit: 'kg',
      purchase_price: '0.00',
      sale_price: '0.00',
    });
    setQuickProductError('');
    setShowQuickProductModal(true);
  };

  // Save Quick Product
  const handleSaveQuickProduct = async (e) => {
    e.preventDefault();
    if (!quickProductForm.name.trim()) {
      setQuickProductError('Product name is required.');
      return;
    }
    if (!quickProductForm.sale_price || parseFloat(quickProductForm.sale_price) <= 0) {
      setQuickProductError('Sale price must be greater than 0.');
      return;
    }

    try {
      setQuickProductSubmitting(true);
      setQuickProductError('');

      const newProd = await api.createProduct({
        name: quickProductForm.name.trim(),
        category_id: quickProductForm.category_id ? parseInt(quickProductForm.category_id) : null,
        unit: quickProductForm.unit.trim() || 'kg',
        purchase_price: parseFloat(quickProductForm.purchase_price || 0),
        sale_price: parseFloat(quickProductForm.sale_price),
        current_stock: 0,
        low_stock_threshold: 5,
      });

      // Refresh product list and update state
      const prodRes = await api.getProducts({ limit: 200 });
      const updatedList = prodRes?.items || [];
      setProducts(updatedList);

      // If opened from a line item, auto-select it!
      if (quickProductTargetIndex !== null && quickProductTargetIndex >= 0) {
        handleItemChange(quickProductTargetIndex, 'product_id', newProd.id.toString());
      }

      setShowQuickProductModal(false);
    } catch (err) {
      setQuickProductError(err.message || 'Failed to create product');
    } finally {
      setQuickProductSubmitting(false);
    }
  };

  // Compute Grand Total
  const grandTotal = purchaseItems.reduce((acc, item) => {
    const q = parseFloat(item.quantity) || 0;
    const c = parseFloat(item.unit_cost) || 0;
    return acc + q * c;
  }, 0);

  // Submit Purchase (Record stock inward)
  const handleRecordPurchase = async (e) => {
    e.preventDefault();
    if (!selectedSupplier) {
      setError('Please select a supplier.');
      return;
    }
    if (purchaseItems.length === 0) {
      setError('Please add at least one item.');
      return;
    }

    // Validate items
    for (let i = 0; i < purchaseItems.length; i++) {
      const it = purchaseItems[i];
      if (!it.product_id) {
        setError(`Please select or write a product for line #${i + 1}.`);
        return;
      }
      if (!it.quantity || parseFloat(it.quantity) <= 0) {
        setError(`Line #${i + 1} quantity must be greater than 0.`);
        return;
      }
      if (!it.unit_cost || parseFloat(it.unit_cost) < 0) {
        setError(`Line #${i + 1} unit cost cannot be negative.`);
        return;
      }
    }

    try {
      setPurchaseSubmitting(true);
      setError('');
      setSuccessMsg('');

      const payload = {
        supplier_id: parseInt(selectedSupplier),
        invoice_number: invoiceNumber.trim() || null,
        items: purchaseItems.map((it) => ({
          product_id: parseInt(it.product_id),
          quantity: parseFloat(it.quantity),
          unit_cost: parseFloat(it.unit_cost),
        })),
        total_amount: parseFloat(grandTotal.toFixed(2)),
      };

      const result = await api.createPurchase(payload);

      setSuccessMsg(
        `Purchase #${result.id} recorded successfully! Stock has been automatically updated in inventory.`
      );
      // Reset form
      setInvoiceNumber('');
      setPurchaseItems([{ product_id: '', quantity: '1', unit_cost: '' }]);

      // Refresh product stock list in background
      api.getProducts({ limit: 200 }).then((res) => setProducts(res?.items || []));
    } catch (err) {
      setError(err.message || 'Failed to record purchase.');
    } finally {
      setPurchaseSubmitting(false);
    }
  };

  // Create Supplier
  const handleSaveSupplier = async (e) => {
    e.preventDefault();
    if (!supplierForm.name.trim()) {
      setSupplierFormError('Supplier / Company name is required.');
      return;
    }
    try {
      setSupplierSubmitting(true);
      setSupplierFormError('');
      const newSup = await api.createSupplier({
        name: supplierForm.name.trim(),
        contact_person: supplierForm.contact_person.trim() || null,
        phone: supplierForm.phone.trim() || null,
        email: supplierForm.email.trim() || null,
        address: supplierForm.address.trim() || null,
      });

      setShowSupplierModal(false);
      setSupplierForm({ name: '', contact_person: '', phone: '', email: '', address: '' });

      // Refresh suppliers and select new supplier
      const res = await api.getSuppliers();
      setSuppliers(res?.items || []);
      setSelectedSupplier(newSup.id.toString());
    } catch (err) {
      setSupplierFormError(err.message || 'Failed to create supplier.');
    } finally {
      setSupplierSubmitting(false);
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">Purchases &amp; Supplier Management</h1>
          <p className="page-subtitle">Module 2 (Azaz - 237): Record incoming goods, vendors, and auto-increment stock.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn btn-secondary" onClick={() => handleOpenQuickProduct('', null)}>
            + Quick Add Product
          </button>
          <button className="btn btn-secondary" onClick={() => setShowSupplierModal(true)}>
            + Add New Supplier
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
        <button
          className={`btn ${activeTab === 'record' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => { setActiveTab('record'); setError(''); setSuccessMsg(''); }}
        >
          📦 Record New Purchase
        </button>
        <button
          className={`btn ${activeTab === 'history' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => { setActiveTab('history'); setError(''); setSuccessMsg(''); }}
        >
          📋 Purchase History
        </button>
        <button
          className={`btn ${activeTab === 'suppliers' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => { setActiveTab('suppliers'); setError(''); setSuccessMsg(''); }}
        >
          🏢 Suppliers Directory
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {successMsg && <div className="success-banner">{successMsg}</div>}

      {/* TAB 1: RECORD NEW PURCHASE */}
      {activeTab === 'record' && (
        <div className="card" style={{ padding: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>
              Inward Stock Entry (Purchase Voucher)
            </h2>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Catalog: <strong>{products.length} products</strong> available
            </span>
          </div>

          {suppliers.length === 0 ? (
            <div className="state-box">
              <p>No active suppliers found.</p>
              <button className="btn btn-primary" onClick={() => setShowSupplierModal(true)}>
                + Register a Supplier First
              </button>
            </div>
          ) : (
            <form onSubmit={handleRecordPurchase}>
              {/* Header Fields */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.5rem' }}>
                <div className="form-group">
                  <label className="form-label">Select Supplier *</label>
                  <select
                    className="form-select"
                    value={selectedSupplier}
                    onChange={(e) => setSelectedSupplier(e.target.value)}
                    required
                  >
                    {suppliers.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} {s.contact_person ? `(${s.contact_person})` : ''}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Supplier Bill / Invoice Number (Optional)</label>
                  <input
                    type="text"
                    className="form-input"
                    value={invoiceNumber}
                    onChange={(e) => setInvoiceNumber(e.target.value)}
                    placeholder="e.g. INV-2026-9901"
                  />
                </div>
              </div>

              {/* Items Table */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Purchase Line Items</h3>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  ✍️ Tip: You can type in the product box to search or create a new item directly.
                </span>
              </div>

              <div className="table-container" style={{ marginBottom: '1.25rem', overflow: 'visible' }}>
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: '48%' }}>Product (Search / Write / Choose) *</th>
                      <th style={{ width: '18%' }}>Quantity *</th>
                      <th style={{ width: '18%' }}>Unit Cost (BDT) *</th>
                      <th style={{ width: '16%', textAlign: 'right' }}>Line Total (BDT)</th>
                      <th style={{ width: '40px' }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {purchaseItems.map((item, idx) => {
                      const lineTotal = (parseFloat(item.quantity) || 0) * (parseFloat(item.unit_cost) || 0);
                      const selectedProd = products.find((p) => p.id === parseInt(item.product_id));

                      return (
                        <tr key={idx}>
                          <td>
                            <ProductSearchSelect
                              products={products}
                              selectedId={item.product_id}
                              onSelect={(val) => handleItemChange(idx, 'product_id', val)}
                              onQuickAdd={(name) => handleOpenQuickProduct(name, idx)}
                            />
                            {selectedProd && (
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                                Unit: <strong>{selectedProd.unit}</strong> • In-Stock:{' '}
                                <strong>{selectedProd.current_stock}</strong>
                              </div>
                            )}
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                              <input
                                type="number"
                                step="0.001"
                                min="0.001"
                                className="form-input"
                                value={item.quantity}
                                onChange={(e) => handleItemChange(idx, 'quantity', e.target.value)}
                                required
                              />
                              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', minWidth: '24px' }}>
                                {selectedProd?.unit || 'qty'}
                              </span>
                            </div>
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                              <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>৳</span>
                              <input
                                type="number"
                                step="0.01"
                                min="0"
                                className="form-input"
                                value={item.unit_cost}
                                onChange={(e) => handleItemChange(idx, 'unit_cost', e.target.value)}
                                placeholder="0.00"
                                required
                              />
                            </div>
                          </td>
                          <td style={{ textAlign: 'right', fontWeight: 600, fontSize: '0.95rem' }}>
                            ৳{lineTotal.toFixed(2)}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            {purchaseItems.length > 1 && (
                              <button
                                type="button"
                                className="btn btn-secondary"
                                style={{ padding: '0.25rem 0.5rem', color: 'var(--danger)', borderColor: '#fca5a5' }}
                                onClick={() => handleRemoveItem(idx)}
                                title="Remove line item"
                              >
                                ✕
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Add Item & Grand Total Bar */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <button type="button" className="btn btn-secondary" onClick={handleAddItem}>
                  + Add Another Product Line
                </button>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    Total Lines: <strong>{purchaseItems.length}</strong>
                  </div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800 }}>
                    Grand Total: <span style={{ color: 'var(--primary)' }}>৳{grandTotal.toFixed(2)}</span>
                  </div>
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: '100%', padding: '0.85rem', fontSize: '1.05rem', justifyContent: 'center' }}
                disabled={purchaseSubmitting}
              >
                {purchaseSubmitting ? 'Recording & Incrementing Stock...' : 'Confirm Purchase & Increase Stock'}
              </button>
            </form>
          )}
        </div>
      )}

      {/* TAB 2: PURCHASE HISTORY */}
      {activeTab === 'history' && (
        <div>
          {loading ? (
            <div className="state-box">
              <div className="spinner" />
              <p>Loading purchase history...</p>
            </div>
          ) : purchases.length === 0 ? (
            <div className="state-box">
              <h3>No purchases recorded yet</h3>
              <p>Switch to "Record New Purchase" tab to enter incoming stock.</p>
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Purchase ID</th>
                    <th>Date</th>
                    <th>Supplier</th>
                    <th>Invoice #</th>
                    <th>Total Items</th>
                    <th>Total Amount (BDT)</th>
                    <th style={{ textAlign: 'right' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {purchases.map((p) => (
                    <tr key={p.id}>
                      <td>#{p.id}</td>
                      <td>{new Date(p.purchased_at).toLocaleDateString()}</td>
                      <td>
                        <strong>{p.supplier_name || `Supplier #${p.supplier_id}`}</strong>
                      </td>
                      <td>{p.invoice_number || '—'}</td>
                      <td>{p.item_count || '—'} items</td>
                      <td>
                        <strong style={{ color: 'var(--primary)' }}>
                          ৳{parseFloat(p.total_amount).toFixed(2)}
                        </strong>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}
                          onClick={async () => {
                            try {
                              const detail = await api.getPurchase(p.id);
                              setSelectedPurchaseDetail(detail);
                            } catch (err) {
                              alert(err.message || 'Failed to load details');
                            }
                          }}
                        >
                          View Voucher
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: SUPPLIERS DIRECTORY */}
      {activeTab === 'suppliers' && (
        <div>
          {suppliers.length === 0 ? (
            <div className="state-box">
              <h3>No suppliers found</h3>
              <button className="btn btn-primary" onClick={() => setShowSupplierModal(true)}>
                + Register First Supplier
              </button>
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Supplier / Company</th>
                    <th>Contact Person</th>
                    <th>Phone</th>
                    <th>Address</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {suppliers.map((s) => (
                    <tr key={s.id}>
                      <td>#{s.id}</td>
                      <td>
                        <strong>{s.name}</strong>
                      </td>
                      <td>{s.contact_person || '—'}</td>
                      <td>{s.phone ? <code>{s.phone}</code> : '—'}</td>
                      <td>{s.address || '—'}</td>
                      <td>
                        <span
                          style={{
                            fontSize: '0.8rem',
                            fontWeight: 600,
                            color: s.is_active ? 'var(--success)' : 'var(--danger)',
                          }}
                        >
                          {s.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modal: Quick Add Product (Write Option) */}
      {showQuickProductModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '500px' }}>
            <h2 style={{ marginBottom: '0.5rem' }}>+ Quick Add New Product</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
              Create a new catalog item immediately without leaving the purchase screen.
            </p>

            {quickProductError && <div className="error-banner">{quickProductError}</div>}

            <form onSubmit={handleSaveQuickProduct}>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Product Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={quickProductForm.name}
                  onChange={(e) => setQuickProductForm({ ...quickProductForm, name: e.target.value })}
                  placeholder="e.g. প্রাণ গুঁড়া মসলা (Pran Spices)"
                  required
                  autoFocus
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Category</label>
                  <select
                    className="form-select"
                    value={quickProductForm.category_id}
                    onChange={(e) => setQuickProductForm({ ...quickProductForm, category_id: e.target.value })}
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
                    value={quickProductForm.unit}
                    onChange={(e) => setQuickProductForm({ ...quickProductForm, unit: e.target.value })}
                    placeholder="kg, pcs, pkt, can"
                    required
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                <div className="form-group">
                  <label className="form-label">Cost Price (BDT)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    className="form-input"
                    value={quickProductForm.purchase_price}
                    onChange={(e) => setQuickProductForm({ ...quickProductForm, purchase_price: e.target.value })}
                    placeholder="0.00"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Selling Price (BDT) *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    className="form-input"
                    value={quickProductForm.sale_price}
                    onChange={(e) => setQuickProductForm({ ...quickProductForm, sale_price: e.target.value })}
                    placeholder="0.00"
                    required
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowQuickProductModal(false)}
                  disabled={quickProductSubmitting}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={quickProductSubmitting}>
                  {quickProductSubmitting ? 'Creating...' : 'Create & Select Product'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Add Supplier */}
      {showSupplierModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h2 style={{ marginBottom: '1rem' }}>Register New Supplier</h2>

            {supplierFormError && <div className="error-banner">{supplierFormError}</div>}

            <form onSubmit={handleSaveSupplier}>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Company / Supplier Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={supplierForm.name}
                  onChange={(e) => setSupplierForm({ ...supplierForm, name: e.target.value })}
                  placeholder="e.g. Square Consumer Products Ltd"
                  required
                  autoFocus
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Contact Person</label>
                  <input
                    type="text"
                    className="form-input"
                    value={supplierForm.contact_person}
                    onChange={(e) => setSupplierForm({ ...supplierForm, contact_person: e.target.value })}
                    placeholder="e.g. Mr. Rafiqul Islam"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Phone Number</label>
                  <input
                    type="text"
                    className="form-input"
                    value={supplierForm.phone}
                    onChange={(e) => setSupplierForm({ ...supplierForm, phone: e.target.value })}
                    placeholder="e.g. 01811223344"
                  />
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Email Address</label>
                <input
                  type="email"
                  className="form-input"
                  value={supplierForm.email}
                  onChange={(e) => setSupplierForm({ ...supplierForm, email: e.target.value })}
                  placeholder="supplier@example.com"
                />
              </div>

              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label className="form-label">Office / Warehouse Address</label>
                <input
                  type="text"
                  className="form-input"
                  value={supplierForm.address}
                  onChange={(e) => setSupplierForm({ ...supplierForm, address: e.target.value })}
                  placeholder="Tejgaon Industrial Area, Dhaka"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowSupplierModal(false)}
                  disabled={supplierSubmitting}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={supplierSubmitting}>
                  {supplierSubmitting ? 'Registering...' : 'Register Supplier'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: View Purchase Voucher Detail */}
      {selectedPurchaseDetail && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '650px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
              <div>
                <h2>Purchase Voucher #{selectedPurchaseDetail.id}</h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                  Supplier: <strong>{selectedPurchaseDetail.supplier?.name}</strong> • Date:{' '}
                  {new Date(selectedPurchaseDetail.purchased_at).toLocaleDateString()}
                </p>
                {selectedPurchaseDetail.invoice_number && (
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    Invoice Ref: <code>{selectedPurchaseDetail.invoice_number}</code>
                  </p>
                )}
              </div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--primary)' }}>
                ৳{parseFloat(selectedPurchaseDetail.total_amount).toFixed(2)}
              </div>
            </div>

            <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>Itemized Breakdown</h3>
            <div className="table-container" style={{ marginBottom: '1.5rem' }}>
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Quantity</th>
                    <th>Unit Cost</th>
                    <th style={{ textAlign: 'right' }}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedPurchaseDetail.items?.map((it) => (
                    <tr key={it.id}>
                      <td>
                        <strong>{it.product?.name || `Product #${it.product_id}`}</strong>
                      </td>
                      <td>
                        {it.quantity} {it.product?.unit || ''}
                      </td>
                      <td>৳{parseFloat(it.unit_cost).toFixed(2)}</td>
                      <td style={{ textAlign: 'right', fontWeight: 600 }}>
                        ৳{parseFloat(it.line_total).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ textAlign: 'right' }}>
              <button className="btn btn-secondary" onClick={() => setSelectedPurchaseDetail(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
