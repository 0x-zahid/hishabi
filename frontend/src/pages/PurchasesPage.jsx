import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function PurchasesPage() {
  const [activeTab, setActiveTab] = useState('record'); // 'record' | 'suppliers' | 'history'

  // Data
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
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

  // Selected Purchase for Detail Modal
  const [selectedPurchaseDetail, setSelectedPurchaseDetail] = useState(null);

  // Load initial suppliers & products
  const loadInitialData = async () => {
    try {
      setLoading(true);
      setError('');
      const [supRes, prodRes] = await Promise.all([
        api.getSuppliers(),
        api.getProducts({ limit: 100 }),
      ]);
      setSuppliers(supRes?.items || []);
      setProducts(prodRes?.items || []);
      if (supRes?.items?.length > 0 && !selectedSupplier) {
        setSelectedSupplier(supRes.items[0].id.toString());
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
      { product_id: products[0]?.id?.toString() || '', quantity: '1', unit_cost: '' },
    ]);
  };

  const handleRemoveItem = (index) => {
    if (purchaseItems.length === 1) return;
    setPurchaseItems(purchaseItems.filter((_, i) => i !== index));
  };

  const handleItemChange = (index, field, value) => {
    const updated = [...purchaseItems];
    updated[index][field] = value;

    // Auto-fill cost price if product changed and cost was empty
    if (field === 'product_id') {
      const prod = products.find((p) => p.id === parseInt(value));
      if (prod && !updated[index].unit_cost) {
        updated[index].unit_cost = prod.purchase_price || '0';
      }
    }

    setPurchaseItems(updated);
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
        setError(`Please select a product for line #${i + 1}.`);
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
        `Purchase #${result.id} recorded successfully! Stock has been updated automatically.`
      );
      // Reset form
      setInvoiceNumber('');
      setPurchaseItems([{ product_id: products[0]?.id?.toString() || '', quantity: '1', unit_cost: '' }]);

      // Refresh product stock list in background
      api.getProducts({ limit: 100 }).then((res) => setProducts(res?.items || []));
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
        <button className="btn btn-secondary" onClick={() => setShowSupplierModal(true)}>
          + Add New Supplier
        </button>
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
          <h2 style={{ fontSize: '1.25rem', marginBottom: '1.25rem', fontWeight: 700 }}>
            Inward Stock Entry (Purchase Voucher)
          </h2>

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
              <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>Purchase Line Items</h3>
              <div className="table-container" style={{ marginBottom: '1.25rem' }}>
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: '45%' }}>Product *</th>
                      <th style={{ width: '20%' }}>Quantity *</th>
                      <th style={{ width: '20%' }}>Unit Cost (BDT) *</th>
                      <th style={{ width: '15%', textAlign: 'right' }}>Line Total (BDT)</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {purchaseItems.map((item, idx) => {
                      const lineTotal = (parseFloat(item.quantity) || 0) * (parseFloat(item.unit_cost) || 0);
                      return (
                        <tr key={idx}>
                          <td>
                            <select
                              className="form-select"
                              value={item.product_id}
                              onChange={(e) => handleItemChange(idx, 'product_id', e.target.value)}
                              required
                            >
                              <option value="">-- Choose Product --</option>
                              {products.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.name} (Current Stock: {p.current_stock} {p.unit})
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <input
                              type="number"
                              step="0.001"
                              min="0.001"
                              className="form-input"
                              value={item.quantity}
                              onChange={(e) => handleItemChange(idx, 'quantity', e.target.value)}
                              required
                            />
                          </td>
                          <td>
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
                          </td>
                          <td style={{ textAlign: 'right', fontWeight: 600 }}>
                            ৳{lineTotal.toFixed(2)}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            {purchaseItems.length > 1 && (
                              <button
                                type="button"
                                className="btn btn-secondary"
                                style={{ padding: '0.2rem 0.5rem', color: 'var(--danger)', borderColor: '#fca5a5' }}
                                onClick={() => handleRemoveItem(idx)}
                                title="Remove item"
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
                  + Add Another Product
                </button>
                <div style={{ fontSize: '1.3rem', fontWeight: 800 }}>
                  Grand Total:{' '}
                  <span style={{ color: 'var(--primary)' }}>৳{grandTotal.toFixed(2)}</span>
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
