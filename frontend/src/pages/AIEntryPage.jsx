import React, { useEffect, useMemo, useState } from 'react';
import * as aiApi from '../api/ai';

/**
 * AI Bangla entry page.
 *
 * Owner: Zahid. Module 3.
 *
 * The user types one Bangla sentence, the server turns it into a proposal,
 * and the user edits that proposal before confirming it. Nothing is saved
 * until the user presses Confirm.
 *
 * When the AI service is unavailable the manual entry form is revealed
 * instead, and it records the same sale through the ordinary sale endpoint,
 * so it works with no AI key configured at all.
 */

const EXAMPLE = 'রহিম ভাই ৫ কেজি চাল আর ১ লিটার তেল নিলেন, ৮০০ টাকা দিয়েছেন';

// --- Exact money arithmetic ------------------------------------------------
// Quantity has three decimal places and money has two, so both are kept as
// scaled integers and the total is computed without floating point error.
const QTY_SCALE = 1000;
const PRICE_SCALE = 100;

function toScaled(value, scale) {
  const num = Number(value);
  if (!Number.isFinite(num)) return 0;
  return Math.round(num * scale);
}

function centsOf(quantity, unitPrice) {
  // thousandths * cents -> hundred-thousandths of a taka -> cents
  return (toScaled(quantity, QTY_SCALE) * toScaled(unitPrice, PRICE_SCALE)) / 1000;
}

function totalCents(items) {
  // quantity is in thousandths and the price in cents, so the product is in
  // hundred-thousandths of a taka and is scaled back down to cents here.
  const micros = items.reduce(
    (sum, item) => sum + toScaled(item.quantity, QTY_SCALE) * toScaled(item.unit_price, PRICE_SCALE),
    0
  );
  return Math.round(micros / 1000);
}

function formatCents(cents) {
  return (cents / 100).toFixed(2);
}

function emptyItem() {
  return {
    product: { id: null, name: null, matched: false },
    quantity: '1.000',
    unit_price: '0.00',
    flags: [],
    suggestions: [],
  };
}

function emptyManualItem() {
  return { product_id: '', quantity: '1.000', unit_price: '0.00' };
}

/**
 * Build the editable form state out of the proposal the server sent.
 * Every field stays a string so the user can type into it.
 */
function proposalToForm(proposal) {
  return {
    customer: {
      id: proposal.customer?.id ?? null,
      name: proposal.customer?.name ?? '',
      matched: proposal.customer?.matched ?? false,
      warning: proposal.customer?.warning ?? null,
    },
    items: (proposal.items || []).map((item) => ({
      product: {
        id: item.product?.id ?? null,
        name: item.product?.name ?? '',
        matched: item.product?.matched ?? false,
      },
      quantity: String(item.quantity ?? '0'),
      unit_price: String(item.unit_price ?? '0'),
      flags: item.flags || [],
      suggestions: [],
    })),
    payment_type: proposal.payment_type || 'cash',
    paid_amount: String(proposal.paid_amount ?? '0'),
    flags: proposal.flags || [],
  };
}

/**
 * Check the edited form. The server checks it again, but the Confirm button
 * is disabled until the obvious problems are fixed.
 */
function validateForm(form) {
  const errors = [];
  const total = totalCents(form.items);

  if (!form.items.length) {
    errors.push('A sale must have at least one item.');
  }

  form.items.forEach((item, index) => {
    if (!item.product.id) {
      errors.push(`Item ${index + 1}: choose a product.`);
    }
    if (!(Number(item.quantity) > 0)) {
      errors.push(`Item ${index + 1}: the quantity must be greater than zero.`);
    }
    if (Number(item.unit_price) < 0) {
      errors.push(`Item ${index + 1}: the unit price cannot be negative.`);
    }
  });

  if (form.payment_type === 'credit' && !form.customer.id) {
    errors.push('A credit sale must name the customer.');
  }

  const paid = Math.round(Number(form.paid_amount || 0) * PRICE_SCALE);
  if (form.payment_type === 'cash' && paid !== total) {
    errors.push(`A cash sale must be paid in full: ${formatCents(total)}.`);
  }
  if (form.payment_type === 'credit' && (paid < 0 || paid > total)) {
    errors.push('The paid amount must be between zero and the total.');
  }

  return errors;
}

export default function AIEntryPage() {
  const [text, setText] = useState('');
  const [usage, setUsage] = useState(null);
  const [requestId, setRequestId] = useState(null);
  const [form, setForm] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [parsing, setParsing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [aiUnavailable, setAiUnavailable] = useState(false);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);

  const [manual, setManual] = useState({
    customer_id: '',
    payment_type: 'cash',
    paid_amount: '',
    items: [emptyManualItem()],
  });
  const [manualSaving, setManualSaving] = useState(false);

  const loadUsage = async () => {
    try {
      const data = await aiApi.getTodayUsage();
      setUsage(data);
    } catch {
      // The usage line is not important enough to break the page over.
    }
  };

  const loadLookups = async () => {
    try {
      const customerData = await aiApi.getCustomers();
      setCustomers(customerData?.items || []);
    } catch {
      setCustomers([]);
    }
    try {
      const productData = await aiApi.getProducts();
      setProducts(productData?.items || []);
    } catch {
      setProducts([]);
    }
  };

  useEffect(() => {
    loadUsage();
    loadLookups();
  }, []);

  const total = useMemo(
    () => (form ? totalCents(form.items) : 0),
    [form]
  );

  const formErrors = useMemo(() => (form ? validateForm(form) : []), [form]);

  const handleParse = async () => {
    if (!text.trim()) {
      setError('Type a Bangla sentence first.');
      return;
    }
    setParsing(true);
    setError('');
    setSuccess('');
    try {
      const data = await aiApi.parseSale(text);
      setRequestId(data.request_id);
      setForm(proposalToForm(data.proposal));
      setWarnings(data.warnings || []);
      setAiUnavailable(false);
      setUsage({
        used: (usage?.used ?? 0) + 1,
        limit: data.remaining_requests_today + (usage?.used ?? 0) + 1,
        remaining: data.remaining_requests_today,
      });
    } catch (err) {
      if (err.status === 503) {
        // The AI service is down: offer the manual form instead.
        setAiUnavailable(true);
        setError(
          err.message || 'The AI service is unavailable. Please use the manual entry form.'
        );
        setForm(null);
        setRequestId(null);
      } else {
        setError(err.message || 'The sentence could not be parsed.');
      }
    } finally {
      setParsing(false);
    }
  };

  const handleCancel = async () => {
    setError('');
    setSuccess('');
    if (requestId) {
      try {
        await aiApi.rejectRequest(requestId);
      } catch {
        // The proposal is dropped from the screen either way.
      }
    }
    setForm(null);
    setRequestId(null);
    setWarnings([]);
  };

  const handleConfirm = async () => {
    if (!form || formErrors.length) return;
    setConfirming(true);
    setError('');
    setSuccess('');
    try {
      const sale = await aiApi.confirmRequest(requestId, {
        customer: form.customer.id ? { id: form.customer.id, name: form.customer.name } : null,
        items: form.items.map((item) => ({
          product: { id: item.product.id, name: item.product.name },
          quantity: item.quantity,
          unit_price: item.unit_price,
        })),
        payment_type: form.payment_type,
        paid_amount: form.paid_amount,
        total_amount: formatCents(total),
      });
      setSuccess(`Sale #${sale.id} was recorded. Total BDT ${sale.total_amount}.`);
      setForm(null);
      setRequestId(null);
      setWarnings([]);
      setText('');
      loadUsage();
    } catch (err) {
      setError(err.message || 'The sale could not be recorded.');
    } finally {
      setConfirming(false);
    }
  };

  const updateCustomer = (id, name) => {
    setForm((prev) => ({
      ...prev,
      customer: { ...prev.customer, id: id ? Number(id) : null, name: name || '', matched: !!id },
    }));
  };

  const updateItem = (index, patch) => {
    setForm((prev) => {
      const items = prev.items.map((item, i) => (i === index ? { ...item, ...patch } : item));
      return { ...prev, items };
    });
  };

  const updateItemProduct = (index, id, name) => {
    updateItem(index, {
      product: { id: id ? Number(id) : null, name: name || '', matched: !!id },
      flags: [],
    });
  };

  /**
   * Change the payment type and keep the paid amount sensible: a cash sale is
   * paid in full, a credit sale starts at zero.
   */
  const updateFormPayment = (paymentType) => {
    setForm((prev) => {
      const newTotal = totalCents(prev.items);
      const paid = paymentType === 'cash' ? formatCents(newTotal) : '0.00';
      return { ...prev, payment_type: paymentType, paid_amount: paid };
    });
  };

  const removeItem = (index) => {
    setForm((prev) => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== index),
    }));
  };

  const addItem = () => {
    setForm((prev) => ({ ...prev, items: [...prev.items, emptyItem()] }));
  };

  // --- The manual form ----------------------------------------------------

  const manualTotal = useMemo(() => totalCents(manual.items), [manual.items]);

  const updateManual = (patch) => setManual((prev) => ({ ...prev, ...patch }));

  const updateManualItem = (index, patch) => {
    setManual((prev) => ({
      ...prev,
      items: prev.items.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    }));
  };

  const handleManualSubmit = async (event) => {
    event.preventDefault();
    setManualSaving(true);
    setError('');
    setSuccess('');
    try {
      const product = products.find((p) => String(p.id) === String(manual.items[0]?.product_id));
      const sale = await aiApi.createManualSale({
        customer_id: manual.customer_id ? Number(manual.customer_id) : null,
        payment_type: manual.payment_type,
        items: manual.items
          .filter((item) => item.product_id)
          .map((item) => ({
            product_id: Number(item.product_id),
            quantity: item.quantity,
            unit_price:
              item.unit_price === '' && product ? String(product.sale_price) : item.unit_price,
          })),
        paid_amount:
          manual.paid_amount === ''
            ? manual.payment_type === 'cash'
              ? formatCents(manualTotal)
              : '0.00'
            : manual.paid_amount,
      });
      setSuccess(`Sale #${sale.id} was recorded. Total BDT ${sale.total_amount}.`);
      setManual({
        customer_id: '',
        payment_type: 'cash',
        paid_amount: '',
        items: [emptyManualItem()],
      });
      loadUsage();
    } catch (err) {
      setError(err.message || 'The sale could not be recorded.');
    } finally {
      setManualSaving(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">AI Bangla Entry</h1>
        <p className="page-subtitle">
          Type a Bangla sentence about a sale. The shop details are extracted for you to check
          before anything is saved.
        </p>
      </div>

      {usage && (
        <div className="success-banner">
          {usage.remaining} of {usage.limit} AI requests remain today ({usage.used} used).
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}
      {success && <div className="success-banner">{success}</div>}

      {/* --- The Bangla sentence --- */}
      {!aiUnavailable && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-title">Sale description in Bangla</div>
          <textarea
            className="form-input"
            style={{ width: '100%', minHeight: '120px', marginBottom: '0.75rem' }}
            placeholder={EXAMPLE}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={parsing}
          />
          <button onClick={handleParse} className="btn btn-primary" disabled={parsing || !text.trim()}>
            {parsing ? 'Reading the sentence...' : 'Parse sentence'}
          </button>
        </div>
      )}

      {aiUnavailable && (
        <div className="error-banner">
          The AI service is unavailable. Use the manual entry form below instead.
        </div>
      )}

      {/* --- The proposal --- */}
      {form && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-title">Review the sale</div>
          <p className="card-subtext" style={{ marginBottom: '1rem' }}>
            Nothing is saved until you press Confirm. Every field can be changed.
          </p>

          {warnings.length > 0 && (
            <div className="error-banner">
              {warnings.map((warning, index) => (
                <div key={`${warning.field}-${index}`}>
                  {warning.message}
                  {warning.suggestions?.length > 0 && (
                    <span>
                      {' '}
                      Did you mean:{' '}
                      {warning.suggestions.map((s) => s.name).join(', ')}?
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Customer */}
          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">Customer</label>
            {form.customer.matched ? (
              <div style={{ fontSize: '0.9rem', marginBottom: '0.35rem' }}>
                {form.customer.name}
                {form.customer.warning && (
                  <span style={{ color: 'var(--warning)', marginLeft: '0.5rem' }}>
                    ({form.customer.warning})
                  </span>
                )}
              </div>
            ) : (
              form.customer.name && (
                <div style={{ fontSize: '0.9rem', color: 'var(--danger)', marginBottom: '0.35rem' }}>
                  Not matched: &ldquo;{form.customer.name}&rdquo;
                </div>
              )
            )}
            <select
              className="form-select"
              value={form.customer.id ?? ''}
              onChange={(e) => {
                const chosen = customers.find((c) => String(c.id) === e.target.value);
                updateCustomer(e.target.value, chosen?.name);
              }}
            >
              <option value="">-- no customer (walk-in) --</option>
              {customers.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name}
                </option>
              ))}
            </select>
          </div>

          {/* Items */}
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Quantity</th>
                  <th>Unit price</th>
                  <th>Line total</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {form.items.map((item, index) => {
                  const lineTotal = Math.round(centsOf(item.quantity, item.unit_price));
                  const hasProblem =
                    item.flags.length > 0 ||
                    !item.product.id ||
                    !(Number(item.quantity) > 0) ||
                    Number(item.unit_price) < 0;
                  return (
                    <tr key={index}>
                      <td style={{ minWidth: '220px' }}>
                        {!item.product.matched && item.product.name && (
                          <div style={{ color: 'var(--danger)', fontSize: '0.8rem' }}>
                            Not matched: &ldquo;{item.product.name}&rdquo;
                          </div>
                        )}
                        <select
                          className="form-select"
                          style={{
                            borderColor: hasProblem ? 'var(--danger)' : undefined,
                          }}
                          value={item.product.id ?? ''}
                          onChange={(e) => {
                            const chosen = products.find((p) => String(p.id) === e.target.value);
                            updateItemProduct(
                              index,
                              e.target.value,
                              chosen?.name ?? item.product.name
                            );
                          }}
                        >
                          <option value="">-- choose a product --</option>
                          {products.map((product) => (
                            <option key={product.id} value={product.id}>
                              {product.name}
                            </option>
                          ))}
                        </select>
                        {item.flags.length > 0 && (
                          <div style={{ color: 'var(--danger)', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                            {item.flags.join(', ')}
                          </div>
                        )}
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.001"
                          className="form-input"
                          style={{
                            width: '100px',
                            borderColor:
                              Number(item.quantity) > 0 ? undefined : 'var(--danger)',
                          }}
                          value={item.quantity}
                          onChange={(e) => updateItem(index, { quantity: e.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.01"
                          className="form-input"
                          style={{
                            width: '110px',
                            borderColor:
                              Number(item.unit_price) < 0 ? 'var(--danger)' : undefined,
                          }}
                          value={item.unit_price}
                          onChange={(e) => updateItem(index, { unit_price: e.target.value })}
                        />
                      </td>
                      <td>BDT {formatCents(lineTotal)}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() => removeItem(index)}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <button type="button" className="btn btn-secondary" onClick={addItem}>
            Add an item
          </button>

          {/* Payment and total */}
          <div
            style={{
              display: 'flex',
              gap: '1rem',
              flexWrap: 'wrap',
              alignItems: 'flex-end',
              marginTop: '1rem',
            }}
          >
            <div className="form-group">
              <label className="form-label">Payment type</label>
              <select
                className="form-select"
                value={form.payment_type}
                onChange={(e) => updateFormPayment(e.target.value)}
              >
                <option value="cash">Cash</option>
                <option value="credit">Credit</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Paid amount</label>
              <input
                type="number"
                step="0.01"
                className="form-input"
                style={{ width: '140px' }}
                value={form.paid_amount}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, paid_amount: e.target.value }))
                }
              />
            </div>
            <div className="form-group">
              <label className="form-label">Total (computed by the server)</label>
              <div className="card-value">BDT {formatCents(total)}</div>
            </div>
          </div>

          {formErrors.length > 0 && (
            <div className="error-banner" style={{ marginTop: '1rem' }}>
              {formErrors.map((message, index) => (
                <div key={index}>{message}</div>
              ))}
            </div>
          )}

          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
            <button
              className="btn btn-primary"
              onClick={handleConfirm}
              disabled={confirming || formErrors.length > 0}
            >
              {confirming ? 'Recording...' : 'Confirm and record'}
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleCancel}
              disabled={confirming}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* --- The manual form --- */}
      {(aiUnavailable || !form) && (
        <div className="card">
          <div className="card-title">Manual entry</div>
          <p className="card-subtext" style={{ marginBottom: '1rem' }}>
            {aiUnavailable
              ? 'The AI service is down, so record the sale by hand.'
              : 'You can also record a sale by hand.'}
          </p>

          <form onSubmit={handleManualSubmit}>
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
                <label className="form-label">Customer</label>
                <select
                  className="form-select"
                  value={manual.customer_id}
                  onChange={(e) => updateManual({ customer_id: e.target.value })}
                >
                  <option value="">-- no customer (walk-in) --</option>
                  {customers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Payment type</label>
                <select
                  className="form-select"
                  value={manual.payment_type}
                  onChange={(e) => updateManual({ payment_type: e.target.value })}
                >
                  <option value="cash">Cash</option>
                  <option value="credit">Credit</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Paid amount</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  style={{ width: '140px' }}
                  value={manual.paid_amount}
                  onChange={(e) => updateManual({ paid_amount: e.target.value })}
                  placeholder={formatCents(manualTotal)}
                />
              </div>
            </div>

            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Quantity</th>
                    <th>Unit price</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {manual.items.map((item, index) => (
                    <tr key={index}>
                      <td style={{ minWidth: '220px' }}>
                        <select
                          className="form-select"
                          value={item.product_id}
                          onChange={(e) => {
                            const chosen = products.find(
                              (p) => String(p.id) === e.target.value
                            );
                            updateManualItem(index, {
                              product_id: e.target.value,
                              unit_price:
                                item.unit_price === '0.00' && chosen
                                  ? String(chosen.sale_price)
                                  : item.unit_price,
                            });
                          }}
                        >
                          <option value="">-- choose a product --</option>
                          {products.map((product) => (
                            <option key={product.id} value={product.id}>
                              {product.name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.001"
                          className="form-input"
                          style={{ width: '100px' }}
                          value={item.quantity}
                          onChange={(e) =>
                            updateManualItem(index, { quantity: e.target.value })
                          }
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.01"
                          className="form-input"
                          style={{ width: '110px' }}
                          value={item.unit_price}
                          onChange={(e) =>
                            updateManualItem(index, { unit_price: e.target.value })
                          }
                        />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() =>
                            setManual((prev) => ({
                              ...prev,
                              items: prev.items.filter((_, i) => i !== index),
                            }))
                          }
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem', alignItems: 'center' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() =>
                  setManual((prev) => ({
                    ...prev,
                    items: [...prev.items, emptyManualItem()],
                  }))
                }
              >
                Add an item
              </button>
              <button type="submit" className="btn btn-primary" disabled={manualSaving}>
                {manualSaving ? 'Recording...' : 'Record sale'}
              </button>
              <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                Total BDT {formatCents(manualTotal)}
              </span>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
