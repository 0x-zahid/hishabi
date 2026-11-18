import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Navbar from './components/Navbar';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ReportsPage from './pages/ReportsPage';
import AuditLogPage from './pages/AuditLogPage';
import AIEntryPage from './pages/AIEntryPage';
import { authStorage } from './api/client';
import './App.css';

/**
 * Protected Route Guard.
 *
 * By default only Owners get through, which is what the dashboard, reports
 * and audit log have always required. Pass `allow` to open a route to other
 * roles: the AI entry page is also open to staff, because staff work the
 * counter and record sales.
 */
function ProtectedRoute({ children, allow = ['owner'] }) {
  const token = authStorage.getToken();
  const user = authStorage.getUser();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  const roleName = (user?.role?.name || user?.role_name || '').toLowerCase();
  const isOwner = roleName === 'owner' || user?.role_id === 1 || user?.username === 'owner';
  const allowed = allow.map((name) => name.toLowerCase());
  const hasAccess = isOwner || allowed.includes(roleName);

  if (!hasAccess) {
    return (
      <div className="state-box" style={{ marginTop: '4rem' }}>
        <h2 style={{ color: 'var(--danger)', marginBottom: '0.5rem' }}>Access Restricted (403 Forbidden)</h2>
        <p>
          This page requires {allowed.map((r) => r[0].toUpperCase() + r.slice(1)).join(' or ')}{' '}
          permissions.
        </p>
        <button
          onClick={() => {
            authStorage.clearAuth();
            window.location.href = '/login';
          }}
          className="btn btn-primary"
          style={{ marginTop: '1rem' }}
        >
          Return to Login
        </button>
      </div>
    );
  }

  return (
    <div className="app-container">
      <Navbar />
      <main className="page-content">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/reports"
          element={
            <ProtectedRoute>
              <ReportsPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/audit"
          element={
            <ProtectedRoute>
              <AuditLogPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/ai"
          element={
            <ProtectedRoute allow={['owner', 'staff']}>
              <AIEntryPage />
            </ProtectedRoute>
          }
        />

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
