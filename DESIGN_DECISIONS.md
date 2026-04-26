# Tài Liệu Thiết Kế — Hệ Thống Quản Lý Nhà Hàng
> Ghi lại toàn bộ quyết định thiết kế, lý do chọn, và những gì cố ý để ngoài scope.
> Cập nhật lần cuối: sau khi tích hợp security layer + xác định vai trò Manager.

---

## 0. Vai Trò Manager — Định Nghĩa Lại

**Manager = Chủ nhà hàng + Dev hệ thống.**

Không phải nhân viên văn phòng không sành IT. Manager là người:
- Thiết kế và build hệ thống này.
- Hiểu toàn bộ DB schema, business logic, security layer từ trong ra ngoài.
- Trực tiếp quản lý vận hành nhà hàng start-up quy mô nhỏ.
- Là người **duy nhất** nắm giữ RSA Private Key và AES Key.

Hệ quả thiết kế:
```
- Dashboard không cần "dễ dùng cho người không biết IT"
  → Có thể hiển thị raw data, filter phức tạp, audit log chi tiết
- Security thiết kế từ đầu vì manager hiểu rủi ro thật sự
  → Không phải "gắn vào cho có điểm"
- Accountability quan trọng: manager cần biết nhân viên có thao tác sai không
  → Audit Log là yêu cầu nghiệp vụ, không chỉ là yêu cầu môn học
```

---

## 1. Quy Mô Hệ Thống (Cố Định, Không Thay Đổi)

| Tham số | Giá trị | Lý do chọn |
|---|---|---|
| Số bàn vật lý | 8 bàn | Bottleneck tự nhiên — hết bàn trước khi hết nhân viên |
| Số nhân viên Phục vụ | 4 người | Cố định trong DB, không model ca làm |
| MAX bàn/nhân viên | 3 bàn cùng lúc | Giới hạn nghiệp vụ thực tế, enforce ở application layer |
| Thời gian block/đơn | 150 phút | 120 phút dùng bữa + 30 phút buffer dọn dẹp |

**Insight toán học quan trọng:**
```
4 nhân viên × 3 bàn = 12 capacity nhân viên
8 bàn vật lý         =  8 capacity bàn

→ Bàn là bottleneck trước. Bài toán staffing tự nhiên đơn giản hóa.
→ Không cần minimum staffing optimization vì bàn hết trước nhân viên hết.
```

---

## 2. Business Rules (Đã Thống Nhất)

### 2.1 Đặt Bàn

- Khách chọn **ngày và giờ cụ thể** khi tạo đơn — không phải ngày hiện tại lúc tạo record.
- Tạo đơn = đặt bàn + giao nhân viên. **Items có thể rỗng** tại thời điểm này.
- Hệ thống block bàn **150 phút** kể từ `ReservationTime`. Khách không biết con số này.
- Hệ thống **không hỏi khách ngồi bao lâu** — đây là thông số nội bộ.

### 2.2 Giới Hạn Đơn Hàng

- Mỗi khách **tối đa 1 order active** tại bất kỳ thời điểm nào.
- Active = `OrderStatus NOT IN ('đã thanh toán', 'đã hủy')`.
- Muốn đặt lần 2 → phải thanh toán hoặc hủy đơn cũ trước.

### 2.3 Gọi Món

**Ai được thêm món:**
- **Khách hàng**: thêm món khi `OrderStatus = 'đang xử lý'`.
- **Nhân viên phụ trách**: thêm món khi `OrderStatus = 'đang xử lý'`, phải là nhân viên được phân công cho đơn đó (`StaffID` khớp).
- **Manager**: thêm món bất kỳ lúc nào khi `OrderStatus = 'đang xử lý'`.
- Sau khi status chuyển sang `'hoàn tất'`: **không ai được thêm món nữa**.

**Quy tắc deposit:**
- Chỉ áp dụng cho **khách hàng** thêm món trước khi đến (`ReservationTime > now()`).
- Nếu **pre-order trước khi đến**: phải thanh toán **cọc 30%** tổng giá trị tất cả món đã đặt trước.
- Nếu **gọi món tại bàn** (`ReservationTime ≤ now()`): không cần cọc.
- Nhân viên và manager thêm món → **không bao giờ** yêu cầu deposit.

### 2.4 Hủy Đơn

**Ai được hủy và điều kiện:**

| Người hủy | Điều kiện cho phép |
|---|---|
| Staff | Chỉ hủy đơn **chưa cọc** (`DepositPaid = 0`) và đang ở `'đang xử lý'` |
| Manager | Hủy đơn ở `'đang xử lý'` hoặc `'hoàn tất'`, kể cả đã cọc |
| Customer | Không có UI tự hủy — liên hệ manager qua điện thoại |

**Chính sách cọc khi hủy:**
- Hủy khi **chưa cọc**: không phát sinh chi phí, đơn chuyển sang `'đã hủy'`.
- Hủy khi **đã cọc**: cọc **không hoàn lại** — đây là chi phí do khách đặt bàn rồi không đến hoặc hủy muộn.
- Manager ghi chú lý do hủy vào `FailedBooking.Note` nếu có liên quan.

---

### 2.5 Đổi Giờ Đặt Bàn

- Khách **không có UI** để tự đổi giờ.
- Khách gọi điện trực tiếp cho manager theo số điện thoại hiển thị trên hệ thống.
- Manager kiểm tra DB, thống nhất giờ mới với khách, tự sửa trong dashboard.
- Hệ thống chỉ cung cấp endpoint `PATCH` phía manager — không phía khách.
- Reschedule chỉ cho phép khi `OrderStatus = 'đang xử lý'`.
- Khi reschedule: hệ thống re-check interval overlap cho bàn hiện tại với khung giờ mới. Nếu conflict → trả lỗi, manager xử lý thủ công.

### 2.6 Phân Công Nhân Viên

- Assign cho nhân viên có **peak concurrent load thấp nhất** tại thời điểm đặt bàn.
- Nếu tất cả nhân viên đã đạt MAX → trả lỗi `NO_STAFF_AVAILABLE`.
- Khách không chọn nhân viên — hệ thống tự phân công.

### 2.7 Order Status — State Machine

**Ngữ nghĩa trạng thái:**

| Trạng thái | Ý nghĩa | Khách thêm món? | Khách thanh toán? |
|---|---|---|---|
| `đang xử lý` | Đơn đang hoạt động, đang phục vụ | Có | Có (kèm cảnh báo) |
| `hoàn tất` | Nhân viên đã mang đồ ăn ra — **khách vẫn có thể gọi thêm** | Có (revert → `đang xử lý`) | Có (kèm cảnh báo) |
| `đã thanh toán` | Khách xác nhận rời bàn, bill đã đóng (terminal) | Không | — |
| `đã hủy` | Đơn bị hủy (terminal) | Không | — |

**Triết lý phân quyền quyết định "xong bữa":**
- **Khách** = người quyết định khi nào xong → nhấn "Thanh toán" = tín hiệu rời bàn.
- **Staff** mark `'hoàn tất'` = "tôi đã mang hết đồ ra" — không khoá khách khỏi gọi thêm.
- Nếu khách gọi thêm món khi đơn đang `'hoàn tất'` → status tự động revert về `'đang xử lý'`.

**Transition hợp lệ:**

```
đang xử lý ──[staff: đã mang đồ ra]──────────→ hoàn tất
đang xử lý ──[khách/staff/manager: hủy]──────→ đã hủy
đang xử lý ──[khách: thanh toán]─────────────→ đã thanh toán   ← khách bỏ qua 'hoàn tất'
hoàn tất   ──[khách: gọi thêm món]───────────→ đang xử lý      ← revert
hoàn tất   ──[khách: thanh toán]─────────────→ đã thanh toán
hoàn tất   ──[manager: hủy]──────────────────→ đã hủy
đã thanh toán → (terminal)
đã hủy        → (terminal)
```

**Quy tắc phân quyền:**
- `đang xử lý → hoàn tất`: **chỉ staff được phân công** cho đơn đó
- `* → đã hủy`: staff (đơn chưa cọc) hoặc manager (mọi đơn)
- `* → đã thanh toán`: chỉ qua payment endpoint, không patch trực tiếp

---

## 3. Thuật Toán Cốt Lõi

### 3.1 Kiểm Tra Conflict Bàn (Interval Overlap)

**Bàn X bị conflict với slot [new_start, new_end) khi tồn tại đơn nào thỏa:**
```
existing.ReservationTime  < new_end
AND
existing.EstimatedEndTime > new_start
```
Ngược lại: bàn X available → assign được.

### 3.2 Tính Peak Concurrent Load Của Nhân Viên (Sweep Line / Critical Points)

Không đếm tổng số đơn overlap — đếm **đỉnh** tại từng thời điểm thay đổi:

```
Bước 1: Lấy tất cả đơn của staff đó overlap với window [new_start, new_end)
Bước 2: Critical points = {new_start} ∪ {res_time của đơn bắt đầu trong (new_start, new_end)}
Bước 3: Tại mỗi critical point, đếm bao nhiêu đơn đang active
Bước 4: peak = max của tất cả các count đó
Bước 5: Nếu peak + 1 ≤ MAX → staff này eligible
```

**Lý do không dùng COUNT(overlap):** đếm tổng đơn overlap cho kết quả sai khi
các đơn không bắt đầu cùng lúc. Ví dụ A(15:00→17:30), B(15:00→17:30),
C(18:00→20:30) — đơn mới 16:00→18:30 chỉ gặp A+B hoặc C, không bao giờ
gặp cả 3 cùng lúc. COUNT trả về 3 → loại staff oan.

### 3.3 Xử Lý Khi Hết Bàn — Notify Manager, Không Để Hệ Thống Tự Loop

**Quyết định thiết kế**: hệ thống **không tự tìm slot thay thế**.

**Lý do bỏ loop tự động:**
```
Loop N bước × mỗi bước 1 SQL query = tốn tài nguyên không cần thiết.
Kết quả trả về vẫn có thể sai vì:
  - Manager có thể đang giữ slot cho khách VIP chưa đặt
  - Có đơn sắp bị hủy mà hệ thống chưa biết
  - Khách muốn ngày hoàn toàn khác, không phải 30 phút sau
→ Hệ thống không có đủ context để tư vấn thay manager.
```

**Luồng đúng khi khách không đặt được:**
```
Khách chọn giờ → hết bàn
       ↓
Hệ thống INSERT vào bảng FailedBooking
  (CustomerID, giờ muốn đặt, thời điểm xảy ra)
       ↓
Manager dashboard hiển thị alert ngay lập tức
       ↓
Manager = chủ nhà hàng, nắm toàn bộ DB
→ Gọi điện trực tiếp cho khách, tư vấn giờ phù hợp
→ Nếu đồng ý → manager tạo đơn thay cho khách luôn trên dashboard
```

---

## 4. Schema — Thay Đổi So Với Bản Gốc

### 4.1 Bảng `Order_`

| Cột | Cũ | Mới | Lý do |
|---|---|---|---|
| `OrderDate` | `DATE` | Bỏ | Chỉ lưu ngày, mất thông tin giờ |
| `ReservationTime` | Không có | `TIMESTAMP NOT NULL` | Giờ khách muốn đến |
| `EstimatedEndTime` | Không có | `TIMESTAMP NOT NULL` | Tính sẵn = ReservationTime + 150 phút |
| `DepositPaid` | Không có | `DECIMAL(10,2) DEFAULT 0` | Track số tiền cọc đã đặt |

### 4.2 `TableStatus` — Thay Đổi Tư Duy

- **Cũ**: flag tĩnh `'trống'`/`'đang dùng'` — cập nhật mỗi lần tạo/thanh toán đơn.
- **Mới**: availability tính **động từ `Order_`** qua interval check — không phụ thuộc cột tĩnh.
- `TableStatus` vẫn giữ nhưng chỉ để hiển thị cho manager, không dùng để check khi đặt bàn.

### 4.3 Bảng Mới — `FailedBooking`

| Cột | Kiểu | Mục đích |
|---|---|---|
| `FailedID` | `VARCHAR(50) PK` | Mã định danh |
| `CustomerID` | `VARCHAR(50) FK` | Khách nào không đặt được |
| `RequestedTime` | `TIMESTAMP` | Giờ khách muốn đặt |
| `CreatedAt` | `TIMESTAMP DEFAULT NOW()` | Thời điểm xảy ra |
| `ContactStatus` | `VARCHAR(50) DEFAULT 'chưa liên hệ'` | `'chưa liên hệ'` / `'đã liên hệ'` / `'đã giải quyết'` |
| `Note` | `TEXT` | Manager ghi chú sau khi gọi điện |

### 4.4 Bảng Mới — `AuditLog`

| Cột | Kiểu | Mục đích |
|---|---|---|
| `LogID` | `VARCHAR(50) PK` | Mã định danh |
| `ActorID` | `VARCHAR(50)` | Ai thực hiện hành động |
| `ActorRole` | `VARCHAR(50)` | Role lúc thực hiện |
| `Action` | `VARCHAR(100)` | `UPDATE_ORDER_STATUS` / `RESCHEDULE` / `CREATE_PAYMENT` / `CANCEL_ORDER`... |
| `TargetTable` | `VARCHAR(50)` | Bảng nào bị ảnh hưởng |
| `TargetID` | `VARCHAR(50)` | Record nào |
| `OldValue` | `TEXT` | Giá trị trước (JSON string) |
| `NewValue` | `TEXT` | Giá trị sau (JSON string) |
| `CreatedAt` | `TIMESTAMP DEFAULT NOW()` | Thời điểm xảy ra |

### 4.5 Bảng `Payment` — Thêm Cột Chữ Ký Số

| Cột | Kiểu | Mục đích |
|---|---|---|
| `Signature` | `TEXT` | RSA Digital Signature của hoá đơn |
| `PaymentType` | `VARCHAR(50)` | `'cọc'` hoặc `'hoàn tất'` |

---

## 5. Security Layer (Tích Hợp Môn An Toàn Thông Tin)

Yêu cầu thầy: implement đủ 4 kỹ thuật — Symmetric, Asymmetric, Hash, Digital Signature.
Quyết định: **implement thật vào hệ thống**, không làm demo tách riêng.
Lý do: manager = dev, hiểu rủi ro thật, mỗi kỹ thuật có lý do nghiệp vụ rõ ràng.

### 5.1 Hash — bcrypt cho Password (SHA-256 based)

**Vấn đề nghiệp vụ:**
```
DB bị leak → attacker đọc được password '123456' của khách
→ đăng nhập tài khoản khách → xem lịch sử, tạo đơn giả mạo
```
**Giải pháp:** `'123456'` → `bcrypt(salt)` → hash không thể reverse.
Salt ngẫu nhiên mỗi lần → cùng password ra hash khác nhau.
**Áp dụng:** `routers/auth.py` — hash khi register, verify khi login.

---

### 5.2 Symmetric — AES-256-GCM cho Dữ Liệu Nhạy Cảm

**Vấn đề nghiệp vụ:**
```
DB chứa số điện thoại khách hàng.
Nhân viên truy cập DB trực tiếp hoặc DB bị leak
→ lộ toàn bộ thông tin liên lạc của khách.
```
**Giải pháp:** `PhoneNumber` encrypt bằng AES-256-GCM trước khi INSERT.
AES key lưu trong `.env` — không bao giờ lưu trong DB.
**Áp dụng:** `utils/crypto.py` — 2 hàm `encrypt_field()` / `decrypt_field()`.

---

### 5.3 Asymmetric — RSA-2048 bảo vệ AES Key (Hybrid Encryption)

**Vấn đề nghiệp vụ:**
```
AES key trong .env bị lộ → toàn bộ data decrypt được ngay.
```
**Giải pháp — Hybrid Encryption (đúng cách TLS/HTTPS làm):**
```
AES key → encrypt bằng RSA Public Key của owner → lưu file encrypted
Khi server cần dùng:
  → Đọc encrypted AES key
  → Decrypt bằng RSA Private Key (chỉ owner giữ, không rời máy owner)
  → Dùng AES key vừa giải mã để encrypt/decrypt data
```
**Áp dụng:** `utils/crypto.py` — setup 1 lần khi khởi động server.

---

### 5.4 Digital Signature — RSA ký Hoá Đơn Thanh Toán

**Vấn đề nghiệp vụ:**
```
Khách giả mạo hoá đơn để khiếu nại.
Nhân viên sửa số tiền sau khi xuất hoá đơn.
```
**Giải pháp:**
```
Khi tạo Payment:
  1. Serialize hoá đơn → JSON: {order_id, amount, items, date}
  2. Hash bằng SHA-256
  3. Ký hash bằng RSA Private Key của owner
  4. Lưu Signature vào Payment.Signature

Verify qua endpoint GET /payments/{id}/verify:
  → Re-serialize → verify bằng RSA Public Key
  → Hợp lệ: hoá đơn chưa bị tamper, do hệ thống xuất thật
```
Non-repudiation: nhà hàng không thể chối "tôi không xuất hoá đơn này."
**Áp dụng:** `services/payment_service.py` + endpoint verify mới.

---

### 5.5 JWT — Authentication & Phân Quyền 3 Role

**Vấn đề nghiệp vụ:**
```
Hiện tại không có gì ngăn customer gọi /api/manager/orders.
Backend không verify caller là ai.
```
**Giải pháp:** Login → JWT token → mọi request gửi kèm token trong header.
Server verify chữ ký + đọc role từ payload.
Token hết hạn sau 8 giờ.

**Phân quyền:**
```
customer → /api/reservations, /api/orders/{id}/items, /api/payments
staff    → /api/staff/*, /api/orders/{id}/status
manager  → tất cả + /api/manager/*
```

---

### 5.6 Audit Log — Accountability cho Owner

**Vấn đề nghiệp vụ:**
```
Nhân viên hủy đơn → khách khiếu nại → ai chịu trách nhiệm?
Manager sửa giờ → khách nói không đồng ý → có bằng chứng không?
```
**Giải pháp:** Mọi thao tác thay đổi dữ liệu quan trọng ghi vào `AuditLog`.
Actions cần log: `UPDATE_ORDER_STATUS`, `RESCHEDULE`, `CREATE_PAYMENT`,
`CANCEL_ORDER`, `CONTACT_FAILED_BOOKING`.

---

## 6. Endpoints Cần Thêm / Sửa

| Method | Path | Ai dùng | Mục đích |
|---|---|---|---|
| `POST` | `/api/auth/login` | Tất cả | Login, trả JWT |
| `POST` | `/api/auth/register` | Khách | Đăng ký |
| `POST` | `/api/reservations` | Khách | Tạo đặt bàn |
| `POST` | `/api/orders/{id}/items` | Khách | Thêm món vào đơn đã có |
| `POST` | `/api/payments` | Khách | Thanh toán (`'cọc'` hoặc `'hoàn tất'`) |
| `GET` | `/api/payments/{id}/verify` | Tất cả | Verify chữ ký số hoá đơn |
| `POST` | `/api/staff/orders/{id}/items` | Staff | Staff thêm món tại bàn cho khách (không cần deposit) |
| `GET` | `/api/manager/failed-bookings` | Manager | Danh sách khách chưa đặt được bàn |
| `PATCH` | `/api/manager/failed-bookings/{id}` | Manager | Cập nhật trạng thái liên hệ |
| `POST` | `/api/manager/reservations` | Manager | Tạo đơn thay khách sau tư vấn (không cần deposit) |
| `PATCH` | `/api/manager/orders/{id}/reschedule` | Manager | Đổi giờ đặt bàn (re-check interval) |
| `PATCH` | `/api/manager/orders/{id}/cancel` | Manager | Hủy đơn, kể cả đơn đã cọc |
| `GET` | `/api/manager/audit-log` | Manager | Xem toàn bộ audit trail |

---

## 7. Scope Chính Thức

### ✅ Trong Scope — Sẽ Implement

**Nghiệp vụ:**
- Đặt bàn theo giờ cụ thể với interval conflict check
- Assign nhân viên theo peak concurrent load (sweep line)
- Khi hết bàn → ghi `FailedBooking` → manager thấy alert trên dashboard
- Manager liên hệ khách, tư vấn, tạo đơn thay nếu cần
- 1 khách chỉ 1 order active
- Gọi món khi `OrderStatus = 'đang xử lý'` (khách hoặc nhân viên phụ trách)
- Cọc 30% chỉ khi **khách** pre-order trước giờ đặt bàn
- Manager reschedule qua endpoint riêng (re-check interval)
- Manager/staff hủy đơn theo phân quyền (staff: chỉ đơn chưa cọc; manager: mọi đơn)
- Manager tạo đơn thay khách qua endpoint riêng (không cần deposit)

**Security (đủ 4 kỹ thuật môn học + 2 bổ sung):**
- Hash: bcrypt cho password
- Symmetric: AES-256-GCM encrypt số điện thoại khách trong DB
- Asymmetric: RSA-2048 hybrid bảo vệ AES key
- Digital Signature: RSA ký hoá đơn + endpoint verify
- JWT: authentication + phân quyền 3 role
- Audit Log: ghi nhận mọi thao tác quan trọng

### ⚠️ Đã Nhận Diện, Cố Ý Không Xử Lý

| Vấn đề | Lý do không làm |
|---|---|
| Overstay thực tế (khách ngồi quá 150 phút) | Buffer 30 phút hấp thụ. Còn lại nhân viên xử lý offline. |
| Overbooking có kiểm soát | Phức tạp, không cần thiết cho 8 bàn. |
| Shift scheduling nhân viên | Ca làm không model — 4 nhân viên cố định. |
| Minimum staffing optimization | Bàn là bottleneck trước nhân viên. |
| Fairness metric giữa nhân viên | Cần lý thuyết thống kê, ngoài level hiện tại. |
| Capacity bếp / công suất nấu | 8 bàn không đủ quy mô để bếp là bottleneck. |
| Ca overlap / handover | Không model ca — không có vấn đề handover. |
| Rebalance khi nhân viên nghỉ đột xuất | Static assignment — manager xử lý thủ công. |
| Inventory nguyên liệu | Hoàn toàn ngoài scope hệ thống đặt bàn. |
| HTTPS/TLS | Cấu hình infrastructure, không phải application code. |
| 2FA | Quá phức tạp, không cần thiết cho quy mô này. |
| Encryption at rest toàn bộ DB | Overkill — chỉ encrypt field nhạy cảm là đủ. |

---

## 8. Nền Toán Đã Dùng

| Công cụ | Dùng ở đâu | Level cần hiểu |
|---|---|---|
| Interval overlap check | Conflict bàn | Cần hiểu bản chất |
| Sweep line / Critical points | Peak load nhân viên | Cần hiểu bản chất |
| Ceiling division ⌈a/b⌉ | Tính minimum staff từ peak | Chỉ cần nhớ công thức |
| Greedy (least load first) | Assign nhân viên | Cần hiểu tại sao greedy đúng ở đây |
| Interval Graph (lý thuyết nền) | Giải thích tại sao greedy optimal | Biết tên, không cần đào sâu |
| SHA-256 (one-way hash) | Password hashing, Digital Signature | Cần hiểu bản chất one-way |
| AES-256-GCM (block cipher) | Encrypt data nhạy cảm | Nhớ: symmetric, cùng key encrypt/decrypt |
| RSA-2048 (asymmetric) | Bảo vệ AES key + Digital Signature | Cần hiểu public/private key pair |
| JWT HS256 | Authentication | Nhớ: stateless token có expiry và chữ ký |

---

## 9. Thứ Tự Implement

```
Bước 1: Sửa schema SQL
         → Order_: bỏ OrderDate, thêm ReservationTime + EstimatedEndTime + DepositPaid
         → Payment: thêm Signature + PaymentType
         → Tạo mới: FailedBooking, AuditLog

Bước 2: Security foundation
         → utils/crypto.py  : bcrypt, AES-256-GCM, RSA hybrid setup
         → utils/jwt.py     : tạo + verify JWT token
         → utils/audit.py   : helper ghi AuditLog

Bước 3: Viết lại auth.py
         → Hash password khi register (bcrypt)
         → Verify bcrypt khi login
         → Trả JWT token thay vì user object

Bước 4: Viết lại order_service.py
         → create_reservation(): interval check bàn + peak check nhân viên
         → add_items_to_order(): thêm món vào đơn đã có
         → find_available_table(): interval overlap SQL
         → find_available_staff(): sweep line critical points

Bước 5: Viết lại payment_service.py
         → RSA Digital Signature khi tạo payment
         → Endpoint verify signature

Bước 6: Sửa tất cả routers
         → JWT middleware Depends() vào mọi endpoint
         → Phân quyền đúng theo role
         → Ghi AuditLog tại các thao tác quan trọng

Bước 7: Thêm manager endpoints mới
         → failed-bookings CRUD
         → audit-log viewer
         → reschedule

Bước 8: Sửa frontend
         → Datetime picker khi đặt bàn
         → Luồng 2 bước: đặt bàn → gọi món
         → Hiển thị số điện thoại manager khi hết bàn
         → Tab Audit Log trong dashboard manager
```
