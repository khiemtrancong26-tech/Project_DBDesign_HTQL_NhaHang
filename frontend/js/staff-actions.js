async function openStaffOrderDetail(orderId) {
  const modal = document.getElementById('modal-staff-order-detail');
  const bodyEl = document.getElementById('staff-order-detail-body');

  modal.classList.remove('hidden');
  bodyEl.innerHTML = '<p>Đang tải chi tiết...</p>';

  try {
    const data = await api('GET', `/staff/${state.user.id}/orders/${orderId}/details`);
    const order = data.order;
    const items = data.items || [];

    const itemRows = items.length
      ? `
          <table>
            <thead>
              <tr><th>Món</th><th>SL</th><th>Đơn giá</th><th>Thành tiền</th></tr>
            </thead>
            <tbody>
              ${items.map(item => `
                <tr>
                  <td>${item.food_name}</td>
                  <td>${item.quantity}</td>
                  <td>${item.unit_price.toLocaleString('vi-VN')}đ</td>
                  <td>${item.subtotal.toLocaleString('vi-VN')}đ</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `
      : '<p>Đơn này chưa có món.</p>';

    bodyEl.innerHTML = `
      <div class="meta" style="margin-bottom:8px">
        <strong>${order.order_id}</strong> | Bàn ${order.table_id} | ${badgeHtml(order.status)}
      </div>
      <div class="meta" style="margin-bottom:12px">
        👤 ${order.customer_name} | 🍽️ ${order.item_count} món | 💰
        ${order.total != null ? order.total.toLocaleString('vi-VN') + 'đ' : 'Chưa có món'}
      </div>
      ${itemRows}
    `;
  } catch (e) {
    bodyEl.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function openStaffAddItems(orderId) {
  state.staffAddOrderId = orderId;
  state.staffAddCart = {};

  const modal = document.getElementById('modal-staff-add-items');
  const listEl = document.getElementById('staff-add-menu-list');
  const summary = document.getElementById('staff-add-summary');
  const msgEl = document.getElementById('staff-add-msg');
  const orderEl = document.getElementById('staff-add-order-id');

  orderEl.textContent = orderId;
  msgEl.classList.add('hidden');
  summary.classList.add('hidden');
  modal.classList.remove('hidden');
  listEl.innerHTML = '<p>Đang tải menu...</p>';

  try {
    if (!state.menuData) state.menuData = await api('GET', '/menu');
    listEl.innerHTML = '';

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
            onchange="updateStaffAddCart(this)" />
        `;
        sec.appendChild(row);
      });
      listEl.appendChild(sec);
    });
  } catch (e) {
    listEl.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function updateStaffAddCart(input) {
  const id = input.dataset.id;
  const qty = parseInt(input.value, 10) || 0;
  if (qty > 0) state.staffAddCart[id] = qty;
  else delete state.staffAddCart[id];

  let total = 0;
  document.querySelectorAll('#staff-add-menu-list input[type=number]').forEach(inp => {
    total += (parseInt(inp.value, 10) || 0) * parseFloat(inp.dataset.price);
  });

  const summary = document.getElementById('staff-add-summary');
  const totalEl = document.getElementById('staff-add-total-text');
  if (Object.keys(state.staffAddCart).length) {
    summary.classList.remove('hidden');
    totalEl.textContent = `${total.toLocaleString('vi-VN')}đ`;
  } else {
    summary.classList.add('hidden');
  }
}

async function submitStaffAddItems() {
  const msgEl = document.getElementById('staff-add-msg');
  msgEl.classList.add('hidden');

  const items = Object.entries(state.staffAddCart).map(([menu_item_id, quantity]) => ({
    menu_item_id,
    quantity,
  }));

  if (!items.length) {
    showMsg(msgEl, 'Chưa chọn món nào để thêm.', true);
    return;
  }

  try {
    await api('POST', `/staff/orders/${state.staffAddOrderId}/items`, {
      staff_id: state.user.id,
      items,
    });
    closeModal('modal-staff-add-items');
    await loadStaffOrders();
  } catch (e) {
    showMsg(msgEl, e.message, true);
  }
}

async function staffConfirmPayment(orderId) {
  if (!confirm(`Xác nhận cho phép khách thanh toán đơn ${orderId}?\nHãy kiểm tra hóa đơn trước khi xác nhận.`)) return;
  try {
    await api('POST', `/staff/orders/${orderId}/confirm-payment`, { staff_id: state.user.id });
    await loadStaffOrders();
  } catch (e) {
    alert(e.message);
  }
}

async function staffCancelOrder(orderId) {
  if (!confirm(`Xác nhận hủy đơn ${orderId}?\nChỉ dùng khi khách chưa đặt cọc.`)) return;
  try {
    await api('PATCH', `/orders/${orderId}/status`, {
      staff_id: state.user.id,
      status: 'đã hủy',
    });
    await loadStaffOrders();
  } catch (e) {
    alert(e.message);
  }
}

