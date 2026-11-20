import React, { useEffect, useState } from 'react';
import {
  createCustomer,
  getCustomerDue,
  getCustomerDues,
  getCustomerHistory,
  getCustomerPayments,
  getCustomers,
  getCustomerSales,
} from '../api/customers';

/**
 * Customer management page.
 *
 * The table lists every customer with their phone number and their current
 * due. The due is read from the server (`/api/v1/customers/due`), never
 * computed in the browser.
 *
 * Clicking a customer opens their profile: the due breakdown from
 * `/api/v1/customers/{id}/due`, their sales history from `/api/v1/sales` and
 * their payment history from `/api/v1/payments`.
 */

const EMPTY_CUSTOMER = {
  name: '',
  phone: '',
  email: '',
  address: '',
};

export default function CustomersPage() {
  const [customers, setCustomers] = useState([]);
  const [dues, setDues] = useState({});
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [search, setSearch] = useState('');
  const limit = 20;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Create form
  const [form, setForm] = useState(EMPTY_CUSTOMER);
  const [saving, setSaving] = useState(false);

  // Profile modal
  const [selected, setSelected] = useState(null);
  const [profile, setProfile] = useState(null);
  const [due, setDue] = useState(null);
  const [sales, setSales] = useState([]);
  const [payments, setPayments] = useState([]);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState('');

  const fetchCustomers = async (currentSkip = 0, currentSearch = '') => {
    try {
      setLoading(true);
      setError('');
      const res = await getCustomers({
        skip: currentSkip,
        limit,
        search: currentSearch,
      });
      setCustomers(res?.items || []);
      setTotal(res?.total || 0);
      setSkip(currentSkip);

      // The due lives on the server, so it is read from the dues endpoint and
      // matched to the customer by id.
      try {
        const dueRes = await getCustomerDues();
        const map = {};
        (dueRes?.items || []).forEach((item) => {
          map[item.customer_id] = item.current_due;
        });
        setDues(map);
      } catch {
        setDues({});
      }
    } catch (err) {
      setError(err.message || 'Failed to load customers.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCustomers(0);
  }, []);

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) {
      setError('A customer needs a name.');
      return;
    }
    try {
      setSaving(true);
      setError('');
      setSuccess('');
      const created = await createCustomer({
        name: form.name.trim(),
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        address: form.address.trim() || null,
      });
      setSuccess(`Customer "${created.name}" was created.`);
      setForm(EMPTY_CUSTOMER);
      fetchCustomers(0);
    } catch (err) {
      setError(err.message || 'Failed to create the customer.');
    } finally {
      setSaving(false);
    }
  };

  const openProfile = async (customer) => {
    setSelected(customer);
    setProfile(null);
    setDue(null);
    setSales([]);
    setPayments([]);
    setProfileError('');
    setProfileLoading(true);
    try {
      // Each part is loaded on its own so one failure does not hide the rest.
      const [historyRes, dueRes, salesRes, paymentsRes] = await Promise.all([
        getCustomerHistory(customer.id),
        getCustomerDue(customer.id),
        getCustomerSales(customer.id),
        getCustomerPayments(customer.id),
      ]);
      setProfile(historyRes?.customer || customer);
      setDue(dueRes);
      setSales(salesRes?.items || []);
      setPayments(paymentsRes?.items || []);
    } catch (err) {
      setProfileError(err.message || 'Failed to load the customer profile.');
    } finally {
      setProfileLoading(false);
    }
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(skip / limit) + 1;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Customers</h1>
        <p className="page-subtitle">Who buys from you, what they owe and what they have paid</p>
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
            placeholder="Name or phone"
          />
        </div>

        <button
          onClick={() => fetchCustomers(0, search)}
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
            <p>Loading customers...</p>
          </div>
        ) : customers.length === 0 ? (
          <div className="state-box">No customers found. Add your first customer below.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone</th>
                <th>Current Due</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((customer) => {
                const dueAmount = dues[customer.id];
                return (
                  <tr
                    key={customer.id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => openProfile(customer)}
                  >
                    <td style={{ fontWeight: 600 }}>{customer.name}</td>
                    <td>{customer.phone || '-'}</td>
                    <td
                      style={{
                        fontWeight: 700,
                        color:
                          dueAmount !== undefined && Number(dueAmount) > 0
                            ? 'var(--danger)'
                            : 'var(--text)',
                      }}
                    >
                      {dueAmount !== undefined ? `BDT ${dueAmount}` : '-'}
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '0.2rem 0.6rem', fontSize: '0.8rem' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          openProfile(customer);
                        }}
                      >
                        View profile
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
            Showing {skip + 1}–{Math.min(skip + limit, total)} of {total} customers
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              disabled={skip === 0 || loading}
              onClick={() => fetchCustomers(Math.max(0, skip - limit), search)}
            >
              Previous
            </button>
            <span style={{ display: 'flex', alignItems: 'center', padding: '0 0.5rem', fontSize: '0.9rem' }}>
              Page {currentPage} of {totalPages}
            </span>
            <button
              className="btn btn-secondary"
              disabled={skip + limit >= total || loading}
              onClick={() => fetchCustomers(skip + limit, search)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Create Form */}
      <div className="card">
        <div className="card-title">Add a customer</div>
        <p className="card-subtext" style={{ marginBottom: '1rem' }}>
          Only the name is required. The phone number must be unique when it is given.
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
              />
            </div>

            <div className="form-group">
              <label className="form-label">Phone</label>
              <input
                type="text"
                className="form-input"
                style={{ width: '160px' }}
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="01711000001"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Email</label>
              <input
                type="email"
                className="form-input"
                style={{ width: '200px' }}
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Address</label>
              <input
                type="text"
                className="form-input"
                style={{ width: '200px' }}
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
              />
            </div>
          </div>

          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Creating...' : 'Create customer'}
          </button>
        </form>
      </div>

      {/* Customer Profile Modal */}
      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div
            className="modal-content"
            style={{ maxWidth: '760px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                {profile?.name || selected.name}
              </h2>
              <button
                onClick={() => setSelected(null)}
                style={{ background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>

            {profileLoading ? (
              <div className="state-box">
                <div className="spinner"></div>
                <p>Loading customer profile...</p>
              </div>
            ) : (
              <>
                {profileError && <div className="error-banner">{profileError}</div>}

                {/* Contact details */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '0.75rem',
                    marginBottom: '1.25rem',
                    fontSize: '0.85rem',
                  }}
                >
                  <div><strong>Phone:</strong> {profile?.phone || '-'}</div>
                  <div><strong>Email:</strong> {profile?.email || '-'}</div>
                  <div><strong>Address:</strong> {profile?.address || '-'}</div>
                  <div>
                    <strong>Member since:</strong>{' '}
                    {profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : '-'}
                  </div>
                </div>

                {/* Due breakdown */}
                <div className="grid-cards" style={{ marginBottom: '1.5rem' }}>
                  <div className="card">
                    <div className="card-title">Total Credit Sales</div>
                    <div className="card-value" style={{ fontSize: '1.25rem' }}>
                      BDT {due?.total_credit_sales ?? '-'}
                    </div>
                    <div className="card-subtext">{due?.sale_count ?? 0} credit sale(s)</div>
                  </div>
                  <div className="card">
                    <div className="card-title">Total Paid</div>
                    <div className="card-value" style={{ fontSize: '1.25rem', color: 'var(--success)' }}>
                      BDT {due?.total_paid ?? '-'}
                    </div>
                    <div className="card-subtext">{due?.payment_count ?? 0} payment(s)</div>
                  </div>
                  <div className="card">
                    <div className="card-title">Current Due</div>
                    <div
                      className="card-value"
                      style={{
                        fontSize: '1.25rem',
                        color:
                          due && Number(due.current_due) > 0 ? 'var(--danger)' : 'var(--success)',
                      }}
                    >
                      BDT {due?.current_due ?? '-'}
                    </div>
                    <div className="card-subtext">Computed by the server</div>
                  </div>
                </div>

                {/* Sales history */}
                <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                  Sales history
                </h3>
                <div className="table-container">
                  {sales.length === 0 ? (
                    <div className="state-box">No sales recorded for this customer.</div>
                  ) : (
                    <table>
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Type</th>
                          <th>Total</th>
                          <th>Paid</th>
                          <th>Due</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sales.map((sale) => (
                          <tr key={sale.id}>
                            <td>{new Date(sale.created_at).toLocaleString()}</td>
                            <td style={{ textTransform: 'capitalize' }}>{sale.payment_type}</td>
                            <td style={{ fontWeight: 600 }}>BDT {sale.total_amount}</td>
                            <td>BDT {sale.paid_amount}</td>
                            <td
                              style={{
                                color: Number(sale.due_amount) > 0 ? 'var(--danger)' : 'var(--text)',
                              }}
                            >
                              BDT {sale.due_amount}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* Payment history */}
                <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                  Payment history
                </h3>
                <div className="table-container">
                  {payments.length === 0 ? (
                    <div className="state-box">No payments recorded for this customer.</div>
                  ) : (
                    <table>
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Amount</th>
                          <th>Method</th>
                          <th>Note</th>
                        </tr>
                      </thead>
                      <tbody>
                        {payments.map((payment) => (
                          <tr key={payment.id}>
                            <td>{new Date(payment.created_at).toLocaleString()}</td>
                            <td style={{ fontWeight: 600, color: 'var(--success)' }}>
                              BDT {payment.amount}
                            </td>
                            <td>{payment.payment_method || '-'}</td>
                            <td style={{ color: 'var(--text-muted)' }}>{payment.note || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                <div style={{ marginTop: '1.5rem', textAlign: 'right' }}>
                  <button onClick={() => setSelected(null)} className="btn btn-primary">
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
