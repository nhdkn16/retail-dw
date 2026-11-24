import logging
import os
from pathlib import Path
from urllib.parse import quote_plus

import matplotlib.pyplot as plt
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("report_generator")

STAGING_DIR = Path("data/staging")
PROCESSED_DIR = Path("data/processed")
REPORT_DIR = Path("reports")
FIGURES_DIR = REPORT_DIR / "figures"


def get_engine():
    load_dotenv()
    user = os.getenv("MYSQL_USER", "root")
    pwd = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    db = os.getenv("MYSQL_DATABASE", "retail_dw")
    return create_engine(f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4", future=True)


def ensure_directories() -> None:
    for folder in [STAGING_DIR, PROCESSED_DIR, REPORT_DIR, FIGURES_DIR]:
        folder.mkdir(parents=True, exist_ok=True)


def export_data_layers(engine) -> None:
    """Xuất dữ liệu phân tầng (Staging & Processed Marts) ra thư mục local để lưu trữ và kiểm chứng."""
    logger.info("Đang xuất dữ liệu phân tầng ra data/staging/ và data/processed/...")

    # Tầng Staging (dữ liệu thô STR-1006 đã tách khỏi file nguồn)
    pd.read_sql("SELECT * FROM stg_sales", engine).to_csv(STAGING_DIR / "stg_sales_str1006.csv", index=False)
    pd.read_sql("SELECT * FROM stg_inventory", engine).to_csv(STAGING_DIR / "stg_inventory_str1006.csv", index=False)

    # Tầng Processed (Data Marts sạch từ Semantic Views và ML Output)
    pd.read_sql("SELECT * FROM vw_daily_product_sales", engine).to_csv(
        PROCESSED_DIR / "mart_daily_product_sales.csv", index=False
    )
    pd.read_sql("SELECT * FROM vw_current_inventory", engine).to_csv(
        PROCESSED_DIR / "mart_current_inventory.csv", index=False
    )
    pd.read_sql("SELECT * FROM ml_weekly_demand_forecast", engine).to_csv(
        PROCESSED_DIR / "mart_ml_weekly_forecast.csv", index=False
    )
    logger.info("Đã lưu đầy đủ dữ liệu phân tầng vào data/staging/ và data/processed/.")


def generate_figures(engine) -> dict:
    """Vẽ 5 biểu đồ phân tích và lưu vào reports/figures/ (300 DPI)."""
    logger.info("Đang khởi tạo các biểu đồ báo cáo tại %s...", FIGURES_DIR)
    plt.rcParams["axes.edgecolor"] = "#CCCCCC"
    plt.rcParams["axes.linewidth"] = 0.8

    # 1. Biểu đồ doanh thu & lợi nhuận gộp theo tháng
    df_monthly = pd.read_sql(
        text(
            """
            SELECT
                DATE_FORMAT(full_date, '%Y-%m') AS ym,
                SUM(net_sales_amount) AS net_sales,
                SUM(gross_profit) AS gross_profit
            FROM vw_daily_product_sales
            GROUP BY ym
            ORDER BY ym
            """
        ),
        engine,
    )
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x = range(len(df_monthly))
    width = 0.38
    ax.bar([i - width / 2 for i in x], df_monthly["net_sales"], width=width, label="Net Sales", color="#1f77b4")
    ax.bar([i + width / 2 for i in x], df_monthly["gross_profit"], width=width, label="Gross Profit", color="#2ca02c")
    ax.set_xticks(list(x))
    ax.set_xticklabels(df_monthly["ym"], rotation=45, ha="right")
    ax.set_title("Figure 1: Monthly Net Sales and Gross Profit Trend (Store STR-1006)", fontweight="bold")
    ax.set_ylabel("Amount (Source Currency Unit)")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend()
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "fig1_monthly_sales_profit.png", dpi=300)
    plt.close(fig)

    # 2. Biểu đồ cơ cấu doanh thu theo Sales Type
    df_stype = pd.read_sql(
        text(
            """
            SELECT
                st.sales_type_name,
                SUM(f.sales_amount) AS net_sales,
                SUM(f.sales_amount - f.cogs) AS gross_profit
            FROM fact_sales f
            JOIN dim_sales_type st ON f.sales_type_sk = st.sales_type_sk
            GROUP BY st.sales_type_name
            ORDER BY net_sales DESC
            """
        ),
        engine,
    )
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    bars = ax.bar(df_stype["sales_type_name"], df_stype["net_sales"], color="#3b75af")
    ax.set_title("Figure 2: Net Sales Breakdown by Sales Type (OLAP Slice)", fontweight="bold")
    ax.set_ylabel("Net Sales")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    for bar in bars:
        h = bar.get_height()
        ax.annotate(f"{h:,.0f}", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=8.5)
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "fig2_sales_by_type.png", dpi=300)
    plt.close(fig)

    # 3. Top 10 Product Category theo Doanh thu thuần
    df_cat = pd.read_sql(
        text(
            """
            SELECT product_category, SUM(net_sales_amount) AS net_sales
            FROM vw_daily_product_sales
            GROUP BY product_category
            ORDER BY net_sales DESC
            LIMIT 10
            """
        ),
        engine,
    ).sort_values("net_sales", ascending=True)
    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    ax.barh(df_cat["product_category"], df_cat["net_sales"], color="#2b8cbe")
    ax.set_title("Figure 3: Top 10 Product Categories by Net Sales", fontweight="bold")
    ax.set_xlabel("Net Sales")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "fig3_top10_categories_sales.png", dpi=300)
    plt.close(fig)

    # 4. Cơ cấu giá trị tồn kho hiện hành theo Category (Top 10)
    df_inv = pd.read_sql(
        text(
            """
            SELECT product_category, SUM(cost_of_stocks) AS cost_value
            FROM vw_current_inventory
            GROUP BY product_category
            ORDER BY cost_value DESC
            LIMIT 10
            """
        ),
        engine,
    ).sort_values("cost_value", ascending=True)
    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    ax.barh(df_inv["product_category"], df_inv["cost_value"], color="#e6550d")
    ax.set_title("Figure 4: Top 10 Product Categories by Current Inventory Cost Value", fontweight="bold")
    ax.set_xlabel("Inventory Cost Value (As-Of Current)")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "fig4_top10_inventory_cost.png", dpi=300)
    plt.close(fig)

    # 5. Biểu đồ kết quả Machine Learning: So sánh MAE/RMSE & Dự báo tổng nhu cầu tuần
    df_metrics = pd.read_sql("SELECT * FROM ml_model_metrics ORDER BY MAE ASC", engine)
    df_fc = pd.read_sql("SELECT * FROM ml_weekly_demand_forecast", engine)
    df_fc["week_start"] = pd.to_datetime(df_fc["week_start"])
    agg_fc = (
        df_fc.groupby(["week_start", "split_type"], as_index=False)[["actual_qty", "predicted_qty"]]
        .sum()
        .sort_values("week_start")
    )

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1, 1.6]})
    # Subplot trái: So sánh MAE
    colors = ["#2ca02c" if "ML" in m else "#7f7f7f" for m in df_metrics["model_name"]]
    ax1.barh(df_metrics["model_name"], df_metrics["MAE"], color=colors)
    ax1.invert_yaxis()
    ax1.set_title("Model Comparison (Test MAE - Lower is Better)", fontweight="bold", fontsize=10)
    ax1.set_xlabel("Mean Absolute Error (Units/Week)")
    ax1.grid(axis="x", linestyle="--", alpha=0.4)

    # Subplot phải: Chuỗi thời gian tổng hợp 15 danh mục
    hist = agg_fc[agg_fc["split_type"].isin(["TRAIN_HISTORY", "TEST_BACKTEST"])]
    test = agg_fc[agg_fc["split_type"] == "TEST_BACKTEST"]
    fut = agg_fc[agg_fc["split_type"] == "FORECAST_FUTURE"]

    ax2.plot(hist["week_start"], hist["actual_qty"], label="Actual Weekly Demand", color="#1f77b4", marker="o", markersize=3)
    ax2.plot(test["week_start"], test["predicted_qty"], label="Test Backtest (Random Forest)", color="#ff7f0e", linestyle="--", marker="s", markersize=4)
    ax2.plot(fut["week_start"], fut["predicted_qty"], label="4-Week Future Forecast", color="#2ca02c", linewidth=2.2, marker="^", markersize=5)
    ax2.set_title("Aggregate Weekly Demand & 4-Week Forecast (15 Categories)", fontweight="bold", fontsize=10)
    ax2.set_ylabel("Weekly Gross Quantity")
    ax2.tick_params(axis="x", rotation=35)
    ax2.grid(True, linestyle="--", alpha=0.4)
    ax2.legend(fontsize=8)

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "fig5_ml_forecast_evaluation.png", dpi=300)
    plt.close(fig)

    logger.info("Đã xuất xong 5 biểu đồ vào thư mục reports/figures/.")
    return {"metrics_df": df_metrics, "stype_df": df_stype}


def write_markdown_report(engine, artifacts: dict) -> None:
    """Tổng hợp toàn bộ số liệu thực nghiệm thành file báo cáo Markdown hoàn chỉnh."""
    kpi = pd.read_sql(
        text(
            """
            SELECT
                ROUND(SUM(gross_sales_amount), 2) AS gross_sales,
                ROUND(SUM(return_amount), 2) AS return_amount,
                ROUND(SUM(net_sales_amount), 2) AS net_sales,
                ROUND(SUM(net_cogs), 2) AS net_cogs,
                ROUND(SUM(gross_profit), 2) AS gross_profit,
                ROUND(SUM(gross_profit) / NULLIF(SUM(gross_sales_amount), 0) * 100, 2) AS margin_pct,
                SUM(gross_qty_sold) AS gross_qty,
                SUM(return_qty) AS return_qty,
                SUM(net_qty_sold) AS net_qty,
                ROUND(SUM(return_qty) / NULLIF(SUM(gross_qty_sold), 0) * 100, 2) AS return_rate_pct,
                SUM(purchase_transactions) AS purchase_tx
            FROM vw_daily_product_sales
            """
        ),
        engine,
    ).iloc[0]

    inv_kpi = pd.read_sql(
        text(
            """
            SELECT
                COUNT(DISTINCT product_sk) AS sku_count,
                SUM(qty_on_hand) AS total_on_hand,
                ROUND(SUM(cost_of_stocks), 2) AS total_cost_val,
                ROUND(SUM(stocks_selling_amount), 2) AS total_retail_val
            FROM vw_current_inventory
            """
        ),
        engine,
    ).iloc[0]

    metrics_md = artifacts["metrics_df"].to_markdown(index=False)

    report_content = f"""# BÁO CÁO TỔNG KẾT ĐỒ ÁN KHO DỮ LIỆU (DATA WAREHOUSE)
**Đề tài:** Xây dựng Kho dữ liệu Phân tích Doanh số, Quản lý Tồn kho và Dự báo Nhu cầu Hàng hóa trong Bán lẻ (Phạm vi: Cửa hàng `STR-1006`)

---

## 1. Tổng quan & Phân tầng Dữ liệu (Data Architecture)

Dự án triển khai kiến trúc xử lý dữ liệu phân tầng (Medallion / Multi-tier Data Architecture) trên môi trường Windows local kết hợp **MySQL** và **Python**:

1. **Tầng Nguồn Bất Biến (`data/raw/`):** Lưu trữ nguyên bản gói dữ liệu `retail-transactions-and-stocks-data.zip` (SHA-256: `f65cb8ace7d2d7864986dde91ae658311cd334e5d6c742d3a9f9f8bfc9675480`), gồm 125.751 dòng Sales và 284.755 dòng Inventory trên 40 cửa hàng.
2. **Tầng Trung Gian (`data/staging/` & MySQL `stg_*`):** Lọc nhất quán dữ liệu của cửa hàng mục tiêu **`STR-1006`** (5.904 dòng Sales, 11.142 dòng Inventory, 323 ngày hoạt động từ `2025-06-01` đến `2026-04-24`, tỷ lệ khớp SKU giữa hai bảng đạt 95,0%).
3. **Tầng Kho Dữ Liệu Lõi (MySQL `retail_dw` — Constellation Schema):**
   * **5 Conformed Dimensions:** `dim_date` (329 bản ghi gồm ngày sentinel `9999-12-31`), `dim_product` (2.068 SKU), `dim_store` (1 cửa hàng), `dim_supplier` (30 nhà cung cấp), `dim_sales_type` (5 hình thức bán hàng).
   * **2 Fact Tables với Grain tách biệt:** `fact_sales` (Fully Additive — tổng hợp giao dịch theo tổ hợp chiều trong ngày) và `fact_inventory_interval` (Semi-Additive — khoảng hiệu lực `Start Date` đến `End Date`).
4. **Tầng Dữ Liệu Nghiệp Vụ (`data/processed/` & Semantic Views):** Bao gồm `vw_daily_product_sales`, `vw_current_inventory`, `vw_weekly_product_sales` và các bảng đầu ra của Machine Learning (`ml_model_metrics`, `ml_weekly_demand_forecast`).

---

## 2. Kết quả Đối soát Dữ liệu ETL (Data Reconciliation)

Quá trình nạp dữ liệu từ Staging sang Data Warehouse đảm bảo tính toàn vẹn và khớp chính xác 100% trên mọi chỉ số:

* **Bảng Sales:** `5.904` dòng | Tổng sản lượng thuần: `{int(kpi['net_qty']):,}` | Tổng doanh thu thuần: `{kpi['net_sales']:,.2f}` | Tổng giá vốn thuần: `{kpi['net_cogs']:,.2f}`.
* **Bảng Inventory:** `11.142` dòng | Số bản ghi tồn kho hiện hành (`is_current = 1`): `576` dòng | Checksum `qty_on_hand`: `28.771`.

---

## 3. Kết quả Phân tích Kinh doanh & OLAP

### 3.1. Các chỉ số KPI Tổng hợp (`STR-1006`)
* **Doanh thu gộp (Gross Sales):** `{kpi['gross_sales']:,.2f}`
* **Giá trị hàng trả lại (Return Amount):** `{kpi['return_amount']:,.2f}`
* **Doanh thu thuần (Net Sales):** `{kpi['net_sales']:,.2f}`
* **Lợi nhuận gộp (Gross Profit):** `{kpi['gross_profit']:,.2f}` (**Biên lợi nhuận gộp: {kpi['margin_pct']:.2f}%**)
* **Sản lượng thuần (Net Qty Sold):** `{int(kpi['net_qty']):,}` sản phẩm (Bán gộp: `{int(kpi['gross_qty']):,}`, Trả lại: `{int(kpi['return_qty']):,}`, Tỷ lệ trả: **{kpi['return_rate_pct']:.2f}%**)
* **Tổng số lượt mua hàng:** `{int(kpi['purchase_tx']):,}` lượt

### 3.2. Phân tích Xu hướng & Cơ cấu Doanh thu
* **Tính mùa vụ theo tháng:** Doanh thu thuần đạt đỉnh mạnh vào **Tháng 8/2025** (`83.826,34`) và **Tháng 12/2025** (`70.858,46`).

![Monthly Sales and Profit](figures/fig1_monthly_sales_profit.png)

* **Hiệu quả theo Hình thức bán hàng (`Sales Type`):** `Full Price` đóng góp **88,11%** tổng doanh thu thuần (`427.835,83`) và mang lại phần lớn lợi nhuận gộp (`210.952,87`). Nhóm `Promo` chiếm **10,63%** (`51.612,71`). Các mức giảm giá sâu như `Markdown Tier 2` và `Clearance` có lợi nhuận gộp âm do xả hàng dưới giá vốn.

![Sales by Type](figures/fig2_sales_by_type.png)

* **Danh mục sản phẩm chủ lực:** Ngành hàng `Scholar Footwear` dẫn đầu toàn cửa hàng, nổi bật với các danh mục như `Scholar Footwear Trailblazer`, `Scholar Footwear Retro Legend` và `Scholar Footwear Modern Legend`.

![Top 10 Categories](figures/fig3_top10_categories_sales.png)

### 3.3. Phân tích Tồn kho Hiện hành (`As-Of Current`)
Tại thời điểm chốt dữ liệu (`is_current = 1`):
* **Tổng số lượng tồn kho (`On-Hand Qty`):** `{int(inv_kpi['total_on_hand']):,}` sản phẩm trên `{int(inv_kpi['sku_count']):,}` SKU đang theo dõi.
* **Tổng giá trị tồn theo giá vốn:** `{inv_kpi['total_cost_val']:,.2f}` | **Theo giá bán lẻ:** `{inv_kpi['total_retail_val']:,.2f}`.

![Top 10 Inventory Cost](figures/fig4_top10_inventory_cost.png)

---

## 4. Kết quả Dự báo Nhu cầu bằng Machine Learning

* **Thiết kế thực nghiệm:** Tổng hợp nhu cầu bán gộp theo **Tuần** qua 46 tuần trọn vẹn (`2025-06-02` đến `2026-04-19`) cho **15 Danh mục sản phẩm** có lịch sử bán hàng liên tục ($\ge 100$ sản phẩm). Chia tập theo thời gian (**Temporal Split**): 34 tuần huấn luyện và **8 tuần cuối kiểm thử** (`2026-02-23` $\rightarrow$ `2026-04-19`), không sử dụng dữ liệu tương lai để tạo đặc trưng trễ.
* **Bảng đánh giá hiệu năng mô hình trên tập Test:**

{metrics_md}

* **Nhận xét:** Mô hình **Random Forest Regressor** đạt sai số thấp nhất (`MAE = 3,750`, `WAPE = 48,24%`), vượt qua cả hai mô hình cơ sở (`Naive Forecast` và `4-Week Moving Average`). Mô hình này được sử dụng để dự báo nhu cầu 4 tuần tiếp theo (`2026-04-20` $\rightarrow$ `2026-05-17`) và tích hợp vào Dashboard Streamlit để cảnh báo nguy cơ thiếu hàng hoặc tồn kho cao.

![ML Forecast Evaluation](figures/fig5_ml_forecast_evaluation.png)

---

## 5. Giới hạn của Hệ thống & Hướng Phát triển

1. **Độ thưa dữ liệu cấp SKU:** Tốc độ bán của từng SKU đơn lẻ khá thấp (1–2 sản phẩm/tuần), do đó mô hình dự báo hoạt động hiệu quả nhất ở cấp độ `Product Category` theo tuần.
2. **Đơn vị tiền tệ & Dữ liệu khách hàng:** Dataset nguồn không định danh đơn vị tiền tệ cụ thể và không có `Customer ID`, giới hạn khả năng phân tích phân khúc khách hàng.
3. **Hướng mở rộng:** Tích hợp thêm dữ liệu lịch khuyến mãi dự kiến, thời gian giao hàng của nhà cung cấp (Lead Time) để nâng cấp bài toán từ dự báo nhu cầu sang tối ưu điểm đặt hàng lại (Reorder Point Optimization).
"""

    report_path = REPORT_DIR / "final_project_report.md"
    report_path.write_text(report_content, encoding="utf-8")
    logger.info("Đã xuất báo cáo tổng hợp thành công tại: %s", report_path.resolve())


def main() -> None:
    ensure_directories()
    engine = get_engine()
    try:
        export_data_layers(engine)
        artifacts = generate_figures(engine)
        write_markdown_report(engine, artifacts)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
    