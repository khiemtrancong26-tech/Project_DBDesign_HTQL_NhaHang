// script.js
const API = '/api';

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  user: null,       // { id, name, role }
  role: 'customer', // role đang chọn trên form login
  cart: {},         // { menu_item_id: quantity }
  currentInvoiceOrderId: null,
  currentInvoiceTotal: null,
};

// ── API helper ────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);

  let res;
  try {
    res = await fetch(API + path, opts);
  } catch (e) {
    throw new Error('Không kết nối được server. Kiểm tra uvicorn đang chạy chưa.');
  }

  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error('Lỗi server ' + res.status + ' — xem terminal uvicorn để biết chi tiết');
  }

  if (!res.ok) throw new Error(data.detail || 'Lỗi ' + res.status);
  return data;
}

// ── Navigation ────────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => {
    s.classList.remove('active');
    s.classList.add('hidden');
  });
  const el = document.getElementById(id);
  el.classList.remove('hidden');
  el.classList.add('active');
}

function switchTab(tabId, btn) {
  // Tắt tất cả tab trong cùng screen
  const screen = btn.closest('.screen');
  screen.querySelectorAll('.tab-content').forEach(t => {
    t.classList.remove('active');
    t.classList.add('hidden');
  });
  screen.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  // Bật tab được chọn
  document.getElementById(tabId).classList.remove('hidden');
  document.getElementById(tabId).classList.add('active');
  btn.classList.add('active');
}

// ── Role selector (login screen) ──────────────────────────────────────────
document.querySelectorAll('.role-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.role-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.role = btn.dataset.role;

    // Ẩn/hiện link đăng ký — chỉ customer mới có
    const regLink = document.getElementById('register-link');
    regLink.classList.toggle('hidden', state.role !== 'customer');
  });
});

function showRegister() {
  document.getElementById('form-login').classList.add('hidden');
  document.getElementById('form-register').classList.remove('hidden');
}

function showLogin() {
  document.getElementById('form-register').classList.add('hidden');
  document.getElementById('form-login').classList.remove('hidden');
}

// ── AUTH: Login ───────────────────────────────────────────────────────────
async function login() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.classList.add('hidden');

  if (!username || !password) {
    errEl.textContent = 'Vui lòng nhập đủ username và password';
    errEl.classList.remove('hidden');
    return;
  }

  try {
    const user = await api('POST', '/login', { username, password, role: state.role });
    state.user = user;
    goToDashboard(user);
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove('hidden');
  }
}

// ── AUTH: Register ────────────────────────────────────────────────────────
async function register() {
  const fullname = document.getElementById('reg-fullname').value.trim();
  const phone = document.getElementById('reg-phone').value.trim();
  const username = document.getElementById('reg-username').value.trim();
  const password = document.getElementById('reg-password').value;
  const errEl = document.getElementById('register-error');
  errEl.classList.add('hidden');

  if (!fullname || !phone || !username || !password) {
    errEl.textContent = 'Vui lòng điền đầy đủ thông tin';
    errEl.classList.remove('hidden');
    return;
  }

  try {
    await api('POST', '/register', { fullname, phone, username, password });
    alert('Đăng ký thành công! Vui lòng đăng nhập.');
    showLogin();
    document.getElementById('login-username').value = username;
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove('hidden');
  }
}

// ── Điều hướng sau login ──────────────────────────────────────────────────
function goToDashboard(user) {
  if (user.role === 'customer') {
    document.getElementById('customer-greeting').textContent = `Xin chào, ${user.name}`;
    showScreen('screen-customer');
    loadMenu();
  } else if (user.role === 'staff') {
    document.getElementById('staff-greeting').textContent = `${user.name} (${user.actual_role})`;
    showScreen('screen-staff');
    loadStaffOrders();
  } else if (user.role === 'manager') {
    document.getElementById('manager-greeting').textContent = `Quản lý: ${user.name}`;
    showScreen('screen-manager');
    loadAllOrders();
  }
}

function logout() {
  state.user = null;
  state.cart = {};
  showScreen('screen-login');
  document.getElementById('login-username').value = '';
  document.getElementById('login-password').value = '';
}

// ═════════════════════════════════════════════════════════════════════════
// CUSTOMER
// ═════════════════════════════════════════════════════════════════════════

// ── Load menu ─────────────────────────────────────────────────────────────
async function loadMenu() {
  const menuEl = document.getElementById('menu-list');
  menuEl.innerHTML = '<p>Đang tải menu...</p>';
  state.cart = {};

  try {
    const categories = await api('GET', '/menu');
    menuEl.innerHTML = '';

    categories.forEach(cat => {
      const section = document.createElement('div');
      section.className = 'menu-category';
      section.innerHTML = `<h3>${cat.category_name}</h3>`;

      cat.items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'menu-item';
        row.innerHTML = `
          <span class="menu-item-name">${item.food_name}</span>
          <span class="menu-item-price">${item.price.toLocaleString('vi-VN')}đ</span>
          <input type="number" min="0" max="99" value="0"
            data-id="${item.menu_item_id}" data-price="${item.price}"
            onchange="updateCart(this)" />
        `;
        section.appendChild(row);
      });

      menuEl.appendChild(section);
    });
  } catch (e) {
    menuEl.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function updateCart(input) {
  const id = input.dataset.id;
  const qty = parseInt(input.value) || 0;
  if (qty > 0) state.cart[id] = qty;
  else delete state.cart[id];

  // Tính tổng preview
  let total = 0;
  document.querySelectorAll('.menu-item input[type=number]').forEach(inp => {
    const qty = parseInt(inp.value) || 0;
    total += qty * parseFloat(inp.dataset.price);
  });

  const footer = document.getElementById('order-footer');
  if (Object.keys(state.cart).length > 0) {
    footer.classList.remove('hidden');
    document.getElementById('order-total-preview').textContent =
      `Tổng dự tính: ${total.toLocaleString('vi-VN')}đ`;
  } else {
    footer.classList.add('hidden');
  }
}

// ── Đặt hàng ─────────────────────────────────────────────────────────────
async function placeOrder() {
  const items = Object.entries(state.cart).map(([menu_item_id, quantity]) => ({
    menu_item_id, quantity,
  }));
  const msgEl = document.getElementById('order-msg');
  msgEl.classList.add('hidden');

  try {
    const res = await api('POST', '/orders', {
      customer_id: state.user.id,
      items,
    });
    state.cart = {};
    document.getElementById('order-footer').classList.add('hidden');
    // Reset quantity inputs
    document.querySelectorAll('.menu-item input[type=number]').forEach(i => i.value = 0);

    msgEl.textContent =
      `✓ Đặt hàng thành công! Bàn: ${res.table_assigned} — Nhân viên: ${res.staff_assigned} — Tổng: ${res.total_amount.toLocaleString('vi-VN')}đ`;
    msgEl.classList.remove('hidden', 'error');
  } catch (e) {
    msgEl.textContent = e.message;
    msgEl.classList.remove('hidden');
    msgEl.classList.add('error');
  }
}

// ── Đơn của tôi ───────────────────────────────────────────────────────────
async function loadMyOrders() {
  const listEl = document.getElementById('my-orders-list');
  listEl.innerHTML = '<p>Đang tải...</p>';
  document.getElementById('invoice-detail').classList.add('hidden');

  try {
    const orders = await api('GET', `/orders/customer/${state.user.id}`);
    listEl.innerHTML = '';

    if (!orders.length) {
      listEl.innerHTML = '<p>Chưa có đơn hàng nào.</p>';
      return;
    }

    orders.forEach(o => {
      const div = document.createElement('div');
      div.className = 'card-item';
      div.innerHTML = `
        <h4>${o.order_id} — ${badgeHtml(o.status)}</h4>
        <div class="meta">Ngày: ${o.order_date} | Bàn: ${o.table_id} | NV: ${o.staff_name}</div>
        <div class="meta">Tổng: ${o.total ? o.total.toLocaleString('vi-VN') + 'đ' : '—'}</div>
        <div class="actions">
          <button onclick="viewInvoice('${o.order_id}', ${o.total})">Xem hóa đơn</button>
        </div>
      `;
      listEl.appendChild(div);
    });
  } catch (e) {
    listEl.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function viewInvoice(orderId, total) {
  state.currentInvoiceOrderId = orderId;
  state.currentInvoiceTotal = total;

  const detail = document.getElementById('invoice-detail');
  const content = document.getElementById('invoice-content');
  const payForm = document.getElementById('payment-form');
  const payMsg = document.getElementById('payment-msg');
  content.innerHTML = '<p>Đang tải...</p>';
  detail.classList.remove('hidden');
  payMsg.classList.add('hidden');

  try {
    const inv = await api('GET', `/orders/${orderId}/invoice`);
    const o = inv.order;

    let rows = inv.items.map(i =>
      `<tr><td>${i.food_name}</td><td>${i.quantity}</td><td>${i.unit_price.toLocaleString('vi-VN')}đ</td><td>${i.subtotal.toLocaleString('vi-VN')}đ</td></tr>`
    ).join('');

    content.innerHTML = `
      <p><b>${o.order_id}</b> — ${badgeHtml(o.status)} — Bàn: ${o.table_id}</p>
      <p>Khách: ${o.customer_name} | NV: ${o.staff_name} | Ngày: ${o.order_date}</p>
      <table style="margin-top:10px">
        <thead><tr><th>Món</th><th>SL</th><th>Đơn giá</th><th>Thành tiền</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <p style="margin-top:8px;font-weight:bold">Tổng: ${o.total_amount ? o.total_amount.toLocaleString('vi-VN') + 'đ' : '—'}</p>
    `;

    // Hiện form thanh toán nếu chưa thanh toán và chưa hủy
    const canPay = !['đã thanh toán', 'đã hủy'].includes(o.status);
    payForm.classList.toggle('hidden', !canPay);
  } catch (e) {
    content.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function submitPayment() {
  const method = document.getElementById('payment-method').value;
  const msgEl = document.getElementById('payment-msg');
  msgEl.classList.add('hidden');

  try {
    const res = await api('POST', '/payments', {
      order_id: state.currentInvoiceOrderId,
      amount: state.currentInvoiceTotal,
      method,
    });
    msgEl.textContent = `✓ Thanh toán thành công! Bàn ${res.table_released} đã được giải phóng.`;
    msgEl.classList.remove('hidden', 'error');
    document.getElementById('payment-form').classList.add('hidden');
    loadMyOrders();
  } catch (e) {
    msgEl.textContent = e.message;
    msgEl.classList.remove('hidden');
    msgEl.classList.add('error');
  }
}

function closeInvoice() {
  document.getElementById('invoice-detail').classList.add('hidden');
}

// ═════════════════════════════════════════════════════════════════════════
// STAFF
// ═════════════════════════════════════════════════════════════════════════
async function loadStaffOrders() {
  const listEl = document.getElementById('staff-orders-list');
  listEl.innerHTML = '<p>Đang tải...</p>';

  try {
    const orders = await api('GET', `/staff/${state.user.id}/orders`);
    listEl.innerHTML = '';

    if (!orders.length) {
      listEl.innerHTML = '<p>Không có đơn nào.</p>';
      return;
    }

    orders.forEach(o => {
      const div = document.createElement('div');
      div.className = 'card-item';
      const canUpdate = o.status === 'đang xử lý';
      div.innerHTML = `
        <h4>${o.order_id} — ${badgeHtml(o.status)}</h4>
        <div class="meta">Khách: ${o.customer_name} | Bàn: ${o.table_id} | Ngày: ${o.order_date}</div>
        <div class="meta">Tổng: ${o.total ? o.total.toLocaleString('vi-VN') + 'đ' : '—'}</div>
        <div class="actions">
          ${canUpdate ? `
            <button onclick="updateStatus('${o.order_id}', 'hoàn tất')">✓ Hoàn tất</button>
            <button onclick="updateStatus('${o.order_id}', 'đã hủy')" style="background:#c00">Hủy đơn</button>
          ` : ''}
        </div>
      `;
      listEl.appendChild(div);
    });
  } catch (e) {
    listEl.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function updateStatus(orderId, status) {
  if (!confirm(`Xác nhận chuyển đơn ${orderId} sang "${status}"?`)) return;
  try {
    await api('PATCH', `/orders/${orderId}/status`, { status });
    loadStaffOrders();
  } catch (e) {
    alert(e.message);
  }
}

// ═════════════════════════════════════════════════════════════════════════
// MANAGER
// ═════════════════════════════════════════════════════════════════════════
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
      <thead><tr><th>Mã đơn</th><th>Ngày</th><th>Trạng thái</th><th>Khách</th><th>NV</th><th>Bàn</th><th>Tổng</th></tr></thead>
      <tbody>
        ${orders.map(o => `
          <tr>
            <td>${o.order_id}</td>
            <td>${o.order_date}</td>
            <td>${badgeHtml(o.status)}</td>
            <td>${o.customer_name}</td>
            <td>${o.staff_name}</td>
            <td>${o.table_id}</td>
            <td>${o.total ? o.total.toLocaleString('vi-VN') + 'đ' : '—'}</td>
          </tr>`).join('')}
      </tbody>
    `;
    listEl.appendChild(table);
  } catch (e) {
    listEl.innerHTML = `<p class="error">${e.message}</p>`;
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
        <thead><tr><th>Nhân viên</th><th>Đang xử lý</th><th>Đã hoàn thành</th><th>Tổng đơn</th></tr></thead>
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

// ── Util ──────────────────────────────────────────────────────────────────
function badgeHtml(status) {
  const map = {
    'đang xử lý': 'badge-process',
    'hoàn tất': 'badge-done',
    'đã thanh toán': 'badge-paid',
    'đã hủy': 'badge-cancelled',
  };
  const cls = map[status] || '';
  return `<span class="badge ${cls}">${status}</span>`;
}