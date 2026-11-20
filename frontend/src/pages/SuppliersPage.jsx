import React, { useEffect, useState } from 'react';
import { createSupplier, getSupplier, getSupplierPurchases, getSuppliers } from '../api/suppliers';

/**
 * Supplier management page.
 *
 * The table lists every supplier with their phone number and contact
 * details. Clicking a supplier opens their profile: the purchase statistics
 * from `/api/v1/suppliers/{id}` and the purchases recorded for them from
 * `/api/v1/suppliers/{id}/purchases`.
 */

const EMPTY_SUPPLIER = {
  name: '',
  phone: '',
  email: '',
  contact_person: '',
  address: '',
};

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [search, setSearch] = useState('');
  const limit = 20;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Create form
  const [form, setForm] = useState(EMPTY_SUPPLIER);
  const [saving, setSaving] = useState(false);

  // Profile modal
  const [selected, setSelected] = useState(null);
  const [profile, setProfile] = useState(null);
  const [purchases, setPurchases] = useState([]);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState('');

  const fetchSuppliers = async (currentSkip = 0, currentSearch = '') => {
    try {
      setLoading(true);
      setError('');
      const res = await getSuppliers({
        skip: currentSkip,
        limit,
        search: currentSearch,
      });
      setSuppliers(res?.items || []);
      setTotal(res?.total || 0);
      setSkip(currentSkip);
    } catch (err) {
      setError(err.message || 'Failed to load suppliers.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSuppliers(0);
  }, []);

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) {
      setError('A supplier needs a name.');
      return;
    }
    try {
      setSaving(true);
      setError('');
      setSuccess('');
      const created = await createSupplier({
        name: form.name.trim(),
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        contact_person: form.contact_person.trim() || null,
        address: form.address.trim() || null,
      });
      setSuccess(`Supplier "${created.name}" was created.`);
      setForm(EMPTY_SUPPLIER);
      fetchSuppliers(0);
    } catch (err) {
      setError(err.message || 'Failed to create the supplier.');
    } finally {
      setSaving(false);
    }
  };

  const openProfile = async (supplier) => {
    setSelected(supplier);
    setProfile(null);
    setPurchases([]);
    setProfileError('');
    setProfileLoading(true);
    try {
      const [detailRes, purchasesRes] = await Promise.all([
        getSupplier(supplier.id),
        getSupplierPurchases(supplier.id),
      ]);
      setProfile(detailRes);
      setPurchases(purchasesRes?.items || []);
    } catch (err) {
      setProfileError(err.message || 'Failed to load the supplier profile.');
    } finally {
      setProfileLoading(false);
    }
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(skip / limit) + 1;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Suppliers</h1>
        <p className="page-subtitle">Who you buy from and what you have bought from them</p>
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
            placeholder="Name, phone or contact person"
          />
        </div>

        <button
          onClick={() => fetchSuppliers(0, search)}
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
            <p>Loading suppliers...</p>
          </div>
        ) : suppliers.length === 0 ? (
          <div className="state-box">No suppliers found. Add your first supplier below.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone</th>
                <th>Contact Person</th>
                <th>Email</th>
                <th>Address</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map((supplier) => (
                <tr
                  key={supplier.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => openProfile(supplier)}
                >
                  <td style={{ fontWeight: 600 }}>{supplier.name}</td>
                  <td>{supplier.phone || '-'}</td>
                  <td>{supplier.contact_person || '-'}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{supplier.email || '-'}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{supplier.address || '-'}</td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.2rem 0.6rem', fontSize: '0.8rem' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        openProfile(supplier);
                      }}
                    >
                      View purchases
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
            Showing {skip + 1}–{Math.min(skip + limit, total)} of {total} suppliers
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              disabled={skip === 0 || loading}
              onClick={() => fetchSuppliers(Math.max(0, skip - limit), search)}
            >
              Previous
            </button>
            <span style={{ display: 'flex', alignItems: 'center', padding: '0 0.5rem', fontSize: '0.9rem' }}>
              Page {currentPage} of {totalPages}
            </span>
            <button
              className="btn btn-secondary"
              disabled={skip + limit >= total || loading}
              onClick={() => fetchSuppliers(skip + limit, search)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Create Form */}
      <div className="card">
        <div className="card-title">Add a supplier</div>
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
                placeholder="01811000001"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Contact person</label>
              <input
                type="text"
                className="form-input"
                style={{ width: '180px' }}
                value={form.contact_person}
                onChange={(e) => setForm({ ...form, contact_person: e.target.value })}
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
            {saving ? 'Creating...' : 'Create supplier'}
          </button>
        </form>
      </div>

      {/* Supplier Profile Modal */}
      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div
            className="modal-content"
            style={{ maxWidth: '720px' }}
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
                <p>Loading supplier profile...</p>
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
                  <div><strong>Contact person:</strong> {profile?.contact_person || '-'}</div>
                  <div><strong>Address:</strong> {profile?.address || '-'}</div>
                </div>

                {/* Purchase statistics */}
                <div className="grid-cards" style={{ marginBottom: '1.5rem' }}>
                  <div className="card">
                    <div className="card-title">Purchases</div>
                    <div className="card-value" style={{ fontSize: '1.25rem' }}>
                      {profile?.purchase_count ?? 0}
                    </div>
                    <div className="card-subtext">Recorded purchases</div>
                  </div>
                  <div className="card">
                    <div className="card-title">Total Purchased</div>
                    <div className="card-value" style={{ fontSize: '1.25rem' }}>
                      BDT {profile?.total_purchased ?? '-'}
                    </div>
                    <div className="card-subtext">Computed by the server</div>
                  </div>
                </div>

                {/* Purchases */}
                <h3 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                  Purchases
                </h3>
                <div className="table-container">
                  {purchases.length === 0 ? (
                    <div className="state-box">No purchases recorded for this supplier.</div>
                  ) : (
                    <table>
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>Date</th>
                          <th>Invoice</th>
                          <th>Items</th>
                          <th>Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {purchases.map((purchase) => (
                          <tr key={purchase.id}>
                            <td>#{purchase.id}</td>
                            <td>{new Date(purchase.created_at).toLocaleString()}</td>
                            <td>{purchase.invoice_no || '-'}</td>
                            <td>{purchase.item_count ?? 0}</td>
                            <td style={{ fontWeight: 600 }}>BDT {purchase.total_amount}</td>
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
