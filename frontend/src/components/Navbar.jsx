import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { api, authStorage } from '../api/client';

export default function Navbar() {
  const navigate = useNavigate();
  const user = authStorage.getUser();

  const handleLogout = () => {
    api.logout();
    navigate('/login');
  };

  return (
    <nav className="navbar">
      <NavLink to="/dashboard" className="navbar-brand">
        Hishabi
      </NavLink>

      <div className="navbar-links">
        <NavLink to="/dashboard" className={({ isActive }) => (isActive ? 'active' : '')}>
          Dashboard
        </NavLink>
        <NavLink to="/reports" className={({ isActive }) => (isActive ? 'active' : '')}>
          Reports
        </NavLink>
        <NavLink to="/audit" className={({ isActive }) => (isActive ? 'active' : '')}>
          Audit Log
        </NavLink>
        <NavLink to="/ai" className={({ isActive }) => (isActive ? 'active' : '')}>
          AI Entry
        </NavLink>
        <NavLink to="/products" className={({ isActive }) => (isActive ? 'active' : '')}>
          Products
        </NavLink>
        <NavLink to="/customers" className={({ isActive }) => (isActive ? 'active' : '')}>
          Customers
        </NavLink>
        <NavLink to="/sales" className={({ isActive }) => (isActive ? 'active' : '')}>
          Sales
        </NavLink>
        <NavLink to="/suppliers" className={({ isActive }) => (isActive ? 'active' : '')}>
          Suppliers
        </NavLink>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginLeft: '1rem' }}>
          <span className="user-badge">{user?.role?.name || user?.username || 'Owner'}</span>
          <button onClick={handleLogout} className="btn-logout" title="Log out">
            Log out
          </button>
        </div>
      </div>
    </nav>
  );
}
