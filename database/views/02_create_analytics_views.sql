-- ============================================================================
-- PROJECT: Retail Sales & Inventory Data Warehouse
-- LAYER:   Semantic Views (Tầng nghiệp vụ & KPI chuẩn hóa)
-- ============================================================================

USE retail_dw;

-- 1. View doanh số tổng hợp theo Ngày và Sản phẩm (Tách rõ Bán gộp, Trả hàng và Thuần)
CREATE OR REPLACE VIEW vw_daily_product_sales AS
SELECT
    d.date_key,
    d.full_date,
    d.year,
    d.quarter,
    d.month,
    d.month_name,
    d.week_of_year,
    d.day_name,
    d.is_weekend,
    p.product_sk,
    p.product_no,
    p.product_description,
    p.product_division,
    p.product_category,
    p.product_subcategory,
    p.product_segment,
    SUM(CASE WHEN f.is_return = 0 THEN f.qty_sold ELSE 0 END) AS gross_qty_sold,
    ABS(SUM(CASE WHEN f.is_return = 1 THEN f.qty_sold ELSE 0 END)) AS return_qty,
    SUM(f.qty_sold) AS net_qty_sold,
    SUM(CASE WHEN f.is_return = 0 THEN f.sales_amount ELSE 0 END) AS gross_sales_amount,
    ABS(SUM(CASE WHEN f.is_return = 1 THEN f.sales_amount ELSE 0 END)) AS return_amount,
    SUM(f.sales_amount) AS net_sales_amount,
    SUM(f.cogs) AS net_cogs,
    SUM(f.sales_amount - f.cogs) AS gross_profit,
    SUM(CASE WHEN f.is_return = 0 THEN f.number_of_transactions ELSE 0 END) AS purchase_transactions,
    SUM(CASE WHEN f.is_return = 1 THEN f.number_of_transactions ELSE 0 END) AS return_transactions
FROM fact_sales f
JOIN dim_date d ON f.transaction_date_key = d.date_key
JOIN dim_product p ON f.product_sk = p.product_sk
GROUP BY
    d.date_key, d.full_date, d.year, d.quarter, d.month, d.month_name,
    d.week_of_year, d.day_name, d.is_weekend,
    p.product_sk, p.product_no, p.product_description, p.product_division,
    p.product_category, p.product_subcategory, p.product_segment;

-- 2. View tồn kho hiện hành (Snapshot tại thời điểm cuối dữ liệu: is_current = 1)
CREATE OR REPLACE VIEW vw_current_inventory AS
SELECT
    p.product_sk,
    p.product_no,
    p.product_description,
    p.product_division,
    p.product_category,
    p.product_subcategory,
    p.product_segment,
    s.supplier_name,
    fi.stock_status,
    d_start.full_date AS effective_from_date,
    fi.qty_on_hand,
    fi.stocks_selling_amount,
    fi.cost_of_stocks,
    fi.stock_unit_selling_price,
    fi.stock_unit_cost_price
FROM fact_inventory_interval fi
JOIN dim_product p ON fi.product_sk = p.product_sk
JOIN dim_supplier s ON fi.supplier_sk = s.supplier_sk
JOIN dim_date d_start ON fi.start_date_key = d_start.date_key
WHERE fi.is_current = 1;

-- 3. View chuỗi thời gian bán hàng theo Tuần (Phục vụ cả BI Trend và ML Forecasting ở Giai đoạn 6)
CREATE OR REPLACE VIEW vw_weekly_product_sales AS
SELECT
    YEARWEEK(d.full_date, 3) AS iso_year_week,
    MIN(d.full_date) AS week_start_date,
    MAX(d.full_date) AS week_end_date,
    p.product_sk,
    p.product_no,
    p.product_description,
    p.product_division,
    p.product_category,
    SUM(CASE WHEN f.is_return = 0 THEN f.qty_sold ELSE 0 END) AS gross_qty_sold,
    SUM(f.qty_sold) AS net_qty_sold,
    SUM(f.sales_amount) AS net_sales_amount,
    SUM(f.sales_amount - f.cogs) AS gross_profit
FROM fact_sales f
JOIN dim_date d ON f.transaction_date_key = d.date_key
JOIN dim_product p ON f.product_sk = p.product_sk
GROUP BY
    YEARWEEK(d.full_date, 3),
    p.product_sk, p.product_no, p.product_description,
    p.product_division, p.product_category;
