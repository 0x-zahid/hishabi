import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Quick Sale modal state
  const [showSaleModal, setShowSaleModal] = useState(false);
  const [products, setProducts] = useState([]);
  const [selectedProductId, setSelectedProductId] = useState('');
  const [saleQty, setSaleQty] = useState('1');
  const [saleNote, setSaleNote] = useState('');
  const [submittingSale, setSubmittingSale] = useState(false);
  const [saleSuccessMsg, setSaleSuccessMsg] = useState('');
  const [saleErrorMsg, setSaleErrorMsg] = useState('');

  const loadSummary = async () => {
    try {
      setLoading(true);
      setError('');
      const summary = await api.getDashboardSummary();
      setData(summary);
    } catch (err) {
      setError(err.message || 'Failed to load dashboard summary.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary();
  }, []);

  const openSaleModal = async () => {
    setShowSaleModal(true);
    setSaleErrorMsg('');
    try {
      const res = await api.getProducts({ limit: 100 });
      const activeProducts = (res?.items || []).filter((p) => p.is_active);
      setProducts(activeProducts);
      if (activeProducts.length > 0 && !selectedProductId) {
        setSelectedProductId(activeProducts[0].id.toString());
      }
    } catch (err) {
      setSaleErrorMsg('Failed to load products list.');
    }
  };

  const handleSaleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedProductId) {
      setSaleErrorMsg('Please select a product.');
      return;
    }
    const qtyNum = parseFloat(saleQty);
    if (!qtyNum || qtyNum <= 0) {
      setSaleErrorMsg('Quantity must be greater than 0.');
      return;
    }
    const prod = products.find((p) => p.id === parseInt(selectedProductId));
    if (prod && qtyNum > parseFloat(prod.current_stock)) {
      setSaleErrorMsg(`Insufficient stock. Only ${prod.current_stock} ${prod.unit} available.`);
      return;
    }

    try {
      setSubmittingSale(true);
      setSaleErrorMsg('');
      await api.recordStockMovement({
        product_id: parseInt(selectedProductId),
        movement_type: 'sale',
        quantity: qtyNum,
        note: saleNote.trim() || 'Retail cash sale',
      });
      setSaleSuccessMsg(
        `Sale recorded successfully! ${qtyNum} ${prod?.unit || 'unit(s)'} of ${prod?.name} deducted from inventory.`
      );
      setShowSaleModal(false);
      setSaleQty('1');
      setSaleNote('');
      await loadSummary();
    } catch (err) {
      setSaleErrorMsg(err.message || 'Failed to record sale.');
    } finally {
      setSubmittingSale(false);
    }
  };

  const selectedProduct = products.find((p) => p.id === parseInt(selectedProductId));
  const calculatedSaleTotal =
    selectedProduct && parseFloat(saleQty) > 0
      ? (parseFloat(saleQty) * parseFloat(selectedProduct.sale_price)).toFixed(2)
      : '0.00';

  if (loading) {
    return (
      <div className="state-box">
        <div className="spinner"></div>
        <p>Loading dashboard metrics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="state-box">
        <div className="error-banner">{error}</div>
        <button onClick={loadSummary} className="btn btn-primary">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 className="page-title">Owner Dashboard</h1>
          <p className="page-subtitle">Real-time overview of your shop's operations (Module 3 - Azaz 237)</p>
        </div>
        <button
          onClick={openSaleModal}
          className="btn btn-primary"
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1.2rem', fontSize: '0.95rem' }}
        >
          <span style={{ fontSize: '1.1rem' }}>⚡</span> + Record Quick Sale
        </button>
      </div>

      {saleSuccessMsg && (
        <div className="success-banner" style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>✓ {saleSuccessMsg}</span>
          <button onClick={() => setSaleSuccessMsg('')} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.2rem', color: 'inherit' }}>×</button>
        </div>
      )}

      {/* Top Metric Cards */}
      <div className="grid-cards">
        {/* Section 1: Today's Sales */}
        <div className="card">
          <div className="card-title">Today's Sales Amount</div>
          <div className="card-value">BDT {data?.today_sales_amount || '0.00'}</div>
          <div className="card-subtext">{data?.today_sales_count || 0} transaction(s) today</div>
        </div>

        {/* Section 2: Customer Dues */}
        <div className="card">
          <div className="card-title">Total Customer Dues</div>
          <div className="card-value" style={{ color: data?.total_customer_dues > 0 ? 'var(--danger)' : 'var(--text)' }}>
            BDT {data?.total_customer_dues || '0.00'}
          </div>
          <div className="card-subtext">Outstanding receivables</div>
        </div>

        {/* Section 3: Low-Stock Products Count */}
        <div className="card">
          <div className="card-title">Low-Stock Alert</div>
          <div className="card-value" style={{ color: data?.low_stock_count > 0 ? 'var(--warning)' : 'var(--success)' }}>
            {data?.low_stock_count || 0}
          </div>
          <div className="card-subtext">Product(s) at or below threshold</div>
        </div>
      </div>

      {/* Section 3 Details: Low-Stock Products Table */}
      <div style={{ marginBottom: '2.5rem' }}>
        <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.75rem' }}>
          Low-Stock Products ({data?.low_stock_count || 0})
        </h2>
        <div className="table-container">
          {data?.low_stock_products?.length === 0 ? (
            <div className="state-box">All products are adequately stocked!</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Product Name</th>
                  <th>Unit</th>
                  <th>Current Stock</th>
                  <th>Threshold</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data?.low_stock_products?.map((p) => (
                  <tr key={p.id}>
                    <td style={{ fontWeight: 600 }}>{p.name}</td>
                    <td>{p.unit}</td>
                    <td style={{ color: 'var(--danger)', fontWeight: 700 }}>{p.current_stock}</td>
                    <td>{p.low_stock_threshold}</td>
                    <td>
                      <span style={{ background: '#fef2f2', color: '#b91c1c', padding: '0.2rem 0.5rem', borderRadius: 4, fontSize: '0.75rem', fontWeight: 600 }}>
                        LOW STOCK
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Section 4: 10 Most Recent Transactions */}
      <div>
        <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.75rem' }}>
          Recent Transactions
        </h2>
        <div className="table-container">
          {data?.recent_transactions?.length === 0 ? (
            <div className="state-box">No recent transactions recorded yet.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Party / Item</th>
                  <th>Amount</th>
                  <th>Date & Time</th>
                </tr>
              </thead>
              <tbody>
                {data?.recent_transactions?.map((t) => (
                  <tr key={`${t.transaction_type}-${t.id}`}>
                    <td>#{t.id}</td>
                    <td>
                      <span style={{ textTransform: 'capitalize', fontWeight: 500 }}>
                        {t.transaction_type.replace('_', ' ')}
                      </span>
                    </td>
                    <td>{t.reference_name || '-'}</td>
                    <td style={{ fontWeight: 600 }}>{t.amount}</td>
                    <td style={{ color: 'var(--text-muted)' }}>
                      {new Date(t.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Quick Sale Modal */}
      {showSaleModal && (
        <div className="modal-overlay" onClick={() => !submittingSale && setShowSaleModal(false)}>
          <div className="modal-content" style={{ maxWidth: '500px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 700 }}>⚡ Record Quick Retail Sale</h2>
              <button
                onClick={() => !submittingSale && setShowSaleModal(false)}
                style={{ background: 'none', border: 'none', fontSize: '1.4rem', cursor: 'pointer' }}
              >
                ×
              </button>
            </div>

            {saleErrorMsg && <div className="error-banner" style={{ marginBottom: '1rem' }}>{saleErrorMsg}</div>}

            <form onSubmit={handleSaleSubmit}>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label" style={{ fontWeight: 600 }}>Select Product *</label>
                <select
                  className="form-control"
                  value={selectedProductId}
                  onChange={(e) => setSelectedProductId(e.target.value)}
                  required
                >
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} (Stock: {p.current_stock} {p.unit} • Price: ৳{p.sale_price})
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div className="form-group">
                  <label className="form-label" style={{ fontWeight: 600 }}>
                    Quantity ({selectedProduct?.unit || 'qty'}) *
                  </label>
                  <input
                    type="number"
                    min="0.001"
                    step="any"
                    className="form-control"
                    value={saleQty}
                    onChange={(e) => setSaleQty(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" style={{ fontWeight: 600 }}>Unit Price (BDT)</label>
                  <input
                    type="text"
                    className="form-control"
                    value={selectedProduct ? `৳${selectedProduct.sale_price}` : '৳0.00'}
                    readOnly
                    disabled
                  />
                </div>
              </div>

              <div style={{ background: '#f8fafc', padding: '0.75rem 1rem', borderRadius: '6px', marginBottom: '1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, color: 'var(--text-muted)' }}>Calculated Total:</span>
                <span style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--primary)' }}>
                  ৳{calculatedSaleTotal}
                </span>
              </div>

              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label className="form-label">Note / Invoice (Optional)</label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. Retail cash sale"
                  value={saleNote}
                  onChange={(e) => setSaleNote(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={submittingSale}
                  onClick={() => setShowSaleModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={submittingSale}>
                  {submittingSale ? 'Processing...' : 'Confirm Sale & Deduct Stock'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
