
-- =========================================================================
-- ĐỢT 1: Bảng không phụ thuộc bảng nào khác
-- =========================================================================

-- Khách Hàng
CREATE TABLE Customer (
    CustomerID  VARCHAR(50)  PRIMARY KEY,
    FullName    VARCHAR(100) NOT NULL,
    PhoneNumber TEXT         NOT NULL,   -- [FIX 1] TEXT thay VARCHAR(20)
                                         -- Lưu plain text để manager tra cứu liên hệ nhanh
    username    VARCHAR(100) NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL    -- plain seed hoặc SHA-256 salt hash dạng salt:hash
);

-- Nhân Viên
CREATE TABLE Staff (
    StaffID     VARCHAR(50)  PRIMARY KEY,
    FullName    VARCHAR(100) NOT NULL,
    Role_       VARCHAR(100) NOT NULL,   -- 'Phục vụ' | 'Quản lý'
    PhoneNumber TEXT         NOT NULL,   -- [FIX 1] TEXT thay VARCHAR(20) — lưu plain text
    username    VARCHAR(100) NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL    -- plain seed hoặc SHA-256 salt hash dạng salt:hash
);

-- Bàn Ăn
CREATE TABLE Table_ (
    TableID     VARCHAR(50)  PRIMARY KEY,
    Location_   VARCHAR(100) NOT NULL,
    TableStatus VARCHAR(100) NOT NULL,   -- §4.2: chỉ dùng cho hiển thị
                                         -- Availability check thật dùng interval overlap trên Order_
    Capacity    INT          NOT NULL
);

-- Danh Mục Món Ăn
CREATE TABLE Category (
    CategoryID    VARCHAR(50)  PRIMARY KEY,
    Category_name VARCHAR(100) NOT NULL
);


-- =========================================================================
-- ĐỢT 2: Bảng có FK trỏ vào đợt 1
-- =========================================================================

-- Đơn Đặt Hàng
-- §4.1: bỏ OrderDate DATE
--        thêm ReservationTime   — giờ khách muốn đến
--        thêm EstimatedEndTime  — app layer tính = ReservationTime + 150 phút
--        thêm DepositPaid       — cọc 30% nếu pre-order (§2.3)
CREATE TABLE Order_ (
    OrderID          VARCHAR(50)    PRIMARY KEY,
    ReservationTime  TIMESTAMP      NOT NULL,
    EstimatedEndTime TIMESTAMP      NOT NULL,
    OrderStatus      VARCHAR(100)   NOT NULL,    -- 'đang xử lý' | 'hoàn tất' | 'đã thanh toán' | 'đã hủy'
    TotalAmount      DECIMAL(10,2),              -- NULL cho đến khi tất toán
    DepositPaid      DECIMAL(10,2)  NOT NULL DEFAULT 0,
    CustomerID       VARCHAR(50)    NOT NULL REFERENCES Customer(CustomerID) ON DELETE RESTRICT,
    StaffID          VARCHAR(50)    NOT NULL REFERENCES Staff(StaffID)       ON DELETE RESTRICT,
    TableID          VARCHAR(50)    NOT NULL REFERENCES Table_(TableID)      ON DELETE RESTRICT
);

-- Ràng buộc thời gian
ALTER TABLE Order_
    ADD CONSTRAINT chk_order_time_range
    CHECK (EstimatedEndTime > ReservationTime);

-- [FIX 3] §2.2: Mỗi khách tối đa 1 order active tại bất kỳ thời điểm nào
-- Active = OrderStatus NOT IN ('đã thanh toán', 'đã hủy')
-- Partial unique index: chỉ enforce trên các row thoả điều kiện WHERE
-- → DB tự chặn, không phụ thuộc application layer
CREATE UNIQUE INDEX idx_one_active_order_per_customer
    ON Order_ (CustomerID)
    WHERE OrderStatus NOT IN ('đã thanh toán', 'đã hủy');


-- Món Ăn
CREATE TABLE MenuItem (
    MenuItemID          VARCHAR(50)   PRIMARY KEY,
    Food_name           VARCHAR(100)  NOT NULL,
    Price               DECIMAL(10,2) NOT NULL,
    Availability_status VARCHAR(100)  NOT NULL,  -- 'available' | 'unavailable'
    CategoryID          VARCHAR(50)   NOT NULL REFERENCES Category(CategoryID) ON DELETE RESTRICT
);


-- =========================================================================
-- ĐỢT 3: Bảng có FK trỏ vào đợt 2
-- =========================================================================

-- Thanh Toán
-- §4.5: thêm Signature + PaymentType
-- [FIX 2] OrderID không còn UNIQUE một mình
--          Một đơn pre-order tạo 2 bản ghi: ('cọc') + ('hoàn tất')
--          UNIQUE(OrderID, PaymentType) đảm bảo không trùng trong cùng loại
CREATE TABLE Payment (
    PaymentID     VARCHAR(50)   PRIMARY KEY,
    Amount        DECIMAL(10,2) NOT NULL,
    PaymentDate   DATE          NOT NULL,
    PaymentMethod VARCHAR(100)  NOT NULL,        -- 'tiền mặt' | 'thẻ' | 'chuyển khoản'
    PaymentStatus VARCHAR(100)  NOT NULL,        -- 'thành công' | 'thất bại'
    PaymentType   VARCHAR(50)   NOT NULL,        -- §4.5: 'cọc' | 'hoàn tất'
    Signature     TEXT,                          -- §4.5: RSA-2048 signature (NULL nếu chưa ký)
    OrderID       VARCHAR(50)   NOT NULL REFERENCES Order_(OrderID) ON DELETE RESTRICT,
    UNIQUE (OrderID, PaymentType)               -- [FIX 2] thay thế UNIQUE(OrderID) cũ
);

-- Chi Tiết Đơn Hàng
CREATE TABLE OrderDetail (
    OrderID    VARCHAR(50)   NOT NULL REFERENCES Order_(OrderID)     ON DELETE CASCADE,
    MenuItemID VARCHAR(50)   NOT NULL REFERENCES MenuItem(MenuItemID) ON DELETE RESTRICT,
    Quantity   INT           NOT NULL CHECK (Quantity > 0),
    Unit_price DECIMAL(10,2) NOT NULL,
    Subtotal   DECIMAL(10,2) GENERATED ALWAYS AS (Quantity * Unit_price) STORED,
    PRIMARY KEY (OrderID, MenuItemID)
);


-- =========================================================================
-- BẢNG MỚI §4.3: FailedBooking — yêu cầu đặt bàn thất bại
-- =========================================================================
CREATE TABLE FailedBooking (
    FailedID      VARCHAR(50)  PRIMARY KEY,
    CustomerID    VARCHAR(50)  NOT NULL REFERENCES Customer(CustomerID) ON DELETE RESTRICT,
    RequestedTime TIMESTAMP    NOT NULL,
    CreatedAt     TIMESTAMP    NOT NULL DEFAULT NOW(),
    ContactStatus VARCHAR(50)  NOT NULL DEFAULT 'chưa liên hệ',
        -- 'chưa liên hệ' | 'đã liên hệ' | 'đã giải quyết'
    Note          TEXT
);


-- =========================================================================
-- BẢNG MỚI §4.4: AuditLog — accountability
-- =========================================================================
CREATE TABLE AuditLog (
    LogID       VARCHAR(50)  PRIMARY KEY,
    ActorID     VARCHAR(50)  NOT NULL,
    ActorRole   VARCHAR(50)  NOT NULL,           -- 'customer' | 'staff' | 'manager'
    Action      VARCHAR(100) NOT NULL,
        -- 'UPDATE_ORDER_STATUS' | 'RESCHEDULE' | 'CREATE_PAYMENT'
        -- 'CANCEL_ORDER' | 'CONTACT_FAILED_BOOKING' | ...
    TargetTable VARCHAR(50)  NOT NULL,
    TargetID    VARCHAR(50)  NOT NULL,
    OldValue    TEXT,                            -- JSON string, NULL nếu INSERT
    NewValue    TEXT,                            -- JSON string, NULL nếu DELETE
    CreatedAt   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_auditlog_actor   ON AuditLog (ActorID, CreatedAt DESC);
CREATE INDEX idx_auditlog_target  ON AuditLog (TargetTable, TargetID);
CREATE INDEX idx_auditlog_created ON AuditLog (CreatedAt DESC);


