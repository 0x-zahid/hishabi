import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Navbar from './components/Navbar';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ReportsPage from './pages/ReportsPage';
import AuditLogPage from './pages/AuditLogPage';
import { authStorage } from './api/client';
import './App.css';

/**
 * Protected Route Guard: Only lets authenticated Owners through
 */
function ProtectedRoute({ children }) {
  const token = authStorage.getToken();
  const user = authStorage.getUser();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  const roleName = (user?.role?.name || '').toLowerCase();
  if (roleName !== 'owner') {
    return (
      <div className="state-box" style={{ marginTop: '4rem' }}>
        <h2 style={{ color: 'var(--danger)', marginBottom: '0.5rem' }}>Access Restricted (403 Forbidden)</h2>
        <p>This management portal requires Owner permissions.</p>
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

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
