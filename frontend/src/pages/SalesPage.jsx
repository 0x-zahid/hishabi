import React, { useEffect, useState } from 'react';
import { getSale, getSales } from '../api/sales';

/**
 * Sales history page.
 *
 * The list shows every recorded sale with its date, customer, payment type,
 * total and item count. The endpoint supports a date range and a payment type
 * filter, so both are offered in the filter bar.
 *
 * Clicking a sale opens its items.
 */

const PAGE_SIZE = 20;

export default function SalesPage() {
  const [sales, setSales] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  // Filters
  const [paymentType, setPaymentType] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Detail modal
  const [selectedSale, setSelectedSale] = useState(null);
  const [saleItems, setSaleItems] = useState([]);
  const [salePayments, setSalePayments] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');

  const fetchSales = async (currentPage = 1) => {
    try {
      setLoading(true);
      setError('');
      const res = await getSales({
        page: currentPage,
        page_size: PAGE_SIZE,
        payment_type: paymentType,
        start_date: startDate,
        end_date: endDate,
      });
      setSales(res?.items || []);
      setTotal(res?.total || 0);
      setPage(currentPage);
    } catch (err) {
      setError(err.message || 'Failed to load sales.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSales(1);
  }, []);

  const handleRowClick = async (saleId) => {
    setSelectedSale(saleId);
    setSaleItems([]);
    setSalePayments([]);
    setDetailError('');
    setDetailLoading(true);
    try {
      const detail = await getSale(saleId);
      setSaleItems(detail?.items || []);
      setSalePayments(detail?.payments || []);
    } catch (err) {
      setDetailError(err.message || 'Failed to fetch the sale details.');
    } finally {
      setDetailLoading(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Sales</h1>
        <p className="page-subtitle">Every recorded sale, newest first</p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Filter Bar */}
      <div className="filter-bar">
        <div className="form-group">
          <label className="form-label">Payment Type</label>
          <select
            className="form-select"
            value={paymentType}
            onChange={(e) => setPaymentType(e.target.value)}
          >
            <option value="">All Payments</option>
            <option value="cash">Cash</option>
            <option value="credit">Credit</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">From Date</label>
          <input
            type="date"
            className="form-input"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">To Date</label>
          <input
            type="date"
            className="form-input"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>

        <button
          onClick={() => fetchSales(1)}
          className="btn btn-primary"
          disabled={loading}
        >
          {loading ? 'Filtering...' : 'Filter'}
        </button>
      </div>

      {/* Table */}
      <div className="table-container">
        {loading ? (
          <div className="state-box">
            <div className="spinner"></div>
            <p>Loading sales...</p>
          </div>
        ) : sales.length === 0 ? (
          <div className="state-box">No sales matching your criteria.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Date & Time</th>
                <th>Customer</th>
                <th>Payment Type</th>
                <th>Total</th>
                <th>Items</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {sales.map((sale) => (
                <tr
                  key={sale.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => handleRowClick(sale.id)}
                >
                  <td>#{sale.id}</td>
                  <td>{new Date(sale.created_at).toLocaleString()}</td>
                  <td style={{ fontWeight: 600 }}>{sale.customer_name || 'Walk-in'}</td>
                  <td>
                    <span
                      style={{
                        padding: '0.2rem 0.5rem',
                        borderRadius: 4,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        textTransform: 'capitalize',
                        background: sale.payment_type === 'cash' ? '#ecfdf5' : '#fff7ed',
                        color: sale.payment_type === 'cash' ? '#065f46' : '#9a3412',
                      }}
                    >
                      {sale.payment_type}
                    </span>
                  </td>
                  <td style={{ fontWeight: 600 }}>BDT {sale.total_amount}</td>
                  <td>{sale.item_count ?? sale.items?.length ?? 0}</td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.2rem 0.6rem', fontSize: '0.8rem' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRowClick(sale.id);
                      }}
                    >
                      View items
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total} sales
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              disabled={page === 1 || loading}
              onClick={() => fetchSales(page - 1)}
            >
              Previous
            </button>
            <span style={{ display: 'flex', alignItems: 'center', padding: '0 0.5rem', fontSize: '0.9rem' }}>
              Page {page} of {totalPages}
            </span>
            <button
              className="btn btn-secondary"
              disabled={page * PAGE_SIZE >= total || loading}
              onClick={() => fetchSales(page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {selectedSale && (
        <div className="modal-overlay" onClick={() => setSelectedSale(null)}>
          <div
            className="modal-content"
            style={{ maxWidth: '720px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                Sale #{selectedSale}
              </h2>
              <button
                onClick={() => setSelectedSale(null)}
                style={{ background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>

            {detailLoading ? (
              <div className="state-box">
                <div className="spinner"></div>
                <p>Loading sale items...</p>
              </div>
            ) : (
              <>
                {detailError && <div className="error-banner">{detailError}</div>}

                <div className="table-container">
                  {saleItems.length === 0 ? (
                    <div className="state-box">This sale has no items.</div>
                  ) : (
                    <table>
                      <thead>
                        <tr>
                          <th>Product</th>
                          <th>Quantity</th>
                          <th>Unit Price</th>
                          <th>Line Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {saleItems.map((item) => (
                          <tr key={item.id}>
                            <td style={{ fontWeight: 600 }}>
                              {item.product_name || `Product #${item.product_id}`}
                            </td>
                            <td>
                              {item.quantity} {item.unit || ''}
                            </td>
                            <td>BDT {item.unit_price}</td>
                            <td style={{ fontWeight: 600 }}>BDT {item.line_total}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {salePayments.length > 0 && (
                  <>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                      Payments against this sale
                    </h3>
                    <div className="table-container">
                      <table>
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th>Amount</th>
                            <th>Method</th>
                          </tr>
                        </thead>
                        <tbody>
                          {salePayments.map((payment) => (
                            <tr key={payment.id}>
                              <td>{new Date(payment.created_at).toLocaleString()}</td>
                              <td style={{ fontWeight: 600, color: 'var(--success)' }}>
                                BDT {payment.amount}
                              </td>
                              <td>{payment.payment_method || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}

                <div style={{ marginTop: '1.5rem', textAlign: 'right' }}>
                  <button onClick={() => setSelectedSale(null)} className="btn btn-primary">
                    Close
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
