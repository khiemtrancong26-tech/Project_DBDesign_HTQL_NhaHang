// script.js — v2
'use strict';

const API = '/api';

// ═══════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════
const state = {
  user: null,
  role: 'customer',
  menuData: null,  // cache menu từ server

  // ── Booking tab ─────────────────────────────────────────
  bookingCart: {},   // { menu_item_id: quantity }
  pendingReservation: null, // response từ POST /reservations khi deposit_required

  // ── Order-at-table modal ─────────────────────────────────
  atTableOrderId: null,
  atTableCart: {},   // { menu_item_id: quantity }

  // ── Pay-final modal ──────────────────────────────────────
  // { order_id, remaining, total, deposit_paid }
  pendingFinalPayment: null,

  // ── Pay-deposit modal (từ Lịch sử) ───────────────────────
  // { order_id, deposit_amount }
  pendingDepositFromHistory: null,

  // Interval cho timer button gọi món + auto-poll trạng thái
  _historyRefreshTimer: null,
  _staffPollTimer: null,
  _managerFailedBookingTimer: null,
  _managerLastPendingFailedCount: -1,
  _lastOrderStatuses: {},    // { order_id: status } — detect 'chờ thanh toán'→'hoàn tất'
  _staffOrderSnapshot: {},   // { order_id: { status, item_count, table_id } }
  _staffLastSoundAt: 0,
  _staffDesktopNotifEnabled: false,
  _staffHistoryExpanded: {}, // { table_id: boolean } giữ trạng thái mở/đóng lịch sử theo bàn

  // Staff modals
  staffAddOrderId: null,
  staffAddCart: {},

  // Cache thông tin liên lạc manager
  managerContact: null,   // { name, phone }
};

// ═══════════════════════════════════════════════════════════
// API HELPER
// ═══════════════════════════════════════════════════════════
async function api(method, path, body = null) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.user && state.user.token) {
    headers.Authorization = `Bearer ${state.user.token}`;
  }
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  let res;
  try {
    res = await fetch(API + path, opts);
  } catch {
    throw new Error('Không kết nối được server. Kiểm tra uvicorn đang chạy chưa.');
  }
  let data;
  try { data = await res.json(); } catch {
    throw new Error('Lỗi server ' + res.status + ' — xem terminal uvicorn');
  }
  if (!res.ok) throw new Error(data.detail || 'Lỗi ' + res.status);
  return data;
}

// ═══════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════
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
  const screen = btn.closest('.screen');
  screen.querySelectorAll('.tab-content').forEach(t => {
    t.classList.remove('active');
    t.classList.add('hidden');
  });
  screen.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(tabId).classList.remove('hidden');
  document.getElementById(tabId).classList.add('active');
  btn.classList.add('active');
}

function closeModal(id) {
  document.getElementById(id).classList.add('hidden');
}

// ═══════════════════════════════════════════════════════════
// ROLE TABS (Login screen)
// ═══════════════════════════════════════════════════════════
document.querySelectorAll('.role-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.role-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.role = btn.dataset.role;
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

// ═══════════════════════════════════════════════════════════
// AUTH
// ═══════════════════════════════════════════════════════════
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
    // v2 dùng /api/auth/login
    const user = await api('POST', '/auth/login', { username, password, role: state.role });
    state.user = user;
    goToDashboard(user);
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove('hidden');
  }
}

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
    await api('POST', '/auth/register', { fullname, phone, username, password });
    alert('Đăng ký thành công! Vui lòng đăng nhập.');
    showLogin();
    document.getElementById('login-username').value = username;
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove('hidden');
  }
}

function goToDashboard(user) {
  if (user.role === 'customer') {
    document.getElementById('customer-greeting').textContent = `Xin chào, ${user.name}`;
    showScreen('screen-customer');
    initBookingTab();
  } else if (user.role === 'staff') {
    document.getElementById('staff-greeting').textContent = `${user.name} (${user.actual_role})`;
    showScreen('screen-staff');
    loadStaffOrders();
  } else if (user.role === 'manager') {
    document.getElementById('manager-greeting').textContent = `Quản lý: ${user.name}`;
    showScreen('screen-manager');
    loadAllOrders();
    if (typeof startManagerFailedBookingMonitor === 'function') {
      startManagerFailedBookingMonitor();
    }
  }
}

function logout() {
  if (typeof stopManagerFailedBookingMonitor === 'function') {
    stopManagerFailedBookingMonitor();
  }

  state.user = null;
  state.menuData = null;
  state.bookingCart = {};
  state.pendingReservation = null;
  if (state._historyRefreshTimer) {
    clearInterval(state._historyRefreshTimer);
    state._historyRefreshTimer = null;
  }
  if (state._staffPollTimer) {
    clearInterval(state._staffPollTimer);
    state._staffPollTimer = null;
  }
  if (state._managerFailedBookingTimer) {
    clearInterval(state._managerFailedBookingTimer);
    state._managerFailedBookingTimer = null;
  }
  state._managerLastPendingFailedCount = -1;
  state._lastOrderStatuses = {};
  state._staffOrderSnapshot = {};
  state._staffLastSoundAt = 0;
  state._staffDesktopNotifEnabled = false;
  state._staffHistoryExpanded = {};
  state.staffAddOrderId = null;
  state.staffAddCart = {};
  showScreen('screen-login');
  document.getElementById('login-username').value = '';
  document.getElementById('login-password').value = '';
}


// ═══════════════════════════════════════════════════════════
// UTIL
// ═══════════════════════════════════════════════════════════
function badgeHtml(status) {
  const map = {
    'đang xử lý':    'badge-process',
    'chờ thanh toán': 'badge-waiting',
    'hoàn tất':      'badge-done',
    'đã thanh toán': 'badge-paid',
    'đã hủy':        'badge-cancelled',
  };
  return `<span class="badge ${map[status] || ''}">${status}</span>`;
}

function showMsg(el, text, isError) {
  el.textContent = text;
  el.classList.remove('hidden');
  if (isError) el.classList.add('error');
  else el.classList.remove('error');
}

async function verifyPaymentAndAlert(paymentId) {
  if (!paymentId) return;
  try {
    const result = await api('GET', `/payments/${paymentId}/verify`);
    const headline = result.verified ? '✅ Chữ ký số hợp lệ' : '⚠️ Chữ ký số không hợp lệ';
    alert(`${headline}\nMã thanh toán: ${paymentId}\n${result.note || ''}`.trim());
  } catch (e) {
    alert(`⚠️ Không xác minh được chữ ký hóa đơn ${paymentId}: ${e.message}`);
  }
}
