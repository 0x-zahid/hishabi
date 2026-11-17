import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

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
      <div className="page-header">
        <h1 className="page-title">Owner Dashboard</h1>
        <p className="page-subtitle">Real-time overview of your shop's operations</p>
      </div>

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
    </div>
  );
}
