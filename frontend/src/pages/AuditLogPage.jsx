import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function AuditLogPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const limit = 20;

  // Filters
  const [action, setAction] = useState('');
  const [entityType, setEntityType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Detail Modal
  const [selectedLog, setSelectedLog] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchLogs = async (currentSkip = 0) => {
    try {
      setLoading(true);
      setError('');
      const res = await api.getAuditLogs({
        action,
        entity_type: entityType,
        date_from: dateFrom,
        date_to: dateTo,
        skip: currentSkip,
        limit,
      });
      setItems(res.items || []);
      setTotal(res.total || 0);
      setSkip(currentSkip);
    } catch (err) {
      setError(err.message || 'Failed to load audit logs.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs(0);
  }, []);

  const handleRowClick = async (logId) => {
    try {
      setDetailLoading(true);
      const detail = await api.getAuditDetail(logId);
      setSelectedLog(detail);
    } catch (err) {
      setError(err.message || 'Failed to fetch audit log detail.');
    } finally {
      setDetailLoading(false);
    }
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(skip / limit) + 1;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">System Audit Log</h1>
        <p className="page-subtitle">Security trail of all critical operations and modifications</p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Filter Bar */}
      <div className="filter-bar">
        <div className="form-group">
          <label className="form-label">Action</label>
          <select
            className="form-select"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          >
            <option value="">All Actions</option>
            <option value="create">create</option>
            <option value="update">update</option>
            <option value="delete">delete</option>
            <option value="stock_movement">stock_movement</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Entity Type</label>
          <select
            className="form-select"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
          >
            <option value="">All Entities</option>
            <option value="product">product</option>
            <option value="customer">customer</option>
            <option value="supplier">supplier</option>
            <option value="purchase">purchase</option>
            <option value="stock_movement">stock_movement</option>
            <option value="user">user</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">From Date</label>
          <input
            type="date"
            className="form-input"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">To Date</label>
          <input
            type="date"
            className="form-input"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </div>

        <button
          onClick={() => fetchLogs(0)}
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
            <p>Loading audit entries...</p>
          </div>
        ) : items.length === 0 ? (
          <div className="state-box">No audit records matching your criteria.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Date & Time</th>
                <th>User</th>
                <th>Action</th>
                <th>Entity Type</th>
                <th>Entity ID</th>
                <th>IP Address</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((log) => (
                <tr
                  key={log.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => handleRowClick(log.id)}
                >
                  <td>{new Date(log.created_at).toLocaleString()}</td>
                  <td style={{ fontWeight: 600 }}>{log.username || `User #${log.user_id || 'System'}`}</td>
                  <td>
                    <span style={{
                      padding: '0.2rem 0.5rem',
                      borderRadius: 4,
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      background: log.action === 'create' ? '#ecfdf5' : log.action === 'delete' ? '#fef2f2' : '#eff6ff',
                      color: log.action === 'create' ? '#065f46' : log.action === 'delete' ? '#991b1b' : '#1e40af',
                    }}>
                      {log.action}
                    </span>
                  </td>
                  <td><code>{log.entity_type}</code></td>
                  <td>{log.entity_id ? `#${log.entity_id}` : '-'}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{log.ip_address || '-'}</td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.2rem 0.6rem', fontSize: '0.8rem' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRowClick(log.id);
                      }}
                    >
                      View Diff
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
            Showing {skip + 1}–{Math.min(skip + limit, total)} of {total} records
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              disabled={skip === 0 || loading}
              onClick={() => fetchLogs(Math.max(0, skip - limit))}
            >
              Previous
            </button>
            <span style={{ display: 'flex', alignItems: 'center', padding: '0 0.5rem', fontSize: '0.9rem' }}>
              Page {currentPage} of {totalPages}
            </span>
            <button
              className="btn btn-secondary"
              disabled={skip + limit >= total || loading}
              onClick={() => fetchLogs(skip + limit)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {selectedLog && (
        <div className="modal-overlay" onClick={() => setSelectedLog(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                Audit Record #{selectedLog.id}
              </h2>
              <button
                onClick={() => setSelectedLog(null)}
                style={{ background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.25rem', fontSize: '0.85rem' }}>
              <div><strong>Action:</strong> {selectedLog.action}</div>
              <div><strong>Entity:</strong> {selectedLog.entity_type} #{selectedLog.entity_id || '-'}</div>
              <div><strong>User:</strong> {selectedLog.username || `ID ${selectedLog.user_id}`}</div>
              <div><strong>IP:</strong> {selectedLog.ip_address || '-'}</div>
              <div style={{ gridColumn: '1 / -1' }}>
                <strong>Timestamp:</strong> {new Date(selectedLog.created_at).toLocaleString()}
              </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#64748b', marginBottom: '0.25rem' }}>
                State Before Change (old_value):
              </h3>
              <pre>
                {selectedLog.old_value ? JSON.stringify(selectedLog.old_value, null, 2) : '(none - created)'}
              </pre>
            </div>

            <div>
              <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#64748b', marginBottom: '0.25rem' }}>
                State After Change (new_value):
              </h3>
              <pre>
                {selectedLog.new_value ? JSON.stringify(selectedLog.new_value, null, 2) : '(none - deleted)'}
              </pre>
            </div>

            <div style={{ marginTop: '1.5rem', textAlign: 'right' }}>
              <button onClick={() => setSelectedLog(null)} className="btn btn-primary">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
