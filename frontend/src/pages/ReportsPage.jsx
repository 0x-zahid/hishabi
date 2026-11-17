import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function ReportsPage() {
  const [reportType, setReportType] = useState('daily');
  const [dateStr, setDateStr] = useState(new Date().toISOString().split('T')[0]);
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [startDate, setStartDate] = useState(
    new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0]
  );
  const [endDate, setEndDate] = useState(new Date().toISOString().split('T')[0]);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');

  const fetchReport = async () => {
    try {
      setLoading(true);
      setError('');
      let res;
      if (reportType === 'daily') {
        res = await api.getDailyReport(dateStr);
      } else if (reportType === 'monthly') {
        res = await api.getMonthlyReport(year, month);
      } else if (reportType === 'dues') {
        res = await api.getDuesReport();
      } else if (reportType === 'profit') {
        res = await api.getProfitReport(startDate, endDate);
      }
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to generate report.');
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, [reportType]);

  const handleExport = async (format) => {
    try {
      setExporting(true);
      setError('');
      let params = {};
      if (reportType === 'daily') params = { date: dateStr };
      else if (reportType === 'monthly') params = { year, month };
      else if (reportType === 'profit') params = { start: startDate, end: endDate };

      await api.exportReport(reportType, format, params);
    } catch (err) {
      setError(err.message || `Failed to export ${format.toUpperCase()}.`);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 className="page-title">Business Reports</h1>
          <p className="page-subtitle">Analyze sales, customer dues, and profit margins</p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={() => handleExport('pdf')}
            className="btn btn-secondary"
            disabled={loading || exporting || !data}
          >
            {exporting ? 'Exporting...' : 'Download PDF'}
          </button>
          <button
            onClick={() => handleExport('xlsx')}
            className="btn btn-secondary"
            disabled={loading || exporting || !data}
          >
            {exporting ? 'Exporting...' : 'Download Excel'}
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Filter / Parameters Bar */}
      <div className="filter-bar">
        <div className="form-group">
          <label className="form-label">Report Type</label>
          <select
            className="form-select"
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
          >
            <option value="daily">Daily Sales</option>
            <option value="monthly">Monthly Sales</option>
            <option value="dues">Customer Dues</option>
            <option value="profit">Profit Analysis</option>
          </select>
        </div>

        {reportType === 'daily' && (
          <div className="form-group">
            <label className="form-label">Date</label>
            <input
              type="date"
              className="form-input"
              value={dateStr}
              onChange={(e) => setDateStr(e.target.value)}
            />
          </div>
        )}

        {reportType === 'monthly' && (
          <>
            <div className="form-group">
              <label className="form-label">Year</label>
              <input
                type="number"
                className="form-input"
                style={{ width: '100px' }}
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
                min={2000}
                max={2100}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Month</label>
              <select
                className="form-select"
                value={month}
                onChange={(e) => setMonth(Number(e.target.value))}
              >
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>
                    {new Date(2000, m - 1).toLocaleString('default', { month: 'long' })}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        {reportType === 'profit' && (
          <>
            <div className="form-group">
              <label className="form-label">Start Date</label>
              <input
                type="date"
                className="form-input"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">End Date</label>
              <input
                type="date"
                className="form-input"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </>
        )}

        <button onClick={fetchReport} className="btn btn-primary" disabled={loading}>
          {loading ? 'Generating...' : 'Apply Filters'}
        </button>
      </div>

      {loading ? (
        <div className="state-box">
          <div className="spinner"></div>
          <p>Calculating metrics...</p>
        </div>
      ) : !data ? (
        <div className="state-box">Select parameters and click Apply Filters.</div>
      ) : (
        <div>
          {/* DAILY REPORT VIEW */}
          {reportType === 'daily' && (
            <>
              <div className="grid-cards">
                <div className="card">
                  <div className="card-title">Total Sales</div>
                  <div className="card-value">BDT {data.total_sales_amount}</div>
                  <div className="card-subtext">{data.sales_count} sale(s)</div>
                </div>
                <div className="card">
                  <div className="card-title">Gross Profit</div>
                  <div className="card-value" style={{ color: 'var(--success)' }}>
                    BDT {data.total_profit}
                  </div>
                  <div className="card-subtext">Revenue − Cost of Goods</div>
                </div>
                <div className="card">
                  <div className="card-title">Cash vs Credit</div>
                  <div className="card-value" style={{ fontSize: '1.25rem' }}>
                    Cash: BDT {data.cash_sales_amount}
                  </div>
                  <div className="card-subtext">Credit: BDT {data.credit_sales_amount}</div>
                </div>
              </div>
            </>
          )}

          {/* MONTHLY REPORT VIEW */}
          {reportType === 'monthly' && (
            <>
              <div className="grid-cards">
                <div className="card">
                  <div className="card-title">Total Monthly Sales</div>
                  <div className="card-value">BDT {data.total_sales_amount}</div>
                  <div className="card-subtext">{data.sales_count} transaction(s)</div>
                </div>
                <div className="card">
                  <div className="card-title">Monthly Gross Profit</div>
                  <div className="card-value" style={{ color: 'var(--success)' }}>
                    BDT {data.total_profit}
                  </div>
                  <div className="card-subtext">Revenue − Cost</div>
                </div>
              </div>

              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
                Daily Breakdown
              </h2>
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Sales Count</th>
                      <th>Sales Amount</th>
                      <th>Gross Profit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.days?.map((d) => (
                      <tr key={d.date}>
                        <td>{d.date}</td>
                        <td>{d.sales_count}</td>
                        <td style={{ fontWeight: 600 }}>BDT {d.total_sales_amount}</td>
                        <td style={{ color: 'var(--success)', fontWeight: 600 }}>BDT {d.total_profit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* DUES REPORT VIEW */}
          {reportType === 'dues' && (
            <>
              <div className="grid-cards">
                <div className="card">
                  <div className="card-title">Total Outstanding Dues</div>
                  <div className="card-value" style={{ color: 'var(--danger)' }}>
                    BDT {data.total_due_amount}
                  </div>
                  <div className="card-subtext">{data.customer_count} registered customer(s)</div>
                </div>
              </div>

              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
                Customer Dues Breakdown
              </h2>
              <div className="table-container">
                {data.customers?.length === 0 ? (
                  <div className="state-box">No customer records found.</div>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>Customer Name</th>
                        <th>Phone</th>
                        <th>Total Sales</th>
                        <th>Total Paid</th>
                        <th>Current Due</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.customers?.map((c) => (
                        <tr key={c.customer_id}>
                          <td style={{ fontWeight: 600 }}>{c.customer_name}</td>
                          <td>{c.phone || '-'}</td>
                          <td>BDT {c.total_sales}</td>
                          <td>BDT {c.total_paid}</td>
                          <td style={{ fontWeight: 700, color: c.current_due > 0 ? 'var(--danger)' : 'var(--text)' }}>
                            BDT {c.current_due}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}

          {/* PROFIT REPORT VIEW */}
          {reportType === 'profit' && (
            <div className="grid-cards">
              <div className="card">
                <div className="card-title">Total Revenue</div>
                <div className="card-value">BDT {data.total_revenue}</div>
                <div className="card-subtext">Total sales value</div>
              </div>
              <div className="card">
                <div className="card-title">Cost of Goods Sold (COGS)</div>
                <div className="card-value">BDT {data.total_cogs}</div>
                <div className="card-subtext">Sum of unit purchase costs</div>
              </div>
              <div className="card">
                <div className="card-title">Gross Profit</div>
                <div className="card-value" style={{ color: 'var(--success)' }}>
                  BDT {data.gross_profit}
                </div>
                <div className="card-subtext">Revenue − COGS</div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
