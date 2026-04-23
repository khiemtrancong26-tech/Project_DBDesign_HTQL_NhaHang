-- =========================================================================
-- DEMO DATA — Dữ liệu nền khởi động
-- Bao gồm: Category, MenuItem, Table_, Staff, Customer
-- Không bao gồm: Order_, OrderDetail, Payment
-- → Nhóm tự thao tác qua giao diện từ đầu
-- =========================================================================

-- =========================================================================
-- 1. CATEGORY (4 rows)
-- =========================================================================
INSERT INTO Category (CategoryID, Category_name) VALUES
  ('CAT001', 'Khai vị'),
  ('CAT002', 'Món chính'),
  ('CAT003', 'Tráng miệng'),
  ('CAT004', 'Đồ uống');

-- =========================================================================
-- 2. MENU ITEM (20 rows — 5 món/category)
-- =========================================================================
INSERT INTO MenuItem (MenuItemID, Food_name, Price, Availability_status, CategoryID) VALUES
  -- Khai vị
  ('M001', 'Gỏi cuốn tôm thịt',     45000.00, 'available', 'CAT001'),
  ('M002', 'Chả giò chiên',         50000.00, 'available', 'CAT001'),
  ('M003', 'Súp bắp cua',           55000.00, 'available', 'CAT001'),
  ('M004', 'Salad trứng cá',        65000.00, 'available', 'CAT001'),
  ('M005', 'Dim sum hấp (4 viên)',  60000.00, 'available', 'CAT001'),
  -- Món chính
  ('M006', 'Bò lúc lắc',            185000.00, 'available', 'CAT002'),
  ('M007', 'Cá hồi áp chảo',        220000.00, 'available', 'CAT002'),
  ('M008', 'Gà nướng mật ong',      165000.00, 'available', 'CAT002'),
  ('M009', 'Mực xào sa tế',         145000.00, 'available', 'CAT002'),
  ('M010', 'Sườn nướng BBQ',        195000.00, 'available', 'CAT002'),
  -- Tráng miệng
  ('M011', 'Bánh flan caramel',     45000.00, 'available', 'CAT003'),
  ('M012', 'Chè thập cẩm',          40000.00, 'available', 'CAT003'),
  ('M013', 'Kem 3 vị',              55000.00, 'available', 'CAT003'),
  ('M014', 'Mousse chanh dây',      60000.00, 'available', 'CAT003'),
  ('M015', 'Bánh tiramisu',         70000.00, 'available', 'CAT003'),
  -- Đồ uống
  ('M016', 'Nước ép cam tươi',      45000.00, 'available', 'CAT004'),
  ('M017', 'Sinh tố bơ',            55000.00, 'available', 'CAT004'),
  ('M018', 'Trà đào cam sả',        50000.00, 'available', 'CAT004'),
  ('M019', 'Cà phê sữa đá',         35000.00, 'available', 'CAT004'),
  ('M020', 'Bia Heineken',          40000.00, 'available', 'CAT004');

-- =========================================================================
-- 3. TABLE_ (12 rows — tất cả trống)
-- =========================================================================
INSERT INTO Table_ (TableID, Location_, TableStatus, Capacity) VALUES
  ('T01', 'Khu trong',  'trống', 4),
  ('T02', 'Khu trong',  'trống', 4),
  ('T03', 'Khu trong',  'trống', 4),
  ('T04', 'Khu trong',  'trống', 4),
  ('T05', 'Khu trong',  'trống', 6),
  ('T06', 'Khu trong',  'trống', 6),
  ('T07', 'Khu trong',  'trống', 6),
  ('T08', 'Khu ngoài',  'trống', 6),
  ('T09', 'Khu ngoài',  'trống', 6),
  ('T10', 'Phòng VIP',  'trống', 8),
  ('T11', 'Khu trong',  'trống', 6),
  ('T12', 'Khu ngoài',  'trống', 6);

-- =========================================================================
-- 4. STAFF (6 rows — chỉ Phục vụ + Quản lý)
--
--    Phục vụ : tham gia phân công đơn
--    Quản lý : login xem dashboard
--
--    Password chung Phục vụ : staff123
--    Password Quản lý       : manager123
-- =========================================================================
INSERT INTO Staff (StaffID, FullName, Role_, PhoneNumber, username, password) VALUES
  ('S000001', 'Nguyễn Văn Minh', 'Phục vụ', '0901111001', 'staff_s001',   'staff123'),
  ('S000002', 'Trần Thị Lan',    'Phục vụ', '0901111002', 'staff_s002',   'staff123'),
  ('S000003', 'Lê Quốc Hùng',    'Phục vụ', '0901111003', 'staff_s003',   'staff123'),
  ('S000004', 'Phạm Ngọc Bảo',   'Phục vụ', '0901111004', 'staff_s004',   'staff123'),
  ('S000005', 'Ngô Thị Mai',     'Quản lý', '0901111009', 'manager_s005', 'manager123'),
  ('S000006', 'Trịnh Văn Dũng',  'Phục vụ', '0901111010', 'staff_s006',   'staff123');

-- =========================================================================
-- 5. CUSTOMER (10 rows — password chung: 123456)
-- =========================================================================
INSERT INTO Customer (CustomerID, FullName, PhoneNumber, username, password) VALUES
  ('C000001', 'Nguyễn Văn An',   '0912001001', 'van',     '123456'),
  ('C000002', 'Trần Thị Bích',   '0912001002', 'tbich',   '123456'),
  ('C000003', 'Lê Minh Châu',    '0912001003', 'mchau',   '123456'),
  ('C000004', 'Phạm Quốc Duy',   '0912001004', 'qduy',    '123456'),
  ('C000005', 'Hoàng Thị Thư',   '0912001005', 'tthư',    '123456');



  
-- Xóa data (giữ nguyên bảng)
TRUNCATE TABLE Payment, OrderDetail, Order_, MenuItem, Category, Table_, Staff, Customer RESTART IDENTITY CASCADE;


SELECT * FROM Payment;
SELECT * FROM OrderDetail;
SELECT * FROM Order_;
SELECT * FROM MenuItem;
SELECT * FROM Category;
SELECT * FROM Table_;
SELECT * FROM Staff;
SELECT * FROM Customer;

DELETE FROM Customer WHERE CustomerID = 'C000006';