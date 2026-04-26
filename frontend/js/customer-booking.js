// ═══════════════════════════════════════════════════════════
// CUSTOMER — BOOKING TAB
// ═══════════════════════════════════════════════════════════

async function initBookingTab() {
  // Hiện phase-book, ẩn phase-deposit (trường hợp quay lại tab)
  document.getElementById('phase-book').classList.remove('hidden');
  document.getElementById('phase-deposit').classList.add('hidden');
  document.getElementById('booking-msg').classList.add('hidden');

  await loadBookingMenu();

  // Set min datetime = ngay bây giờ
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  const local = new Date(now - offset).toISOString().slice(0, 16);
  document.getElementById('reservation-time').min = local;
}

async function loadBookingMenu() {
  const el = document.getElementById('booking-menu-list');
  try {
    if (!state.menuData) {
      el.innerHTML = '<p style="color:#888">Đang tải menu...</p>';
      state.menuData = await api('GET', '/menu');
    }
    el.innerHTML = '';
    state.bookingCart = {};

    state.menuData.forEach(cat => {
      const sec = document.createElement('div');
      sec.className = 'menu-category';
      sec.innerHTML = `<h3>${cat.category_name}</h3>`;
      cat.items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'menu-item';
        row.innerHTML = `
          <span class="menu-item-name">${item.food_name}</span>
          <span class="menu-item-price">${item.price.toLocaleString('vi-VN')}đ</span>
          <input type="number" min="0" max="99" value="0"
            data-id="${item.menu_item_id}" data-price="${item.price}"
            onchange="updateBookingCart(this)" />
        `;
        sec.appendChild(row);
      });
      el.appendChild(sec);
    });
  } catch (e) {
    el.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function updateBookingCart(input) {
  const id = input.dataset.id;
  const qty = parseInt(input.value) || 0;
  if (qty > 0) state.bookingCart[id] = qty;
  else delete state.bookingCart[id];

  let total = 0;
  document.querySelectorAll('#booking-menu-list input[type=number]').forEach(inp => {
    total += (parseInt(inp.value) || 0) * parseFloat(inp.dataset.price);
  });

  const summary = document.getElementById('booking-summary');
  if (Object.keys(state.bookingCart).length > 0) {
    summary.classList.remove('hidden');
    document.getElementById('booking-total-text').textContent =
      total.toLocaleString('vi-VN') + 'đ';
  } else {
    summary.classList.add('hidden');
  }
}

// ─────────────────────────────────────────────────────────────
// Bước 1: Nhấn "Đặt bàn"
// ─────────────────────────────────────────────────────────────
async function handleBookTable() {
  const timeInput = document.getElementById('reservation-time').value;
  const msgEl = document.getElementById('booking-msg');
  msgEl.classList.add('hidden');

  if (!timeInput) {
    showMsg(msgEl, 'Vui lòng chọn thời gian đặt bàn', true);
    return;
  }

  const resTime = new Date(timeInput);
  if (resTime <= new Date()) {
    showMsg(msgEl, 'Thời gian đặt bàn phải ở tương lai', true);
    return;
  }

  const items = Object.entries(state.bookingCart).map(([menu_item_id, quantity]) => ({
    menu_item_id, quantity,
  }));

  const btn = document.getElementById('btn-book');
  btn.disabled = true;
  btn.textContent = 'Đang xử lý...';

  try {
    // POST /api/reservations — v2 endpoint
    const res = await api('POST', '/reservations', {
      customer_id: state.user.id,
      // Gửi giờ local trực tiếp — KHÔNG dùng toISOString() vì nó convert sang UTC
      reservation_time: timeInput.length === 16 ? timeInput + ':00' : timeInput,
      items,
    });

    if (!res.success) {
      // Hết bàn hoặc hết nhân viên — server đã ghi FailedBooking
      showMsg(
        msgEl,
        `😔 ${res.reason}\n` +
        `Mã yêu cầu: ${res.failed_id} — chúng tôi sẽ liên hệ bạn sớm nhất.`,
        false,
      );
      return;
    }

    if (res.deposit_required) {
      // Có gọi món trước → cần đặt cọc 30%
      state.pendingReservation = res;
      document.getElementById('deposit-amount-text').textContent =
        res.deposit_amount.toLocaleString('vi-VN') + 'đ';
      document.getElementById('deposit-order-id').textContent = res.order_id;
      document.getElementById('deposit-table-id').textContent = res.table_assigned;
      document.getElementById('deposit-msg').classList.add('hidden');

      // Chuyển sang phase 2
      document.getElementById('phase-book').classList.add('hidden');
      document.getElementById('phase-deposit').classList.remove('hidden');

    } else {
      // Không gọi món trước → đặt bàn thành công ngay
      showMsg(
        msgEl,
        `✅ Đặt bàn thành công!\n` +
        `Bàn ${res.table_assigned} · Nhân viên ${res.staff_assigned}\n` +
        `Giờ: ${new Date(res.reservation_time).toLocaleString('vi-VN')}`,
        false,
      );
      resetBookingForm();
    }

  } catch (e) {
    showMsg(msgEl, e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = '🗓️ Đặt bàn';
  }
}

// ─────────────────────────────────────────────────────────────
// Bước 2: Nhấn "Thanh toán cọc 30%"
// ─────────────────────────────────────────────────────────────
async function handlePayDeposit() {
  const method = document.getElementById('deposit-method').value;
  const msgEl = document.getElementById('deposit-msg');
  msgEl.classList.add('hidden');

  const res = state.pendingReservation;
  if (!res) return;

  try {
    await api('POST', '/payments', {
      order_id: res.order_id,
      amount: res.deposit_amount,
      method,
      payment_type: 'cọc',
    });

    showMsg(
      msgEl,
      `✅ Đặt cọc thành công! Bàn ${res.table_assigned} đã được xác nhận.\n` +
      `Mã đơn: ${res.order_id}`,
      false,
    );

    // Reset form sau 2 giây
    setTimeout(() => {
      document.getElementById('phase-book').classList.remove('hidden');
      document.getElementById('phase-deposit').classList.add('hidden');
      resetBookingForm();
    }, 2500);

  } catch (e) {
    showMsg(msgEl, e.message, true);
  }
}

function cancelDepositPhase() {
  // Bàn đã được giữ, nhưng deposit chưa trả
  // Khách có thể vào Lịch sử để trả sau
  document.getElementById('phase-book').classList.remove('hidden');
  document.getElementById('phase-deposit').classList.add('hidden');
  resetBookingForm();
  document.getElementById('booking-msg').classList.add('hidden');
}

function resetBookingForm() {
  document.getElementById('reservation-time').value = '';
  document.querySelectorAll('#booking-menu-list input[type=number]').forEach(i => i.value = 0);
  state.bookingCart = {};
  state.pendingReservation = null;
  document.getElementById('booking-summary').classList.add('hidden');
}

