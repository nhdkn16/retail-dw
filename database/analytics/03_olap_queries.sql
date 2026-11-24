-- ============================================================================
-- PROJECT: Retail Sales & Inventory Data Warehouse
-- PURPOSE: Bộ truy vấn SQL Analytics & OLAP (Roll-up, Drill-down, Slice, Dice)
-- ============================================================================

USE retail_dw;

-- [Q1 - KPI TỔNG QUAN DOANH SỐ & LỢI NHUẬN CỬA HÀNG STR-1006]
SELECT
    ROUND(SUM(gross_sales_amount), 2) AS total_gross_sales,
    ROUND(SUM(return_amount), 2) AS total_return_amount,
    ROUND(SUM(net_sales_amount), 2) AS total_net_sales,
    ROUND(SUM(net_cogs), 2) AS total_net_cogs,
    ROUND(SUM(gross_profit), 2) AS total_gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(gross_sales_amount), 0) * 100, 2) AS gross_margin_pct,
    SUM(gross_qty_sold) AS total_gross_qty,
    SUM(return_qty) AS total_return_qty,
    SUM(net_qty_sold) AS total_net_qty,
    ROUND(SUM(return_qty) / NULLIF(SUM(gross_qty_sold), 0) * 100, 2) AS qty_return_rate_pct,
    SUM(purchase_transactions) AS total_purchase_tx
FROM vw_daily_product_sales;

-- [Q2 - OLAP ROLL-UP: Tổng hợp doanh thu & lợi nhuận từ Tháng -> Quý -> Năm]
SELECT
    year,
    quarter,
    month,
    month_name,
    ROUND(SUM(net_sales_amount), 2) AS net_sales,
    ROUND(SUM(gross_profit), 2) AS gross_profit,
    SUM(net_qty_sold) AS net_qty
FROM vw_daily_product_sales
GROUP BY year, quarter, month, month_name WITH ROLLUP;

-- [Q3 - OLAP DRILL-DOWN: Phân rã doanh số theo phân cấp sản phẩm Division -> Category -> Subcategory]
SELECT
    product_division,
    product_category,
    product_subcategory,
    COUNT(DISTINCT product_sk) AS active_skus,
    SUM(net_qty_sold) AS net_qty_sold,
    ROUND(SUM(net_sales_amount), 2) AS net_sales_amount,
    ROUND(SUM(gross_profit), 2) AS gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(gross_sales_amount), 0) * 100, 2) AS margin_pct
FROM vw_daily_product_sales
GROUP BY product_division, product_category, product_subcategory
ORDER BY net_sales_amount DESC
LIMIT 15;

-- [Q4 - OLAP SLICE: Cắt lát theo chiều Hình thức bán hàng (Sales Type)]
SELECT
    st.sales_type_group,
    st.sales_type_name,
    SUM(CASE WHEN f.is_return = 0 THEN f.qty_sold ELSE 0 END) AS gross_qty,
    SUM(f.qty_sold) AS net_qty,
    ROUND(SUM(f.sales_amount), 2) AS net_sales,
    ROUND(SUM(f.sales_amount - f.cogs), 2) AS gross_profit,
    ROUND(SUM(f.sales_amount) / (SELECT SUM(sales_amount) FROM fact_sales) * 100, 2) AS net_sales_share_pct
FROM fact_sales f
JOIN dim_sales_type st ON f.sales_type_sk = st.sales_type_sk
GROUP BY st.sales_type_group, st.sales_type_name
ORDER BY net_sales DESC;

-- [Q5 - OLAP DICE: Lọc đa chiều (Cuối tuần vs Ngày thường x Nhóm sản phẩm chính)]
SELECT
    d.is_weekend,
    CASE WHEN d.is_weekend = 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
    p.product_division,
    SUM(f.qty_sold) AS net_qty_sold,
    ROUND(SUM(f.sales_amount), 2) AS net_sales_amount,
    SUM(CASE WHEN f.is_return = 0 THEN f.number_of_transactions ELSE 0 END) AS purchase_tx
FROM fact_sales f
JOIN dim_date d ON f.transaction_date_key = d.date_key
JOIN dim_product p ON f.product_sk = p.product_sk
WHERE d.year IN (2025, 2026)
GROUP BY d.is_weekend, day_type, p.product_division
ORDER BY p.product_division, d.is_weekend;

-- [Q6 - PHÂN TÍCH TỒN KHO HIỆN HÀNH (AS-OF CURRENT) THEO PHÂN CẤP SẢN PHẨM]
-- Lưu ý: Chỉ tổng hợp trên các bản ghi is_current = 1 để không cộng trùng qua các khoảng hiệu lực
SELECT
    product_division,
    product_category,
    stock_status,
    COUNT(DISTINCT product_sk) AS sku_count,
    SUM(qty_on_hand) AS current_qty_on_hand,
    ROUND(SUM(stocks_selling_amount), 2) AS current_retail_value,
    ROUND(SUM(cost_of_stocks), 2) AS current_cost_value
FROM vw_current_inventory
GROUP BY product_division, product_category, stock_status
ORDER BY current_cost_value DESC;

-- [Q7 - KIỂM TRA TỒN KHO TẠI MỘT THỜI ĐIỂM LỊCH SỬ BẤT KỲ (POINT-IN-TIME SNAPSHOT: 2025-12-31)]
SELECT
    p.product_division,
    fi.stock_status,
    COUNT(DISTINCT fi.product_sk) AS sku_count,
    SUM(fi.qty_on_hand) AS qty_on_hand_as_of_date,
    ROUND(SUM(fi.cost_of_stocks), 2) AS cost_value_as_of_date
FROM fact_inventory_interval fi
JOIN dim_product p ON fi.product_sk = p.product_sk
WHERE fi.start_date_key <= 20251231
  AND fi.end_date_key >= 20251231
GROUP BY p.product_division, fi.stock_status
ORDER BY cost_value_as_of_date DESC;

-- [Q8 - KẾT HỢP AN TOÀN SALES & INVENTORY (CHỐNG FAN-OUT BẰNG CTE ĐỘC LẬP)]
-- Tính tốc độ bán trung bình 30 ngày cuối (từ 2026-03-26 đến 2026-04-24) và đối chiếu tồn kho hiện hành
WITH recent_sales_30d AS (
    SELECT
        product_sk,
        SUM(gross_qty_sold) AS sold_qty_30d,
        ROUND(SUM(gross_qty_sold) / 30.0, 3) AS avg_daily_sales,
        ROUND(SUM(net_sales_amount), 2) AS net_sales_30d
    FROM vw_daily_product_sales
    WHERE full_date BETWEEN '2026-03-26' AND '2026-04-24'
    GROUP BY product_sk
),
current_stock AS (
    SELECT
        product_sk,
        SUM(qty_on_hand) AS on_hand_qty,
        ROUND(SUM(cost_of_stocks), 2) AS on_hand_cost
    FROM vw_current_inventory
    GROUP BY product_sk
)
SELECT
    p.product_no,
    p.product_description,
    p.product_category,
    COALESCE(rs.sold_qty_30d, 0) AS sold_qty_30d,
    COALESCE(rs.avg_daily_sales, 0) AS avg_daily_sales,
    COALESCE(cs.on_hand_qty, 0) AS current_on_hand_qty,
    ROUND(COALESCE(cs.on_hand_qty, 0) / NULLIF(rs.avg_daily_sales, 0), 1) AS est_days_of_supply
FROM dim_product p
JOIN recent_sales_30d rs ON p.product_sk = rs.product_sk
LEFT JOIN current_stock cs ON p.product_sk = cs.product_sk
WHERE rs.sold_qty_30d >= 5
ORDER BY est_days_of_supply ASC, rs.sold_qty_30d DESC
LIMIT 15;
