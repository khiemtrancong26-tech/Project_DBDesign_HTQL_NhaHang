// STAFF — Realtime quản lý theo từng bàn phụ trách
// ═══════════════════════════════════════════════════════════
async function loadStaffOrders() {
  if (state._staffPollTimer) {
    clearInterval(state._staffPollTimer);
    state._staffPollTimer = null;
  }

  const listEl = document.getElementById('staff-orders-list');
  listEl.innerHTML = '<p>Đang tải...</p>';

  try {
    const orders = await _fetchStaffOrders();
    state._staffOrderSnapshot = _buildStaffSnapshot(orders);
    _renderStaffOrders(orders, listEl);
    _startStaffPoll(listEl);
    _ensureStaffDesktopPermission();
  } catch (e) {
    listEl.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function _fetchStaffOrders() {
  return api('GET', `/staff/${state.user.id}/orders`);
}

function _buildStaffSnapshot(orders) {
  const snap = {};
  orders.forEach(o => {
    snap[o.order_id] = {
      status: o.status,
      item_count: o.item_count || 0,
      table_id: o.table_id,
      customer_name: o.customer_name,
    };
  });
  return snap;
}

const STAFF_OPEN_STATUSES = ['chờ thanh toán', 'đang xử lý', 'hoàn tất'];
const STAFF_CLOSED_STATUSES = ['đã thanh toán', 'đã hủy'];
const STAFF_STATUS_PRIORITY = {
  'chờ thanh toán': 0,
  'đang xử lý': 1,
  'hoàn tất': 2,
  'đã thanh toán': 3,
  'đã hủy': 4,
};

function _sortByStatusThenTime(a, b) {
  const pa = STAFF_STATUS_PRIORITY[a.status] ?? 99;
  const pb = STAFF_STATUS_PRIORITY[b.status] ?? 99;
  if (pa !== pb) return pa - pb;
  return new Date(b.reservation_time) - new Date(a.reservation_time);
}

function _sortByTimeDesc(a, b) {
  return new Date(b.reservation_time) - new Date(a.reservation_time);
}

function _startStaffPoll(listEl) {
  if (state._staffPollTimer) return;

  state._staffPollTimer = setInterval(async () => {
    if (!state.user || state.user.role !== 'staff') {
      clearInterval(state._staffPollTimer);
      state._staffPollTimer = null;
      return;
    }

    const fresh = await _fetchStaffOrders().catch(() => null);
    if (!fresh) return;

    const events = _collectStaffRealtimeEvents(fresh);
    _renderStaffOrders(fresh, listEl);
    _dispatchStaffEvents(events);
  }, 5000);
}

function _collectStaffRealtimeEvents(fresh) {
  const previous = state._staffOrderSnapshot || {};
  const current = _buildStaffSnapshot(fresh);
  const events = [];

  fresh.forEach(order => {
    const oldOrder = previous[order.order_id];

    if (!oldOrder) {
      events.push({
        kind: 'new_order',
        order_id: order.order_id,
        table_id: order.table_id,
        title: `Bàn ${order.table_id} có đơn mới`,
        message: `${order.customer_name} vừa được phân công cho bạn (${order.order_id}).`,
      });
      return;
    }

    if (order.item_count > oldOrder.item_count) {
      const added = order.item_count - oldOrder.item_count;
      events.push({
        kind: 'items_added',
        order_id: order.order_id,
        table_id: order.table_id,
        title: `Bàn ${order.table_id} gọi thêm món`,
        message: `${order.order_id} vừa gọi thêm ${added} món.`,
      });
    }

    if (order.status !== oldOrder.status && order.status === 'chờ thanh toán') {
      events.push({
        kind: 'status_changed',
        order_id: order.order_id,
        table_id: order.table_id,
        title: `Bàn ${order.table_id} yêu cầu thanh toán`,
        message: `${order.order_id} vừa chuyển sang trạng thái chờ thanh toán.`,
      });
    }
  });

  state._staffOrderSnapshot = current;
  return events;
}

function _dispatchStaffEvents(events) {
  if (!events.length) return;

  events.forEach(event => {
    _showStaffBanner(event);
    _playStaffAlertSound();
    _showStaffDesktopNotification(event);
  });
}

function _showStaffBanner(event) {
  const container = document.getElementById('staff-live-alerts');
  if (!container) return;

  const item = document.createElement('div');
  item.className = 'staff-live-alert-item';
  item.innerHTML = `
    <div class="staff-live-alert-title">${event.title}</div>
    <div class="staff-live-alert-body">${event.message}</div>
  `;

  container.prepend(item);
  while (container.children.length > 5) {
    container.removeChild(container.lastChild);
  }
  setTimeout(() => item.remove(), 14000);
}

function _playStaffAlertSound() {
  const now = Date.now();
  if (now - state._staffLastSoundAt < 1400) return;
  state._staffLastSoundAt = now;

  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.value = 920;
    osc.connect(gain);
    gain.connect(ctx.destination);

    const t = ctx.currentTime;
    gain.gain.setValueAtTime(0.001, t);
    gain.gain.exponentialRampToValueAtTime(0.14, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.24);

    osc.start(t);
    osc.stop(t + 0.25);
    osc.onended = () => ctx.close();
  } catch {
    // Ignore browser audio restrictions.
  }
}

async function _ensureStaffDesktopPermission() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'granted') {
    state._staffDesktopNotifEnabled = true;
    return;
  }
  if (Notification.permission !== 'default') return;

  try {
    const permission = await Notification.requestPermission();
    state._staffDesktopNotifEnabled = permission === 'granted';
  } catch {
    state._staffDesktopNotifEnabled = false;
  }
}

function _showStaffDesktopNotification(event) {
  if (!document.hidden) return;
  if (!state._staffDesktopNotifEnabled) return;
  if (!('Notification' in window)) return;
  if (Notification.permission !== 'granted') return;

  new Notification(event.title, {
    body: event.message,
    tag: `staff-${event.kind}-${event.order_id}`,
  });
}

function _renderStaffOrders(orders, listEl) {
  listEl.innerHTML = '';

  if (!orders.length) {
    listEl.innerHTML = '<p style="color:#888;padding:16px">Bạn chưa được phân công bàn nào.</p>';
    return;
  }

  const waiting = orders.filter(o => o.status === 'chờ thanh toán').length;
  const active = orders.filter(o => o.status === 'đang xử lý').length;
  const done = orders.filter(o => o.status === 'hoàn tất').length;
  const paid = orders.filter(o => o.status === 'đã thanh toán').length;
  const cancelled = orders.filter(o => o.status === 'đã hủy').length;

  const summary = document.createElement('div');
  summary.className = 'card-item';
  summary.style.cssText = 'background:#1f2937;color:#fff;border-color:#1f2937';
  summary.innerHTML = `
    <div style="display:flex;gap:22px;flex-wrap:wrap">
      <div><strong style="font-size:22px">${waiting}</strong><br><small style="color:#facc15">Chờ xác nhận TT</small></div>
      <div><strong style="font-size:22px">${active}</strong><br><small>Đang phục vụ</small></div>
      <div><strong style="font-size:22px">${done}</strong><br><small>Đã xác nhận</small></div>
      <div><strong style="font-size:22px">${paid}</strong><br><small>Đã thanh toán</small></div>
      <div><strong style="font-size:22px">${cancelled}</strong><br><small style="color:#dc2626">Đã hủy</small></div>
    </div>
  `;
  listEl.appendChild(summary);

  const grouped = {};
  orders.forEach(order => {
    if (!grouped[order.table_id]) grouped[order.table_id] = [];
    grouped[order.table_id].push(order);
  });

  const tableGroups = Object.keys(grouped)
    .sort((a, b) => String(a).localeCompare(String(b), 'vi', { numeric: true }))
    .map(tableId => {
      const ordersByTable = grouped[tableId].sort(_sortByStatusThenTime);
      const openOrders = ordersByTable.filter(o => STAFF_OPEN_STATUSES.includes(o.status));
      const closedOrders = ordersByTable.filter(o => STAFF_CLOSED_STATUSES.includes(o.status)).sort(_sortByTimeDesc);
      return {
        tableId,
        openOrders,
        closedOrders,
      };
    });

  const activeTables = tableGroups
    .filter(group => group.openOrders.length > 0)
    .sort((a, b) => {
      const firstA = a.openOrders[0];
      const firstB = b.openOrders[0];
      const prio = _sortByStatusThenTime(firstA, firstB);
      if (prio !== 0) return prio;
      return String(a.tableId).localeCompare(String(b.tableId), 'vi', { numeric: true });
    });

  const historyOnlyTables = tableGroups.filter(group => group.openOrders.length === 0);

  if (activeTables.length) {
    listEl.appendChild(_buildStaffSectionHeading('Đơn đang cần xử lý'));
    activeTables.forEach(group => {
      const section = document.createElement('div');
      section.className = 'staff-table-section';
      section.innerHTML = `
        <div class="staff-table-title">
          <div>Bàn ${group.tableId}</div>
          <small>${group.openOrders.length} đơn đang hoạt động</small>
        </div>
      `;

      group.openOrders.forEach(order => {
        section.appendChild(_buildStaffOrderCard(order, { historyMode: false }));
      });

      if (group.closedOrders.length) {
        section.appendChild(_buildStaffTableHistory(group.tableId, group.closedOrders));
      }

      listEl.appendChild(section);
    });
  }

  if (historyOnlyTables.length) {
    listEl.appendChild(_buildStaffSectionHeading('Bàn chỉ còn lịch sử'));
    historyOnlyTables.forEach(group => {
      const section = document.createElement('div');
      section.className = 'staff-table-section';
      section.innerHTML = `
        <div class="staff-table-title">
          <div>Bàn ${group.tableId}</div>
          <small>Không còn đơn hoạt động</small>
        </div>
      `;
      section.appendChild(_buildStaffTableHistory(group.tableId, group.closedOrders, true));
      listEl.appendChild(section);
    });
  }
}

function _buildStaffSectionHeading(text) {
  const heading = document.createElement('div');
  heading.className = 'staff-section-heading';
  heading.textContent = text;
  return heading;
}

function _buildStaffTableHistory(tableId, closedOrders, expandByDefault = false) {
  const paidCount = closedOrders.filter(o => o.status === 'đã thanh toán').length;
  const cancelledCount = closedOrders.filter(o => o.status === 'đã hủy').length;
  const preview = closedOrders.slice(0, 5);

  const wrap = document.createElement('details');
  wrap.className = 'staff-history-wrap';
  const savedExpanded = state._staffHistoryExpanded[tableId];
  const shouldOpen = savedExpanded !== undefined ? savedExpanded : expandByDefault;
  if (shouldOpen) wrap.setAttribute('open', '');
  wrap.addEventListener('toggle', () => {
    state._staffHistoryExpanded[tableId] = wrap.open;
  });

  wrap.innerHTML = `
    <summary>
      Lịch sử gần đây (${closedOrders.length} phiên) ·
      ${paidCount} đã thanh toán · ${cancelledCount} đã hủy
    </summary>
  `;

  preview.forEach(order => {
    wrap.appendChild(_buildStaffOrderCard(order, { historyMode: true }));
  });

  if (closedOrders.length > preview.length) {
    const more = document.createElement('div');
    more.className = 'staff-history-note';
    more.textContent = `Đang hiển thị ${preview.length}/${closedOrders.length} phiên gần nhất`;
    wrap.appendChild(more);
  }

  return wrap;
}

function _buildStaffOrderCard(order, options = {}) {
  const historyMode = options.historyMode === true;
  const card = document.createElement('div');
  card.className = 'staff-order-card';
  if (order.status === 'chờ thanh toán') {
    card.classList.add('staff-order-card-highlight');
  }
  if (historyMode) {
    card.classList.add('staff-order-card-muted');
  }

  const resTime = new Date(order.reservation_time);
  const endTime = new Date(order.estimated_end);
  const totalText = order.total != null ? `${order.total.toLocaleString('vi-VN')}đ` : 'Chưa có món';
  const depositText = order.deposit_paid > 0 ? ` | Cọc: ${order.deposit_paid.toLocaleString('vi-VN')}đ` : '';

  const actions = [];
  actions.push(`<button onclick="openStaffOrderDetail('${order.order_id}')">Chi tiết món</button>`);
  if (!historyMode && order.can_add_items) {
    actions.push(`<button onclick="openStaffAddItems('${order.order_id}')">Thêm món hộ khách</button>`);
  }
  if (!historyMode && order.can_confirm_payment) {
    actions.push(`<button onclick="staffConfirmPayment('${order.order_id}')" class="btn-pay">Xác nhận thanh toán</button>`);
  }
  if (!historyMode && order.can_cancel) {
    actions.push(`<button onclick="staffCancelOrder('${order.order_id}')" class="btn-danger">Hủy đơn chưa cọc</button>`);
  }

  card.innerHTML = `
    <div class="staff-order-head">
      <div>
        <strong>${order.order_id}</strong>
        <div class="meta">👤 ${order.customer_name}</div>
      </div>
      <div>${badgeHtml(order.status)}</div>
    </div>
    <div class="meta">🕐 ${resTime.toLocaleString('vi-VN')} → ${endTime.toLocaleTimeString('vi-VN')}</div>
    <div class="meta">🍽️ ${order.item_count} món | 💰 ${totalText}${depositText}</div>
    <div class="actions" style="margin-top:10px">${actions.join('')}</div>
  `;
  return card;
}

