-- ============================================================================
-- PROJECT: Retail Sales & Inventory Data Warehouse
-- LAYER:   Staging (stg_*), Dimensions (dim_*), Facts (fact_*)
-- ============================================================================

CREATE DATABASE IF NOT EXISTS retail_dw
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE retail_dw;

-- ----------------------------------------------------------------------------
-- 1. STAGING LAYER (Lưu trữ bản sao thô đã lọc cho STR-1006 để đối soát)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS stg_sales;
CREATE TABLE stg_sales (
    stg_sales_id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    transaction_date       VARCHAR(20),
    sales_type             VARCHAR(50),
    is_return              INT,
    reason_of_return       VARCHAR(150),
    supplier               VARCHAR(100),
    product_no             VARCHAR(50),
    product_description    VARCHAR(255),
    product_division       VARCHAR(100),
    product_category       VARCHAR(100),
    product_subcategory    VARCHAR(100),
    product_segment        VARCHAR(100),
    store                  VARCHAR(30),
    sales_channel          VARCHAR(50),
    qty_sold               DECIMAL(14, 4),
    sales_amount           DECIMAL(14, 4),
    cogs                   DECIMAL(14, 4),
    number_of_transactions INT,
    loaded_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

DROP TABLE IF EXISTS stg_inventory;
CREATE TABLE stg_inventory (
    stg_inventory_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    start_date               VARCHAR(20),
    end_date                 VARCHAR(20),
    stock_status             VARCHAR(50),
    supplier                 VARCHAR(100),
    product_no               VARCHAR(50),
    product_description      VARCHAR(255),
    product_division         VARCHAR(100),
    product_category         VARCHAR(100),
    product_subcategory      VARCHAR(100),
    product_segment          VARCHAR(100),
    store                    VARCHAR(30),
    store_type               VARCHAR(50),
    sales_channel            VARCHAR(50),
    qty_on_hand              DECIMAL(14, 4),
    stocks_selling_amount    DECIMAL(14, 4),
    cost_of_stocks           DECIMAL(14, 4),
    stock_unit_selling_price DECIMAL(14, 4),
    stock_unit_cost_price    DECIMAL(14, 4),
    loaded_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 2. DIMENSION TABLES (Conformed Dimensions)
-- ----------------------------------------------------------------------------
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS fact_inventory_interval;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_store;
DROP TABLE IF EXISTS dim_supplier;
DROP TABLE IF EXISTS dim_sales_type;

SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE dim_date (
    date_key     INT PRIMARY KEY,
    full_date    DATE NOT NULL UNIQUE,
    year         INT NOT NULL,
    quarter      INT NOT NULL,
    month        INT NOT NULL,
    month_name   VARCHAR(15) NOT NULL,
    week_of_year INT NOT NULL,
    day_of_week  INT NOT NULL,
    day_name     VARCHAR(15) NOT NULL,
    is_weekend   TINYINT(1) NOT NULL,
    is_sentinel  TINYINT(1) NOT NULL DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE dim_product (
    product_sk          INT AUTO_INCREMENT PRIMARY KEY,
    product_no          VARCHAR(50) NOT NULL UNIQUE,
    product_description VARCHAR(255) NOT NULL,
    product_division    VARCHAR(100) NOT NULL,
    product_category    VARCHAR(100) NOT NULL,
    product_subcategory VARCHAR(100) NOT NULL,
    product_segment     VARCHAR(100) NOT NULL,
    INDEX idx_product_hierarchy (product_division, product_category, product_subcategory)
) ENGINE=InnoDB;

CREATE TABLE dim_store (
    store_sk      INT AUTO_INCREMENT PRIMARY KEY,
    store_code    VARCHAR(30) NOT NULL UNIQUE,
    store_type    VARCHAR(50) NOT NULL,
    sales_channel VARCHAR(50) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE dim_supplier (
    supplier_sk   INT AUTO_INCREMENT PRIMARY KEY,
    supplier_name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE dim_sales_type (
    sales_type_sk    INT AUTO_INCREMENT PRIMARY KEY,
    sales_type_name  VARCHAR(50) NOT NULL UNIQUE,
    sales_type_group VARCHAR(30) NOT NULL
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 3. FACT TABLES (Constellation Schema)
-- ----------------------------------------------------------------------------

-- Grain: 1 dòng = Tổ hợp [Ngày, Sản phẩm, Cửa hàng, NCC, Loại giá, Trả hàng, Lý do trả]
CREATE TABLE fact_sales (
    sales_sk               BIGINT AUTO_INCREMENT PRIMARY KEY,
    transaction_date_key   INT NOT NULL,
    product_sk             INT NOT NULL,
    store_sk               INT NOT NULL,
    supplier_sk            INT NOT NULL,
    sales_type_sk          INT NOT NULL,
    is_return              TINYINT(1) NOT NULL,
    reason_of_return       VARCHAR(150) NOT NULL,
    qty_sold               INT NOT NULL,
    sales_amount           DECIMAL(14, 4) NOT NULL,
    cogs                   DECIMAL(14, 4) NOT NULL,
    number_of_transactions INT NOT NULL,
    CONSTRAINT fk_sales_date       FOREIGN KEY (transaction_date_key) REFERENCES dim_date(date_key),
    CONSTRAINT fk_sales_product    FOREIGN KEY (product_sk)           REFERENCES dim_product(product_sk),
    CONSTRAINT fk_sales_store      FOREIGN KEY (store_sk)             REFERENCES dim_store(store_sk),
    CONSTRAINT fk_sales_supplier   FOREIGN KEY (supplier_sk)          REFERENCES dim_supplier(supplier_sk),
    CONSTRAINT fk_sales_sales_type FOREIGN KEY (sales_type_sk)        REFERENCES dim_sales_type(sales_type_sk),
    INDEX idx_sales_date_prod (transaction_date_key, product_sk),
    INDEX idx_sales_return    (is_return)
) ENGINE=InnoDB;

-- Grain: 1 dòng = Khoảng hiệu lực [Start Date -> End Date] trạng thái tồn kho của Sản phẩm tại Cửa hàng & NCC
CREATE TABLE fact_inventory_interval (
    inventory_sk             BIGINT AUTO_INCREMENT PRIMARY KEY,
    start_date_key           INT NOT NULL,
    end_date_key             INT NOT NULL,
    product_sk               INT NOT NULL,
    store_sk                 INT NOT NULL,
    supplier_sk              INT NOT NULL,
    stock_status             VARCHAR(50) NOT NULL,
    is_current               TINYINT(1) NOT NULL,
    qty_on_hand              INT NOT NULL,
    stocks_selling_amount    DECIMAL(14, 4) NOT NULL,
    cost_of_stocks           DECIMAL(14, 4) NOT NULL,
    stock_unit_selling_price DECIMAL(14, 4) NOT NULL,
    stock_unit_cost_price    DECIMAL(14, 4) NOT NULL,
    CONSTRAINT fk_inv_start_date FOREIGN KEY (start_date_key) REFERENCES dim_date(date_key),
    CONSTRAINT fk_inv_end_date   FOREIGN KEY (end_date_key)   REFERENCES dim_date(date_key),
    CONSTRAINT fk_inv_product    FOREIGN KEY (product_sk)     REFERENCES dim_product(product_sk),
    CONSTRAINT fk_inv_store      FOREIGN KEY (store_sk)       REFERENCES dim_store(store_sk),
    CONSTRAINT fk_inv_supplier   FOREIGN KEY (supplier_sk)    REFERENCES dim_supplier(supplier_sk),
    INDEX idx_inv_dates_prod (start_date_key, end_date_key, product_sk),
    INDEX idx_inv_current    (is_current, product_sk)
) ENGINE=InnoDB;
