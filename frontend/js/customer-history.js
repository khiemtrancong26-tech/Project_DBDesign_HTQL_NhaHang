// ═══════════════════════════════════════════════════════════
// CUSTOMER — LỊCH SỬ TAB
// ═══════════════════════════════════════════════════════════

async function loadHistory() {
  const listEl = document.getElementById('history-list');
  listEl.innerHTML = '<p style="color:#888">Đang tải...</p>';

  // Dừng timer cũ nếu có
  if (state._historyRefreshTimer) {
    clearInterval(state._historyRefreshTimer);
    state._historyRefreshTimer = null;
  }

  try {
    const orders = await api('GET', `/orders/customer/${state.user.id}`);
    // Lưu trạng thái ban đầu để detect thay đổi
    orders.forEach(o => { state._lastOrderStatuses[o.order_id] = o.status; });
    renderHistoryList(orders, listEl);

    // Có đơn active → poll 5s để bắt tín hiệu nhân viên xác nhận thanh toán
    const hasActive = orders.some(o =>
      ['đang xử lý', 'chờ thanh toán', 'hoàn tất'].includes(o.status)
    );
    if (hasActive) {
      _startCustomerPoll(listEl);
    }

  } catch (e) {
    listEl.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function _startCustomerPoll(listEl) {
  if (state._historyRefreshTimer) return; // đã chạy
  state._historyRefreshTimer = setInterval(async () => {
    if (!state.user || state.user.role !== 'customer') {
      clearInterval(state._historyRefreshTimer);
      state._historyRefreshTimer = null;
      return;
    }
    const fresh = await api('GET', `/orders/customer/${state.user.id}`).catch(() => null);
    if (!fresh) return;

    // Detect 'chờ thanh toán' → 'hoàn tất' → tự mở modal thanh toán
    fresh.forEach(o => {
      const prev = state._lastOrderStatuses[o.order_id];
      if (prev === 'chờ thanh toán' && o.status === 'hoàn tất') {
        const remaining = o.total != null ? Math.max(0, o.total - (o.deposit_paid || 0)) : 0;
        openPayWarningModal(o.order_id, remaining, o.total || 0, o.deposit_paid || 0);
      }
      state._lastOrderStatuses[o.order_id] = o.status;
    });

    renderHistoryList(fresh, listEl);

    // Dừng poll nếu không còn đơn active
    const stillActive = fresh.some(o =>
      ['đang xử lý', 'chờ thanh toán', 'hoàn tất'].includes(o.status)
    );
    if (!stillActive) {
      clearInterval(state._historyRefreshTimer);
      state._historyRefreshTimer = null;
    }
  }, 5000);
}

function renderHistoryList(orders, listEl) {
  listEl.innerHTML = '';
  if (!orders.length) {
    listEl.innerHTML = '<p>Chưa có đặt bàn nào.</p>';
    return;
  }
  orders.forEach(order => {
    listEl.appendChild(buildOrderCard(order));
  });
}

// ─────────────────────────────────────────────────────────────
// Build card cho mỗi đơn trong lịch sử
// ─────────────────────────────────────────────────────────────
function buildOrderCard(o) {
  const card = document.createElement('div');
  card.className = 'card-item';
  card.id = `card-${o.order_id}`;

  const resTime = new Date(o.reservation_time);
  const endTime = new Date(o.estimated_end);

  const isActive = ['đang xử lý', 'chờ thanh toán', 'hoàn tất'].includes(o.status);
  const total = o.total;            // null hoặc số
  const depositPaid = o.deposit_paid || 0;
  const hasPreOrder = total != null && total > 0;
  // Cần đóng cọc khi: có đặt món trước VÀ chưa trả cọc đồng nào
  const depositNeeded = hasPreOrder && depositPaid === 0;

  // ── Header ──────────────────────────────────────────────
  card.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <h4 style="margin:0">${o.order_id}</h4>
      ${badgeHtml(o.status)}
    </div>
    <div class="meta">
      🕐 ${resTime.toLocaleString('vi-VN')} → ${endTime.toLocaleTimeString('vi-VN')}
    </div>
    <div class="meta">
      🪑 Bàn: <strong>${o.table_id}</strong> &nbsp;|&nbsp;
      👤 NV: ${o.staff_name}
    </div>
    ${buildBillSummary(o)}
    <div class="actions" id="actions-${o.order_id}">
      ${buildActionButtons(o, isActive, hasPreOrder, depositNeeded, depositPaid, resTime, endTime)}
    </div>
  `;

  return card;
}

function buildBillSummary(o) {
  const total = o.total;
  const depositPaid = o.deposit_paid || 0;
  if (total == null) return '<div class="meta" style="color:#aaa">Chưa có món nào</div>';

  const remaining = Math.max(0, total - depositPaid);
  return `
    <div class="meta">
      💰 Tổng: <strong>${total.toLocaleString('vi-VN')}đ</strong>
      ${depositPaid > 0 ? ` | Đã cọc: <span style="color:#0f5132">${depositPaid.toLocaleString('vi-VN')}đ</span>` : ''}
      ${remaining > 0 && o.status !== 'đã thanh toán' ? ` | Còn lại: <strong style="color:#c00">${remaining.toLocaleString('vi-VN')}đ</strong>` : ''}
    </div>
  `;
}

function buildActionButtons(o, isActive, hasPreOrder, depositNeeded, depositPaid, resTime, endTime) {
  if (!isActive) return ''; // Đã thanh toán, đã hủy → không có button

  const contactBtn = `<button onclick="openManagerContact()" style="background:#666;font-size:12px">📞 Đổi giờ / Hủy bàn</button>`;

  // ── Trường hợp 1: Cần đặt cọc trước (pre-order chưa trả cọc) ──────────
  if (depositNeeded) {
    const depositAmount = Math.round(o.total * 0.30);
    return `
      <div class="deposit-alert">
        ⚠️ Cần đặt cọc <strong>${depositAmount.toLocaleString('vi-VN')}đ</strong>
        (30% tổng đơn) để xác nhận bàn
      </div>
      <button onclick="openDepositModalFromHistory('${o.order_id}', ${depositAmount})">
        💳 Thanh toán cọc 30%
      </button>
      ${contactBtn}
    `;
  }

  // ── Trường hợp 2: 'đang xử lý' — gọi thêm món + yêu cầu thanh toán ───
  if (o.status === 'đang xử lý') {
    const now = new Date();
    const canOrder = _canOrderAtTable(resTime, endTime, now);
    const minsLeft = _minutesUntilCanOrder(resTime, now);

    const orderBtn = canOrder
      ? `<button onclick="openOrderAtTable('${o.order_id}')">🍽️ Gọi thêm món</button>`
      : `<div>
           <button disabled>🍽️ Gọi thêm món</button>
           <div class="timer-hint">Mở sau ${minsLeft} phút nữa (15 phút trước giờ đặt)</div>
         </div>`;

    const hasItems = o.total != null && o.total > 0;
    const reqPayBtn = hasItems
      ? `<button class="btn-pay" onclick="requestPayment('${o.order_id}')">
           📤 Yêu cầu thanh toán
         </button>`
      : `<button class="btn-pay" disabled title="Chưa có món nào">📤 Yêu cầu thanh toán</button>`;

    return `${orderBtn}${reqPayBtn}${contactBtn}`;
  }

  // ── Trường hợp 3: 'chờ thanh toán' — chờ nhân viên xác nhận ───────────
  if (o.status === 'chờ thanh toán') {
    return `
      <button disabled style="background:#856404;cursor:default;opacity:1">
        ⏳ Đang chờ nhân viên xác nhận...
      </button>
      <button onclick="cancelPaymentRequest('${o.order_id}')" style="background:#555">
        ↩ Hủy yêu cầu
      </button>
    `;
  }

  // ── Trường hợp 4: 'hoàn tất' — nhân viên đã xác nhận, tiến hành TT ────
  if (o.status === 'hoàn tất') {
    const remaining = o.total != null ? Math.max(0, o.total - (o.deposit_paid || 0)) : 0;
    const payLabel  = o.total != null
      ? `💳 Tiến hành thanh toán ${remaining.toLocaleString('vi-VN')}đ`
      : '💳 Tiến hành thanh toán';
    return `
      <div style="font-size:13px;color:#0f5132;margin-bottom:6px">
        ✅ Nhân viên đã xác nhận — bạn có thể thanh toán ngay
      </div>
      <button class="btn-pay"
        onclick="openPayWarningModal('${o.order_id}', ${remaining}, ${o.total || 0}, ${o.deposit_paid || 0})">
        ${payLabel}
      </button>
    `;
  }

  return '';
}

// ─────────────────────────────────────────────────────────────
// Modal liên hệ manager (Đổi giờ / Hủy bàn)
// ─────────────────────────────────────────────────────────────
async function openManagerContact() {
  document.getElementById('modal-manager-contact').classList.remove('hidden');
  const infoEl = document.getElementById('mc-info');

  // Dùng cache nếu đã fetch rồi
  if (state.managerContact) {
    renderManagerContact(state.managerContact, infoEl);
    return;
  }

  infoEl.innerHTML = '<p>Đang tải thông tin...</p>';
  try {
    const data = await api('GET', '/manager/contact');
    state.managerContact = data;
    renderManagerContact(data, infoEl);
  } catch {
    infoEl.innerHTML = `
      <p>Vui lòng liên hệ trực tiếp nhà hàng để được hỗ trợ đổi giờ hoặc hủy bàn.</p>
    `;
  }
}

function renderManagerContact(data, el) {
  el.innerHTML = `
    <p style="font-size:15px;margin-bottom:6px">
      👤 <strong>${data.name}</strong>
    </p>
    <p style="font-size:20px;font-weight:bold;color:#0f5132;margin-bottom:8px">
      📞 ${data.phone}
    </p>
    <p style="font-size:13px;color:#555">
      Vui lòng gọi điện để thông báo yêu cầu đổi giờ hoặc hủy bàn.<br>
      Chúng tôi sẽ xử lý và xác nhận lại với bạn sớm nhất.
    </p>
  `;
}

// Kiểm tra có được gọi món tại bàn chưa
// Điều kiện: now >= resTime - 15 phút VÀ now < endTime
function _canOrderAtTable(resTime, endTime, now) {
  const openAt = new Date(resTime.getTime() - 15 * 60 * 1000);
  return now >= openAt && now < endTime;
}

// Bao nhiêu phút nữa mới được gọi món
function _minutesUntilCanOrder(resTime, now) {
  const openAt = new Date(resTime.getTime() - 15 * 60 * 1000);
  const diffMs = openAt - now;
  if (diffMs <= 0) return 0;
  return Math.ceil(diffMs / 60000);
}

// ═══════════════════════════════════════════════════════════
// MODAL: THANH TOÁN CỌC TỪ LỊCH SỬ
// ═══════════════════════════════════════════════════════════
function openDepositModalFromHistory(orderId, depositAmount) {
  state.pendingDepositFromHistory = { order_id: orderId, amount: depositAmount };
  document.getElementById('md-order-id').textContent = orderId;
  document.getElementById('md-deposit-amount').textContent =
    depositAmount.toLocaleString('vi-VN') + 'đ';
  document.getElementById('md-msg').classList.add('hidden');
  document.getElementById('modal-deposit').classList.remove('hidden');
}

async function confirmDepositFromHistory() {
  const { order_id, amount } = state.pendingDepositFromHistory;
  const method = document.getElementById('md-method').value;
  const msgEl = document.getElementById('md-msg');
  msgEl.classList.add('hidden');

  try {
    const payment = await api('POST', '/payments', {
      order_id,
      amount,
      method,
      payment_type: 'cọc',
    });
    await verifyPaymentAndAlert(payment.payment_id);
    closeModal('modal-deposit');
    loadHistory(); // Refresh lịch sử
  } catch (e) {
    showMsg(msgEl, e.message, true);
  }
}

// ═══════════════════════════════════════════════════════════
// MODAL: GỌI MÓN TẠI BÀN
// Chỉ mở được khi _canOrderAtTable() = true (đã check ở button)
// ═══════════════════════════════════════════════════════════
async function openOrderAtTable(orderId) {
  state.atTableOrderId = orderId;
  state.atTableCart = {};

  const el = document.getElementById('at-table-menu-list');
  el.innerHTML = '<p>Đang tải menu...</p>';
  document.getElementById('at-table-summary').classList.add('hidden');
  document.getElementById('at-table-msg').classList.add('hidden');
  document.getElementById('modal-order-at-table').classList.remove('hidden');

  try {
    if (!state.menuData) state.menuData = await api('GET', '/menu');
    el.innerHTML = '';
    state.menuData.forEach(cat => {
      const sec = document.createElement('div');
      sec.className = 'menu-category';
      sec.innerHTML = `<h4>${cat.category_name}</h4>`;
      cat.items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'menu-item';
        row.innerHTML = `
          <span class="menu-item-name">${item.food_name}</span>
          <span class="menu-item-price">${item.price.toLocaleString('vi-VN')}đ</span>
          <input type="number" min="0" max="99" value="0"
            data-id="${item.menu_item_id}" data-price="${item.price}"
            onchange="updateAtTableCart(this)" />
        `;
        sec.appendChild(row);
      });
      el.appendChild(sec);
    });
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function updateAtTableCart(input) {
  const id = input.dataset.id;
  const qty = parseInt(input.value) || 0;
  if (qty > 0) state.atTableCart[id] = qty;
  else delete state.atTableCart[id];

  let total = 0;
  document.querySelectorAll('#at-table-menu-list input[type=number]').forEach(inp => {
    total += (parseInt(inp.value) || 0) * parseFloat(inp.dataset.price);
  });

  const summary = document.getElementById('at-table-summary');
  if (Object.keys(state.atTableCart).length > 0) {
    summary.classList.remove('hidden');
    document.getElementById('at-table-total-text').textContent =
      total.toLocaleString('vi-VN') + 'đ';
  } else {
    summary.classList.add('hidden');
  }
}

async function submitOrderAtTable() {
  const msgEl = document.getElementById('at-table-msg');
  msgEl.classList.add('hidden');

  const items = Object.entries(state.atTableCart).map(([menu_item_id, quantity]) => ({
    menu_item_id, quantity,
  }));

  if (!items.length) {
    showMsg(msgEl, 'Chưa chọn món nào', true);
    return;
  }

  try {
    // POST /api/orders/{id}/items — truyền customer_id để validate ownership
    await api('POST', `/orders/${state.atTableOrderId}/items`, {
      customer_id: state.user.id,
      items,
    });
    closeModal('modal-order-at-table');
    loadHistory(); // Cập nhật tổng tiền mới trong lịch sử
  } catch (e) {
    showMsg(msgEl, e.message, true);
  }
}

// ═══════════════════════════════════════════════════════════
// CUSTOMER — YÊU CẦU THANH TOÁN (2-step flow)
// ═══════════════════════════════════════════════════════════

async function requestPayment(orderId) {
  if (!confirm(
    'Gửi yêu cầu thanh toán cho nhân viên?\n\n' +
    'Nhân viên sẽ đến xác nhận, sau đó bạn mới tiến hành thanh toán được.\n' +
    'Bạn vẫn có thể hủy yêu cầu nếu muốn tiếp tục gọi món.'
  )) return;
  try {
    await api('POST', `/orders/${orderId}/request-payment`, { customer_id: state.user.id });
    // Cập nhật ngay — không cần đợi poll
    const listEl = document.getElementById('history-list');
    const fresh = await api('GET', `/orders/customer/${state.user.id}`);
    fresh.forEach(o => { state._lastOrderStatuses[o.order_id] = o.status; });
    renderHistoryList(fresh, listEl);
    _startCustomerPoll(listEl);
  } catch (e) {
    alert(e.message);
  }
}

async function cancelPaymentRequest(orderId) {
  try {
    await api('POST', `/orders/${orderId}/cancel-payment-request`, { customer_id: state.user.id });
    const listEl = document.getElementById('history-list');
    const fresh = await api('GET', `/orders/customer/${state.user.id}`);
    fresh.forEach(o => { state._lastOrderStatuses[o.order_id] = o.status; });
    renderHistoryList(fresh, listEl);
  } catch (e) {
    alert(e.message);
  }
}

// ═══════════════════════════════════════════════════════════
// MODAL: CẢNH BÁO THANH TOÁN HOÀN TẤT
// ═══════════════════════════════════════════════════════════
function openPayWarningModal(orderId, remaining, total, depositPaid) {
  state.pendingFinalPayment = { order_id: orderId, remaining, total, depositPaid };

  // Hiện bill tóm tắt trong modal
  const billEl = document.getElementById('pw-bill');
  billEl.innerHTML = `
    <div class="bill-row"><span>Tổng đơn:</span><span>${total.toLocaleString('vi-VN')}đ</span></div>
    ${depositPaid > 0 ? `<div class="bill-row"><span>Đã cọc:</span><span>− ${depositPaid.toLocaleString('vi-VN')}đ</span></div>` : ''}
    <div class="bill-row total"><span>Cần thanh toán:</span><span>${remaining.toLocaleString('vi-VN')}đ</span></div>
  `;

  document.getElementById('final-pay-msg').classList.add('hidden');
  document.getElementById('modal-pay-warning').classList.remove('hidden');
}

async function confirmFinalPayment() {
  const { order_id, remaining } = state.pendingFinalPayment;
  const method = document.getElementById('final-pay-method').value;
  const msgEl = document.getElementById('final-pay-msg');
  msgEl.classList.add('hidden');

  try {
    const payment = await api('POST', '/payments', {
      order_id,
      amount: remaining,
      method,
      payment_type: 'hoàn tất',
    });
    await verifyPaymentAndAlert(payment.payment_id);
    closeModal('modal-pay-warning');
    loadHistory(); // Card sẽ đổi sang trạng thái "đã thanh toán"
  } catch (e) {
    showMsg(msgEl, e.message, true);
  }
}

