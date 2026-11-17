import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, authStorage } from '../api/client';

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please enter both username and password.');
      return;
    }

    try {
      setLoading(true);
      setError('');
      const profile = await api.login(username.trim(), password);

      // Verify Owner role
      const roleName = (profile?.role?.name || '').toLowerCase();
      if (roleName !== 'owner') {
        authStorage.clearAuth();
        setError('Access restricted: Only Owner accounts can access this management portal.');
        return;
      }

      navigate('/dashboard');
    } catch (err) {
      setError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f1f5f9' }}>
      <div className="card" style={{ width: '100%', maxWidth: '380px', padding: '2rem' }}>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--primary)', marginBottom: '0.25rem' }}>Hishabi</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Owner Management Portal</p>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">Username</label>
            <input
              type="text"
              className="form-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. owner"
              disabled={loading}
              autoFocus
            />
          </div>

          <div className="form-group" style={{ marginBottom: '1.5rem' }}>
            <label className="form-label">Password</label>
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              disabled={loading}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%', justifyContent: 'center' }}
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign In as Owner'}
          </button>
        </form>

        <div style={{ marginTop: '1.5rem', textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Demo owner: <code>owner</code> / <code>owner_pass123</code>
        </div>
      </div>
    </div>
  );
}
