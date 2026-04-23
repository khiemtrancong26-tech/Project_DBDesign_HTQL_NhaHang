-- =========================================================================
-- KHỞI TẠO CÁC BẢNG DANH MỤC (Không phụ thuộc vào bảng khác)
-- =========================================================================

-- Khách Hàng
CREATE TABLE Customer (
    CustomerID VARCHAR(50) PRIMARY KEY,
    FullName VARCHAR(100) NOT NULL,
    PhoneNumber VARCHAR(20) NOT NULL,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL
);

-- Nhân Viên
CREATE TABLE Staff (
    StaffID VARCHAR(50) PRIMARY KEY,
    FullName VARCHAR(100) NOT NULL,
    Role_ VARCHAR(100) NOT NULL,
    PhoneNumber VARCHAR(20) NOT NULL,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL
);

-- Bàn Ăn
CREATE TABLE Table_ (
    TableID VARCHAR(50) PRIMARY KEY,
    Location_ VARCHAR(100) NOT NULL,
    TableStatus VARCHAR(100) NOT NULL,
    Capacity INT NOT NULL
);

-- Danh Mục Món Ăn
CREATE TABLE Category (
    CategoryID VARCHAR(50) PRIMARY KEY,
    Category_name VARCHAR(100) NOT NULL
);

-- =========================================================================
-- KHỞI TẠO CÁC BẢNG FK trỏ vào đợt 1
-- =========================================================================

-- Đơn Đặt Hàng
CREATE TABLE Order_ (
    OrderID VARCHAR(50) PRIMARY KEY,
    OrderDate DATE NOT NULL,
    OrderStatus VARCHAR(100) NOT NULL,
    TotalAmount DECIMAL(10,2),
    CustomerID VARCHAR(50) NOT NULL REFERENCES Customer(CustomerID) ON DELETE RESTRICT,
    StaffID VARCHAR(50) NOT NULL REFERENCES Staff(StaffID) ON DELETE RESTRICT,
    TableID VARCHAR(50) NOT NULL REFERENCES Table_(TableID) ON DELETE RESTRICT
);

-- Món Ăn
CREATE TABLE MenuItem (
    MenuItemID VARCHAR(50) PRIMARY KEY,
    Food_name VARCHAR(100) NOT NULL,
    Price DECIMAL(10,2) NOT NULL,
    Availability_status VARCHAR(100) NOT NULL,
    CategoryID VARCHAR(50) NOT NULL REFERENCES Category(CategoryID) ON DELETE RESTRICT
);

-- =========================================================================
-- KHỞI TẠO CÁC BẢNG FK trỏ vào đợt 2
-- =========================================================================

-- Thanh Toán
CREATE TABLE Payment (
    PaymentID VARCHAR(50) PRIMARY KEY,
    Amount DECIMAL(10,2) NOT NULL,
    PaymentDate DATE NOT NULL,
    PaymentMethod VARCHAR(100) NOT NULL,
    PaymentStatus VARCHAR(100) NOT NULL,
    OrderID VARCHAR(50) NOT NULL UNIQUE REFERENCES Order_(OrderID) ON DELETE RESTRICT
);

-- Chi Tiết Đơn Hàng
CREATE TABLE OrderDetail (
    OrderID VARCHAR(50) NOT NULL REFERENCES Order_(OrderID) ON DELETE CASCADE,
    MenuItemID VARCHAR(50) NOT NULL REFERENCES MenuItem(MenuItemID) ON DELETE RESTRICT,
    Quantity INT NOT NULL,
    Unit_price DECIMAL(10,2) NOT NULL,
    Subtotal DECIMAL(10,2),
    PRIMARY KEY (OrderID, MenuItemID)
);

