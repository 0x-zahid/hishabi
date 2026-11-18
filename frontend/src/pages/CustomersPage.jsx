import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function CustomersPage() {
  const [customers, setCustomers] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Filters
  const [search, setSearch] = useState('');
  const [activeOnly, setActiveOnly] = useState(true);

  // Modals & Drawers
  const [showModal, setShowModal] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState(null);
  const [viewingHistory, setViewingHistory] = useState(null);
  const [historyData, setHistoryData] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Form State
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    email: '',
    address: '',
    note: '',
  });
  const [formError, setFormError] = useState('');
  const [formSubmitting, setFormSubmitting] = useState(false);

  const fetchCustomers = async () => {
    try {
      setLoading(true);
      setError('');
      const res = await api.getCustomers({
        search: search.trim() || undefined,
        is_active: activeOnly ? true : undefined,
      });
      setCustomers(res?.items || []);
      setTotal(res?.total || 0);
    } catch (err) {
      setError(err.message || 'Failed to load customers');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCustomers();
  }, [activeOnly]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    fetchCustomers();
  };

  const openAddModal = () => {
    setEditingCustomer(null);
    setFormData({ name: '', phone: '', email: '', address: '', note: '' });
    setFormError('');
    setShowModal(true);
  };

  const openEditModal = (cust) => {
    setEditingCustomer(cust);
    setFormData({
      name: cust.name,
      phone: cust.phone || '',
      email: cust.email || '',
      address: cust.address || '',
      note: cust.note || '',
    });
    setFormError('');
    setShowModal(true);
  };

  const handleSaveCustomer = async (e) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setFormError('Customer name is required.');
      return;
    }

    try {
      setFormSubmitting(true);
      setFormError('');

      if (editingCustomer) {
        await api.updateCustomer(editingCustomer.id, {
          name: formData.name.trim(),
          phone: formData.phone.trim() || null,
          email: formData.email.trim() || null,
          address: formData.address.trim() || null,
          note: formData.note.trim() || null,
        });
      } else {
        await api.createCustomer({
          name: formData.name.trim(),
          phone: formData.phone.trim() || null,
          email: formData.email.trim() || null,
          address: formData.address.trim() || null,
          note: formData.note.trim() || null,
        });
      }

      setShowModal(false);
      fetchCustomers();
    } catch (err) {
      setFormError(err.message || 'Failed to save customer');
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleDeactivate = async (cust) => {
    if (!window.confirm(`Deactivate customer "${cust.name}"? Past records will remain intact.`)) {
      return;
    }
    try {
      await api.deactivateCustomer(cust.id);
      fetchCustomers();
    } catch (err) {
      alert(err.message || 'Failed to deactivate customer');
    }
  };

  const handleViewHistory = async (cust) => {
    setViewingHistory(cust);
    setHistoryData(null);
    setHistoryLoading(true);
    try {
      const data = await api.getCustomerHistory(cust.id);
      setHistoryData(data);
    } catch (err) {
      alert(err.message || 'Failed to load history');
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">Customer Management</h1>
          <p className="page-subtitle">Module 2 (Azaz - 237): Retail customer records, profiles, and ledger history.</p>
        </div>
        <button className="btn btn-primary" onClick={openAddModal}>
          + Add Customer
        </button>
      </div>

      {/* Filter Bar */}
      <form onSubmit={handleSearchSubmit} className="filter-bar">
        <div className="form-group" style={{ flex: 1, minWidth: '220px' }}>
          <label className="form-label">Search Customer</label>
          <input
            type="text"
            className="form-input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Type customer name or phone and press Enter..."
          />
        </div>

        <div className="form-group" style={{ minWidth: '150px' }}>
          <label className="form-label">Status Filter</label>
          <select
            className="form-select"
            value={activeOnly ? 'active' : 'all'}
            onChange={(e) => setActiveOnly(e.target.value === 'active')}
          >
            <option value="active">Active Only</option>
            <option value="all">All Customers</option>
          </select>
        </div>

        <button type="submit" className="btn btn-primary">
          Search
        </button>
        {search && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setSearch('');
              api.getCustomers().then((res) => {
                setCustomers(res?.items || []);
                setTotal(res?.total || 0);
              });
            }}
          >
            Reset
          </button>
        )}
      </form>

      {error && <div className="error-banner">{error}</div>}

      {/* Customers Table */}
      {loading ? (
        <div className="state-box">
          <div className="spinner" />
          <p>Loading customers...</p>
        </div>
      ) : customers.length === 0 ? (
        <div className="state-box">
          <h3>No customers found</h3>
          <p>Click "+ Add Customer" to register your first retail customer.</p>
        </div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Phone Number</th>
                <th>Address</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.id}>
                  <td>#{c.id}</td>
                  <td>
                    <strong>{c.name}</strong>
                    {c.note && (
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{c.note}</div>
                    )}
                  </td>
                  <td>
                    {c.phone ? (
                      <code style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: '4px' }}>
                        {c.phone}
                      </code>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>{c.address || '—'}</td>
                  <td>
                    <span
                      style={{
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        color: c.is_active ? 'var(--success)' : 'var(--danger)',
                      }}
                    >
                      {c.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem', marginRight: '0.4rem' }}
                      onClick={() => handleViewHistory(c)}
                    >
                      History
                    </button>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem', marginRight: '0.4rem' }}
                      onClick={() => openEditModal(c)}
                    >
                      Edit
                    </button>
                    {c.is_active && (
                      <button
                        className="btn btn-secondary"
                        style={{
                          padding: '0.25rem 0.6rem',
                          fontSize: '0.8rem',
                          color: 'var(--danger)',
                          borderColor: '#fecaca',
                        }}
                        onClick={() => handleDeactivate(c)}
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ padding: '0.75rem 1rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Showing {customers.length} of {total} registered customers
          </div>
        </div>
      )}

      {/* Add / Edit Modal */}
      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h2 style={{ marginBottom: '1rem' }}>
              {editingCustomer ? 'Edit Customer' : 'Add New Customer'}
            </h2>

            {formError && <div className="error-banner">{formError}</div>}

            <form onSubmit={handleSaveCustomer}>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Full Name *</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. হাসান আলী (Hasan Ali)"
                  required
                  autoFocus
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div className="form-group">
                  <label className="form-label">Phone Number</label>
                  <input
                    type="text"
                    className="form-input"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    placeholder="e.g. 01711001122"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Email Address (Optional)</label>
                  <input
                    type="email"
                    className="form-input"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    placeholder="customer@example.com"
                  />
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Address</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  placeholder="Shop #4, Market road, Dhaka"
                />
              </div>

              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label className="form-label">Note</label>
                <input
                  type="text"
                  className="form-input"
                  value={formData.note}
                  onChange={(e) => setFormData({ ...formData, note: e.target.value })}
                  placeholder="e.g. Regular monthly customer"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowModal(false)}
                  disabled={formSubmitting}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={formSubmitting}>
                  {formSubmitting ? 'Saving...' : editingCustomer ? 'Save Changes' : 'Create Customer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Customer Profile & History Modal */}
      {viewingHistory && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '650px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem' }}>
              <div>
                <h2 style={{ fontSize: '1.4rem', fontWeight: 700 }}>{viewingHistory.name}</h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                  Customer #{viewingHistory.id} • {viewingHistory.phone || 'No phone'} • {viewingHistory.address || 'No address'}
                </p>
              </div>
              <span
                style={{
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: '9999px',
                  backgroundColor: viewingHistory.is_active ? '#ecfdf5' : '#fee2e2',
                  color: viewingHistory.is_active ? '#065f46' : '#b91c1c',
                }}
              >
                {viewingHistory.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>

            {historyLoading ? (
              <div className="state-box">
                <div className="spinner" />
                <p>Loading customer history...</p>
              </div>
            ) : (
              <div>
                {/* Financial Summary Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                  <div className="card" style={{ padding: '1rem', textAlign: 'center' }}>
                    <div className="card-title" style={{ fontSize: '0.75rem' }}>Total Purchases</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                      ৳{parseFloat(historyData?.summary?.total_purchases || 0).toFixed(2)}
                    </div>
                  </div>
                  <div className="card" style={{ padding: '1rem', textAlign: 'center' }}>
                    <div className="card-title" style={{ fontSize: '0.75rem' }}>Total Paid</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--success)' }}>
                      ৳{parseFloat(historyData?.summary?.total_paid || 0).toFixed(2)}
                    </div>
                  </div>
                  <div className="card" style={{ padding: '1rem', textAlign: 'center' }}>
                    <div className="card-title" style={{ fontSize: '0.75rem' }}>Current Due</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--danger)' }}>
                      ৳{parseFloat(historyData?.summary?.current_due || 0).toFixed(2)}
                    </div>
                  </div>
                </div>

                {/* History Section */}
                <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>Recent Activity &amp; Transactions</h3>
                {(!historyData?.recent_activity || historyData.recent_activity.length === 0) ? (
                  <div style={{ padding: '1.5rem', background: '#f8fafc', borderRadius: '8px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No purchase or credit history recorded for this customer yet.
                  </div>
                ) : (
                  <div style={{ maxHeight: '200px', overflowY: 'auto', border: '1px solid var(--border)', borderRadius: '6px' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Activity</th>
                          <th>Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {historyData.recent_activity.map((act, idx) => (
                          <tr key={idx}>
                            <td>{new Date(act.created_at).toLocaleDateString()}</td>
                            <td>{act.description}</td>
                            <td>৳{parseFloat(act.amount).toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            <div style={{ marginTop: '1.5rem', textAlign: 'right' }}>
              <button className="btn btn-secondary" onClick={() => setViewingHistory(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
