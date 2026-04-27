// ═══════════════════════════════════════════════════════════
// MANAGER
// ═══════════════════════════════════════════════════════════
const MANAGER_FAILED_POLL_MS = 5000;

function startManagerFailedBookingMonitor() {
  stopManagerFailedBookingMonitor();
  _pollManagerFailedBookings();
  state._managerFailedBookingTimer = setInterval(
    _pollManagerFailedBookings,
    MANAGER_FAILED_POLL_MS,
  );
}

function stopManagerFailedBookingMonitor() {
  if (state._managerFailedBookingTimer) {
    clearInterval(state._managerFailedBookingTimer);
    state._managerFailedBookingTimer = null;
  }
  state._managerLastPendingFailedCount = -1;

  const tabBtn = document.getElementById('manager-tab-failed');
  if (tabBtn) tabBtn.textContent = 'Đặt bàn thất bại';
  const alertsEl = document.getElementById('manager-live-alerts');
  if (alertsEl) alertsEl.innerHTML = '';
}

async function _pollManagerFailedBookings() {
  if (!state.user || state.user.role !== 'manager') return;
  try {
    const pending = await api(
      'GET',
      '/manager/failed-bookings?contact_status=' + encodeURIComponent('chưa liên hệ'),
    );
    _renderManagerFailedBookingNotice(pending || []);
  } catch {
    // Không spam lỗi UI khi poll fail tạm thời.
  }
}

function _renderManagerFailedBookingNotice(pendingItems) {
  const count = pendingItems.length;
  const tabBtn = document.getElementById('manager-tab-failed');
  if (tabBtn) {
    tabBtn.textContent = count > 0
      ? `Đặt bàn thất bại (${count})`
      : 'Đặt bàn thất bại';
  }

  const alertsEl = document.getElementById('manager-live-alerts');
  if (!alertsEl) return;

  if (count <= 0) {
    alertsEl.innerHTML = '';
    state._managerLastPendingFailedCount = 0;
    return;
  }

  const newest = pendingItems[0];
  const requestedAt = newest?.requested_time
    ? new Date(newest.requested_time).toLocaleString('vi-VN')
    : 'không rõ thời gian';
  const isNewSpike = state._managerLastPendingFailedCount >= 0
    && count > state._managerLastPendingFailedCount;

  alertsEl.innerHTML = `
    <div class="manager-live-alert-item">
      <div class="manager-live-alert-title">
        ⚠️ Có ${count} yêu cầu đặt bàn thất bại chưa liên hệ
      </div>
      <div class="manager-live-alert-body">
        Mới nhất: ${newest?.customer_name || 'khách chưa xác định'} · ${requestedAt}
      </div>
      <div class="manager-live-alert-actions">
        <button onclick="openManagerFailedBookingsTab()">Xem danh sách và liên hệ</button>
        ${isNewSpike ? '<span class="manager-live-alert-new">Có yêu cầu mới</span>' : ''}
      </div>
    </div>
  `;

  state._managerLastPendingFailedCount = count;
}

function openManagerFailedBookingsTab() {
  const btn = document.getElementById('manager-tab-failed');
  if (!btn) return;
  switchTab('tab-failed', btn);
  loadFailedBookings();
}

function _toLocalInputValue(isoDateString) {
  if (!isoDateString) return '';
  const d = new Date(isoDateString);
  const offset = d.getTimezoneOffset() * 60000;
  return new Date(d - offset).toISOString().slice(0, 16);
}

async function loadAllOrders() {
  const listEl = document.getElementById('all-orders-list');
  const status = document.getElementById('filter-status').value;
  listEl.innerHTML = '<p>Đang tải...</p>';
  try {
    const path = status ? `/manager/orders?status=${encodeURIComponent(status)}` : '/manager/orders';
    const orders = await api('GET', path);
    listEl.innerHTML = '';
    if (!orders.length) { listEl.innerHTML = '<p>Không có đơn nào.</p>'; return; }
    const table = document.createElement('table');
    table.innerHTML = `
      <thead>
        <tr><th>Mã đơn</th><th>Giờ đặt</th><th>Trạng thái</th><th>Khách</th><th>NV</th><th>Bàn</th><th>Tổng</th><th>Cọc</th><th>Thao tác</th></tr>
      </thead>
      <tbody>
        ${orders.map(o => {
      const canCancel = ['đang xử lý', 'chờ thanh toán', 'hoàn tất'].includes(o.status);
      const canReschedule = o.status === 'đang xử lý';
      return `
          <tr>
            <td>${o.order_id}</td>
            <td style="white-space:nowrap">${new Date(o.reservation_time).toLocaleString('vi-VN')}</td>
            <td>${badgeHtml(o.status)}</td>
            <td>${o.customer_name}</td>
            <td>${o.staff_name}</td>
            <td>${o.table_id}</td>
            <td>${o.total ? o.total.toLocaleString('vi-VN') + 'đ' : '—'}</td>
            <td>${o.deposit_paid > 0 ? o.deposit_paid.toLocaleString('vi-VN') + 'đ' : '—'}</td>
            <td>
              ${canReschedule
          ? `<button onclick="managerRescheduleOrder('${o.order_id}', '${o.reservation_time}')" 
                     style="padding:4px 10px;font-size:12px;margin-right:6px">Đổi giờ</button>`
          : ''}
              ${canCancel
          ? `<button onclick="managerCancelOrder('${o.order_id}')" class="btn-danger"
                     style="padding:4px 10px;font-size:12px">Hủy đơn</button>`
          : '—'}
            </td>
          </tr>`;
    }).join('')}
      </tbody>
    `;
    listEl.appendChild(table);
  } catch (e) {
    listEl.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function managerCancelOrder(orderId) {
  if (!confirm(`Xác nhận HỦY đơn ${orderId}?\nNếu đơn đã cọc, tiền cọc sẽ không được hoàn lại.\nHành động này không thể hoàn tác.`)) return;
  try {
    // Dùng endpoint manager riêng — có thể hủy kể cả đơn đã cọc
    const result = await api('PATCH', `/manager/orders/${orderId}/cancel`);
    if (result.deposit_forfeited) {
      alert(`Đã hủy đơn. Lưu ý: ${result.deposit_note}`);
    }
    loadAllOrders();
  } catch (e) {
    alert(e.message);
  }
}

async function managerRescheduleOrder(orderId, currentTimeIso) {
  const defaultValue = _toLocalInputValue(currentTimeIso);
  const input = prompt(
    `Nhập giờ mới cho đơn ${orderId} (YYYY-MM-DDTHH:mm)`,
    defaultValue,
  );
  if (!input) return;
  const normalized = input.length === 16 ? `${input}:00` : input;

  try {
    const result = await api('PATCH', `/manager/orders/${orderId}/reschedule`, {
      new_reservation_time: normalized,
    });
    alert(
      `Đã đổi giờ đơn ${orderId}:\n` +
      `${new Date(result.old_time).toLocaleString('vi-VN')} → ${new Date(result.new_time).toLocaleString('vi-VN')}`,
    );
    loadAllOrders();
  } catch (e) {
    alert(e.message);
  }
}

async function loadRevenue() {
  const el = document.getElementById('revenue-content');
  el.innerHTML = '<p>Đang tải...</p>';
  try {
    const data = await api('GET', '/manager/revenue');
    el.innerHTML = `
      <h3>Tổng doanh thu: ${data.total_revenue.toLocaleString('vi-VN')}đ</h3>
      <table style="margin-top:12px">
        <thead><tr><th>Danh mục</th><th>Số đơn</th><th>Doanh thu</th></tr></thead>
        <tbody>
          ${data.by_category.map(r => `
            <tr>
              <td>${r.category}</td>
              <td>${r.so_don}</td>
              <td>${r.doanh_thu.toLocaleString('vi-VN')}đ</td>
            </tr>`).join('')}
        </tbody>
      </table>
    `;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function loadStaffPerf() {
  const el = document.getElementById('staff-perf-content');
  el.innerHTML = '<p>Đang tải...</p>';
  try {
    const data = await api('GET', '/manager/staff-performance');
    el.innerHTML = `
      <table>
        <thead>
          <tr><th>Nhân viên</th><th>Đang xử lý</th><th>Đã hoàn thành</th><th>Tổng đơn</th></tr>
        </thead>
        <tbody>
          ${data.map(r => `
            <tr>
              <td>${r.name} <small style="color:#888">(${r.staff_id})</small></td>
              <td>${r.dang_xu_ly}</td>
              <td>${r.da_hoan_thanh}</td>
              <td>${r.tong_don}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    `;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function loadFailedBookings() {
  const el = document.getElementById('failed-bookings-content');
  el.innerHTML = '<p>Đang tải...</p>';
  try {
    const items = await api('GET', '/manager/failed-bookings');
    if (!items.length) { el.innerHTML = '<p>Không có yêu cầu thất bại nào.</p>'; return; }
    el.innerHTML = `
      <table>
        <thead>
          <tr><th>Khách</th><th>Giờ muốn đặt</th><th>Trạng thái liên hệ</th><th>Ghi chú</th><th>Thao tác</th></tr>
        </thead>
        <tbody>
          ${items.map(r => `
            <tr>
              <td>${r.customer_name}</td>
              <td>${new Date(r.requested_time).toLocaleString('vi-VN')}</td>
              <td>
                <select id="fb-status-${r.failed_id}">
                  <option value="chưa liên hệ" ${r.contact_status === 'chưa liên hệ' ? 'selected' : ''}>chưa liên hệ</option>
                  <option value="đã liên hệ" ${r.contact_status === 'đã liên hệ' ? 'selected' : ''}>đã liên hệ</option>
                  <option value="đã giải quyết" ${r.contact_status === 'đã giải quyết' ? 'selected' : ''}>đã giải quyết</option>
                </select>
              </td>
              <td>${r.note || '—'}</td>
              <td>
                <div style="display:flex;flex-direction:column;gap:6px;min-width:280px">
                  <button onclick="managerUpdateFailedBooking('${r.failed_id}')">Cập nhật liên hệ</button>
                  <div style="display:flex;gap:6px">
                    <input id="fb-time-${r.failed_id}" type="datetime-local" value="${_toLocalInputValue(r.requested_time)}" />
                    <button onclick="managerCreateReservationFromFailed('${r.failed_id}', '${r.customer_id}')">
                      Tạo đơn hộ khách
                    </button>
                  </div>
                </div>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    `;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function managerUpdateFailedBooking(failedId) {
  const statusEl = document.getElementById(`fb-status-${failedId}`);
  if (!statusEl) return;
  const note = prompt('Nhập ghi chú liên hệ (có thể để trống):', '') || null;

  try {
    await api('PATCH', `/manager/failed-bookings/${failedId}`, {
      contact_status: statusEl.value,
      note,
    });
    loadFailedBookings();
  } catch (e) {
    alert(e.message);
  }
}

async function managerCreateReservationFromFailed(failedId, customerId) {
  const timeEl = document.getElementById(`fb-time-${failedId}`);
  const value = timeEl?.value;
  if (!value) {
    alert('Vui lòng chọn giờ đặt mới trước khi tạo đơn.');
    return;
  }
  const reservationTime = value.length === 16 ? `${value}:00` : value;

  try {
    const result = await api('POST', '/manager/reservations', {
      customer_id: customerId,
      reservation_time: reservationTime,
      items: [],
    });

    if (!result.success) {
      alert(`Không tạo được đơn: ${result.reason}`);
      return;
    }

    await api('PATCH', `/manager/failed-bookings/${failedId}`, {
      contact_status: 'đã giải quyết',
      note: `Đã tạo đơn ${result.order_id}`,
    });

    alert(
      `Đã tạo đơn ${result.order_id} cho khách.\n` +
      `Bàn ${result.table_assigned} · NV ${result.staff_assigned}`,
    );
    loadFailedBookings();
    loadAllOrders();
  } catch (e) {
    alert(e.message);
  }
}

async function loadAuditLog() {
  const el = document.getElementById('audit-log-content');
  if (!el) return;
  el.innerHTML = '<p>Đang tải...</p>';

  const actorId = document.getElementById('audit-actor-filter')?.value?.trim();
  const targetTable = document.getElementById('audit-target-filter')?.value?.trim();
  const params = new URLSearchParams({ limit: '100' });
  if (actorId) params.append('actor_id', actorId);
  if (targetTable) params.append('target_table', targetTable);

  try {
    const rows = await api('GET', `/manager/audit-log?${params.toString()}`);
    if (!rows.length) {
      el.innerHTML = '<p>Chưa có bản ghi audit phù hợp bộ lọc.</p>';
      return;
    }
    el.innerHTML = `
      <table>
        <thead>
          <tr><th>Thời gian</th><th>Actor</th><th>Action</th><th>Target</th><th>Old</th><th>New</th></tr>
        </thead>
        <tbody>
          ${rows.map(r => `
            <tr>
              <td style="white-space:nowrap">${new Date(r.created_at).toLocaleString('vi-VN')}</td>
              <td>${r.actor_role}:${r.actor_id}</td>
              <td>${r.action}</td>
              <td>${r.target_table}:${r.target_id}</td>
              <td><code style="font-size:11px">${_esc(r.old_value || 'null')}</code></td>
              <td><code style="font-size:11px">${_esc(r.new_value || 'null')}</code></td>
            </tr>`).join('')}
        </tbody>
      </table>
    `;
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

// ═══════════════════════════════════════════════════════════
// MANAGER — SQL TERMINAL
// ═══════════════════════════════════════════════════════════

function sqlTemplate(sql) {
  document.getElementById('sql-input').value = sql;
  document.getElementById('sql-input').focus();
}

function sqlKeyHandler(e) {
  // Ctrl+Enter → chạy ngay
  if (e.ctrlKey && e.key === 'Enter') {
    e.preventDefault();
    runManagerSQL();
    return;
  }
  // Tab → indent 2 spaces thay vì mất focus
  if (e.key === 'Tab') {
    e.preventDefault();
    const ta = e.target;
    const pos = ta.selectionStart;
    ta.value = ta.value.slice(0, pos) + '  ' + ta.value.slice(ta.selectionEnd);
    ta.selectionStart = ta.selectionEnd = pos + 2;
  }
}

function clearSqlTerminal() {
  document.getElementById('sql-input').value = '';
  document.getElementById('sql-output').innerHTML =
    '<span class="sql-placeholder">-- Kết quả sẽ hiển thị ở đây</span>';
  document.getElementById('sql-status').textContent = '';
}

async function runManagerSQL() {
  const sql = document.getElementById('sql-input').value.trim();
  const outputEl = document.getElementById('sql-output');
  const statusEl = document.getElementById('sql-status');

  if (!sql) return;

  outputEl.innerHTML = '<span class="sql-msg-info">Đang chạy...</span>';
  statusEl.textContent = '';

  const t0 = Date.now();
  try {
    const res = await api('POST', '/manager/sql', { sql });
    const ms = Date.now() - t0;

    if (res.type === 'select') {
      // ── SELECT → render table ────────────────────────────
      if (res.rows.length === 0) {
        outputEl.innerHTML = '<span class="sql-msg-info">✓ Query OK — 0 rows returned.</span>';
      } else {
        const colHtml = res.columns
          .map(c => `<th>${_esc(c)}</th>`)
          .join('');
        const rowsHtml = res.rows
          .map(row =>
            '<tr>' +
            row.map(cell =>
              `<td title="${_esc(String(cell ?? ''))}">${_esc(String(cell ?? 'NULL'))}</td>`
            ).join('') +
            '</tr>'
          )
          .join('');

        outputEl.innerHTML = `
          <div class="sql-msg-ok" style="margin-bottom:8px">
            ✓ ${res.rowcount} row${res.rowcount !== 1 ? 's' : ''} returned &nbsp;(${ms}ms)
          </div>
          <div style="overflow-x:auto">
            <table class="sql-result-table">
              <thead><tr>${colHtml}</tr></thead>
              <tbody>${rowsHtml}</tbody>
            </table>
          </div>
        `;
      }
      statusEl.textContent = `${res.rowcount} rows · ${ms}ms`;

    } else {
      // ── DML / DDL → hiện rows affected ──────────────────
      outputEl.innerHTML = `
        <span class="sql-msg-ok">✓ ${_esc(res.message)}&nbsp; (${ms}ms)</span>
      `;
      statusEl.textContent = `${res.rowcount} rows affected · ${ms}ms`;
    }

  } catch (e) {
    const ms = Date.now() - t0;
    // Hiện lỗi DB nguyên văn để dev debug được
    outputEl.innerHTML = `
      <span class="sql-msg-err">✗ ERROR (${ms}ms)</span><br><br>
      <span style="color:#ce9178;white-space:pre-wrap">${_esc(e.message)}</span>
    `;
    statusEl.textContent = `Error · ${ms}ms`;
  }
}

// ═══════════════════════════════════════════════════════════
// MANAGER — SECURE SEED (chạy database/secure_seed.py qua API)
// ═══════════════════════════════════════════════════════════
async function runSecureSeed(dryRun) {
  const outputEl = document.getElementById('sql-output');
  const statusEl = document.getElementById('sql-status');

  const label = dryRun ? 'Dry-run' : 'Mã hoá lại';
  if (!dryRun && !confirm(
    'Hash lại mật khẩu plain-text và ký RSA cho các Payment chưa có chữ ký?\n' +
    'Hành động này sẽ COMMIT vào database.'
  )) return;

  outputEl.innerHTML = `<span class="sql-msg-info">Đang chạy ${label}...</span>`;
  statusEl.textContent = '';
  const t0 = Date.now();

  try {
    const r = await api('POST', '/manager/secure-seed', { dry_run: dryRun });
    const ms = Date.now() - t0;
    outputEl.innerHTML = `
      <div class="sql-msg-ok" style="margin-bottom:8px">
        ✓ ${_esc(r.mode)} hoàn tất&nbsp; (${ms}ms)
      </div>
      <table class="sql-result-table">
        <thead><tr><th>Mục</th><th>Số lượng</th></tr></thead>
        <tbody>
          <tr><td>Customer rows updated</td><td>${r.customer_updated}</td></tr>
          <tr><td>Customer passwords hashed</td><td>${r.customer_pwd}</td></tr>
          <tr><td>Staff rows updated</td><td>${r.staff_updated}</td></tr>
          <tr><td>Staff passwords hashed</td><td>${r.staff_pwd}</td></tr>
          <tr><td>Payment signatures added</td><td>${r.payment_signed}</td></tr>
        </tbody>
      </table>
    `;
    statusEl.textContent = `${r.mode} · ${ms}ms`;
  } catch (e) {
    const ms = Date.now() - t0;
    outputEl.innerHTML = `
      <span class="sql-msg-err">✗ ERROR (${ms}ms)</span><br><br>
      <span style="color:#ce9178;white-space:pre-wrap">${_esc(e.message)}</span>
    `;
    statusEl.textContent = `Error · ${ms}ms`;
  }
}

// HTML escape helper — tránh XSS từ data trong DB
function _esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
