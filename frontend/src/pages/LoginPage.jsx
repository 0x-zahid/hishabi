import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, authStorage } from '../api/client';

export default function LoginPage() {
  const navigate = useNavigate();

  // Mode: 'signin' | 'signup'
  const [mode, setMode] = useState('signin');

  // Sign In Form State
  const [loginUsername, setLoginUsername] = useState('owner');
  const [loginPassword, setLoginPassword] = useState('owner_pass123');

  // Sign Up Form State
  const [fullName, setFullName] = useState('');
  const [regUsername, setRegUsername] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // Status State
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // 1-Click Demo Fill Helpers
  const fillDemoOwner = () => {
    setLoginUsername('owner');
    setLoginPassword('owner_pass123');
    setError('');
  };

  const fillDemoStaff = () => {
    setLoginUsername('staff');
    setLoginPassword('staff_pass123');
    setError('');
  };

  // Sign In Submission
  const handleLogin = async (e) => {
    e.preventDefault();
    if (!loginUsername.trim() || !loginPassword) {
      setError('Please provide both username and password.');
      return;
    }

    try {
      setLoading(true);
      setError('');
      setSuccess('');

      const profile = await api.login(loginUsername.trim(), loginPassword);

      // Verify Owner permission
      const roleName = (profile?.role?.name || profile?.role_name || '').toLowerCase();
      const isOwner = roleName === 'owner' || profile?.role_id === 1 || profile?.username === 'owner';

      if (!isOwner) {
        authStorage.clearAuth();
        setError(
          `User '${profile?.username}' has role '${roleName || 'staff'}'. Only Owner accounts have access to this portal. Please log in with Owner credentials.`
        );
        return;
      }

      navigate('/dashboard');
    } catch (err) {
      setError(err.message || 'Login failed. Please check your credentials or backend server status.');
    } finally {
      setLoading(false);
    }
  };

  // Sign Up Submission
  const handleRegister = async (e) => {
    e.preventDefault();
    if (!fullName.trim() || !regUsername.trim() || !regPassword) {
      setError('Full Name, Username, and Password are required.');
      return;
    }

    if (regPassword.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    if (regPassword !== confirmPassword) {
      setError('Passwords do not match. Please re-enter identical passwords.');
      return;
    }

    try {
      setLoading(true);
      setError('');
      setSuccess('');

      // 1. Register user
      await api.register({
        full_name: fullName.trim(),
        username: regUsername.trim(),
        email: regEmail.trim() || null,
        password: regPassword,
      });

      setSuccess('Account created successfully! Logging you into the Owner Dashboard...');

      // 2. Automatically log in with the new credentials
      const profile = await api.login(regUsername.trim(), regPassword);
      navigate('/dashboard');
    } catch (err) {
      setError(err.message || 'Registration failed. Please check your input.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-card">
        {/* Branding Header */}
        <div className="auth-header">
          <h1 className="auth-title">Hishabi</h1>
          <p className="auth-subtitle">Owner &amp; Inventory Management Portal</p>
        </div>

        {/* Tab Toggle: Sign In vs Sign Up */}
        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab-btn ${mode === 'signin' ? 'active' : ''}`}
            onClick={() => {
              setMode('signin');
              setError('');
              setSuccess('');
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`auth-tab-btn ${mode === 'signup' ? 'active' : ''}`}
            onClick={() => {
              setMode('signup');
              setError('');
              setSuccess('');
            }}
          >
            Sign Up / Register
          </button>
        </div>

        {/* Feedback Banners */}
        {error && <div className="error-banner">{error}</div>}
        {success && <div className="success-banner">{success}</div>}

        {/* MODE: SIGN IN */}
        {mode === 'signin' && (
          <form onSubmit={handleLogin}>
            <div className="form-group" style={{ marginBottom: '1.25rem' }}>
              <label className="form-label" style={{ fontSize: '0.88rem' }}>
                Username
              </label>
              <input
                type="text"
                className="form-input"
                style={{ fontSize: '1rem', padding: '0.65rem 0.85rem' }}
                value={loginUsername}
                onChange={(e) => setLoginUsername(e.target.value)}
                placeholder="Enter username (e.g. owner)"
                disabled={loading}
                autoFocus
              />
            </div>

            <div className="form-group" style={{ marginBottom: '1.75rem' }}>
              <label className="form-label" style={{ fontSize: '0.88rem' }}>
                Password
              </label>
              <input
                type="password"
                className="form-input"
                style={{ fontSize: '1rem', padding: '0.65rem 0.85rem' }}
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="Enter password (e.g. owner_pass123)"
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{
                width: '100%',
                justifyContent: 'center',
                padding: '0.75rem 1rem',
                fontSize: '1rem',
                fontWeight: 600,
                borderRadius: '8px',
              }}
              disabled={loading}
            >
              {loading ? 'Authenticating...' : 'Sign In to Dashboard'}
            </button>

            {/* Quick 1-Click Credentials Bar */}
            <div className="auth-demo-box">
              <div className="auth-demo-title">
                <span>⚡ 1-Click Demo Accounts</span>
                <span style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--primary)' }}>
                  Click to prefill
                </span>
              </div>
              <div className="auth-demo-actions">
                <button
                  type="button"
                  className="btn-demo-pill"
                  onClick={fillDemoOwner}
                  disabled={loading}
                  title="Prefill Owner credentials"
                >
                  🔑 Fill Owner (owner / owner_pass123)
                </button>
                <button
                  type="button"
                  className="btn-demo-pill"
                  style={{ background: '#f8fafc', borderColor: '#cbd5e1', color: '#475569' }}
                  onClick={fillDemoStaff}
                  disabled={loading}
                  title="Prefill Staff credentials"
                >
                  👤 Fill Staff (staff / staff_pass123)
                </button>
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                <strong>Role Note:</strong> Owner has full access to the <strong>Dashboard</strong>,{' '}
                <strong>Reports</strong>, and <strong>Audit Log</strong> pages.
              </div>
            </div>
          </form>
        )}

        {/* MODE: SIGN UP */}
        {mode === 'signup' && (
          <form onSubmit={handleRegister}>
            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label" style={{ fontSize: '0.88rem' }}>
                Full Name <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <input
                type="text"
                className="form-input"
                style={{ fontSize: '0.95rem', padding: '0.6rem 0.85rem' }}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="e.g. Md Abdullah Azaz"
                disabled={loading}
                autoFocus
              />
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label" style={{ fontSize: '0.88rem' }}>
                Username <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <input
                type="text"
                className="form-input"
                style={{ fontSize: '0.95rem', padding: '0.6rem 0.85rem' }}
                value={regUsername}
                onChange={(e) => setRegUsername(e.target.value)}
                placeholder="e.g. azaz_owner"
                disabled={loading}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label" style={{ fontSize: '0.88rem' }}>
                Email Address <span style={{ color: 'var(--text-muted)' }}>(Optional)</span>
              </label>
              <input
                type="email"
                className="form-input"
                style={{ fontSize: '0.95rem', padding: '0.6rem 0.85rem' }}
                value={regEmail}
                onChange={(e) => setRegEmail(e.target.value)}
                placeholder="e.g. azaz@example.com"
                disabled={loading}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label" style={{ fontSize: '0.88rem' }}>
                Password <span style={{ color: 'var(--danger)' }}>* (Min 8 chars)</span>
              </label>
              <input
                type="password"
                className="form-input"
                style={{ fontSize: '0.95rem', padding: '0.6rem 0.85rem' }}
                value={regPassword}
                onChange={(e) => setRegPassword(e.target.value)}
                placeholder="At least 8 characters"
                disabled={loading}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '1.5rem' }}>
              <label className="form-label" style={{ fontSize: '0.88rem' }}>
                Confirm Password <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <input
                type="password"
                className="form-input"
                style={{ fontSize: '0.95rem', padding: '0.6rem 0.85rem' }}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-type password"
                disabled={loading}
              />
            </div>

            <div
              style={{
                background: '#eff6ff',
                border: '1px solid #bfdbfe',
                borderRadius: '8px',
                padding: '0.75rem',
                fontSize: '0.82rem',
                color: '#1e40af',
                marginBottom: '1.25rem',
              }}
            >
              ✨ <strong>Owner Registration:</strong> Registered accounts are automatically assigned Owner permissions and granted immediate access to the Dashboard, Reports, and Audit Log.
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{
                width: '100%',
                justifyContent: 'center',
                padding: '0.75rem 1rem',
                fontSize: '1rem',
                fontWeight: 600,
                borderRadius: '8px',
              }}
              disabled={loading}
            >
              {loading ? 'Creating Account...' : 'Create Owner Account & Enter'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
