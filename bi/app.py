import os
from urllib.parse import quote_plus

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Retail DW Analytics & Forecasting - Store STR-1006",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_db_engine():
    load_dotenv()
    user = os.getenv("MYSQL_USER", "root")
    pwd = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    db = os.getenv("MYSQL_DATABASE", "retail_dw")
    return create_engine(f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4", future=True)


@st.cache_data(ttl=300)
def load_sales_data() -> pd.DataFrame:
    engine = get_db_engine()
    query = """
        SELECT
            full_date, year, quarter, month, month_name, week_of_year, day_name, is_weekend,
            product_sk, product_no, product_description, product_division, product_category,
            product_subcategory, gross_qty_sold, return_qty, net_qty_sold,
            gross_sales_amount, return_amount, net_sales_amount, net_cogs, gross_profit,
            purchase_transactions, return_transactions
        FROM vw_daily_product_sales
    """
    df = pd.read_sql(text(query), engine)
    df["full_date"] = pd.to_datetime(df["full_date"])
    return df


@st.cache_data(ttl=300)
def load_sales_type_data() -> pd.DataFrame:
    engine = get_db_engine()
    query = """
        SELECT
            d.full_date,
            p.product_division,
            p.product_category,
            st.sales_type_group,
            st.sales_type_name,
            SUM(CASE WHEN f.is_return = 0 THEN f.qty_sold ELSE 0 END) AS gross_qty,
            SUM(f.qty_sold) AS net_qty,
            SUM(f.sales_amount) AS net_sales,
            SUM(f.sales_amount - f.cogs) AS gross_profit
        FROM fact_sales f
        JOIN dim_date d ON f.transaction_date_key = d.date_key
        JOIN dim_product p ON f.product_sk = p.product_sk
        JOIN dim_sales_type st ON f.sales_type_sk = st.sales_type_sk
        GROUP BY d.full_date, p.product_division, p.product_category, st.sales_type_group, st.sales_type_name
    """
    df = pd.read_sql(text(query), engine)
    df["full_date"] = pd.to_datetime(df["full_date"])
    return df


@st.cache_data(ttl=300)
def load_current_inventory() -> pd.DataFrame:
    engine = get_db_engine()
    return pd.read_sql(text("SELECT * FROM vw_current_inventory"), engine)


@st.cache_data(ttl=300)
def load_ml_outputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    engine = get_db_engine()
    metrics_df = pd.read_sql(text("SELECT * FROM ml_model_metrics"), engine)
    forecast_df = pd.read_sql(text("SELECT * FROM ml_weekly_demand_forecast"), engine)
    forecast_df["week_start"] = pd.to_datetime(forecast_df["week_start"])
    return metrics_df, forecast_df


def main():
    st.title("📊 Retail Sales & Inventory Data Warehouse — Store STR-1006")
    st.caption(
        "Kiến trúc: MySQL Data Warehouse (`retail_dw`) + Python ETL + Scikit-Learn ML + Streamlit BI | "
        "Kênh: `Channel Alpha` | Lưu ý: Đơn vị tiền tệ giữ nguyên theo dữ liệu nguồn."
    )

    df_sales = load_sales_data()
    df_stype = load_sales_type_data()
    df_inv = load_current_inventory()
    df_metrics, df_forecast = load_ml_outputs()

    # --- SIDEBAR FILTERS ---
    st.sidebar.header("🎛️ Bộ lọc phân tích (OLAP Slice & Dice)")
    min_date = df_sales["full_date"].min().date()
    max_date = df_sales["full_date"].max().date()

    date_range = st.sidebar.date_input(
        "Khoảng thời gian giao dịch",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    divisions = sorted(df_sales["product_division"].unique().tolist())
    selected_divisions = st.sidebar.multiselect("Ngành hàng (Division)", divisions, default=divisions)

    avail_categories = sorted(
        df_sales[df_sales["product_division"].isin(selected_divisions)]["product_category"].unique().tolist()
    )
    selected_categories = st.sidebar.multiselect("Danh mục (Category)", avail_categories, default=avail_categories)

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    else:
        start_dt, end_dt = pd.to_datetime(min_date), pd.to_datetime(max_date)

    sales_filtered = df_sales[
        (df_sales["full_date"] >= start_dt)
        & (df_sales["full_date"] <= end_dt)
        & (df_sales["product_division"].isin(selected_divisions))
        & (df_sales["product_category"].isin(selected_categories))
    ]

    stype_filtered = df_stype[
        (df_stype["full_date"] >= start_dt)
        & (df_stype["full_date"] <= end_dt)
        & (df_stype["product_division"].isin(selected_divisions))
        & (df_stype["product_category"].isin(selected_categories))
    ]

    inv_filtered = df_inv[
        (df_inv["product_division"].isin(selected_divisions))
        & (df_inv["product_category"].isin(selected_categories))
    ]

    # --- TABS PHÂN TÍCH ---
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📈 Tổng quan Doanh số",
            "🏷️ Sản phẩm & Khuyến mãi",
            "📦 Quản trị Tồn kho",
            "🤖 Dự báo ML & Hỗ trợ Quyết định",
        ]
    )

    # ==================== TAB 1: TỔNG QUAN DOANH SỐ ====================
    with tab1:
        gross_sales = sales_filtered["gross_sales_amount"].sum()
        net_sales = sales_filtered["net_sales_amount"].sum()
        gross_profit = sales_filtered["gross_profit"].sum()
        margin_pct = (gross_profit / gross_sales * 100) if gross_sales != 0 else 0.0
        net_qty = int(sales_filtered["net_qty_sold"].sum())
        gross_qty = int(sales_filtered["gross_qty_sold"].sum())
        return_qty = int(sales_filtered["return_qty"].sum())
        return_rate = (return_qty / gross_qty * 100) if gross_qty != 0 else 0.0
        purchase_tx = int(sales_filtered["purchase_transactions"].sum())

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Doanh thu thuần (Net Sales)", f"{net_sales:,.2f}")
        c2.metric("Lợi nhuận gộp (Gross Profit)", f"{gross_profit:,.2f}", f"Biên LN: {margin_pct:.2f}%")
        c3.metric("Sản lượng thuần (Net Qty)", f"{net_qty:,}")
        c4.metric("Tỷ lệ trả hàng (Qty)", f"{return_rate:.2f}%", f"-{return_qty:,} sp trả", delta_color="inverse")
        c5.metric("Số lượt mua hàng", f"{purchase_tx:,}")

        st.divider()

        monthly_df = (
            sales_filtered.assign(year_month=sales_filtered["full_date"].dt.to_period("M").astype(str))
            .groupby("year_month", as_index=False)[["net_sales_amount", "gross_profit", "net_qty_sold"]]
            .sum()
        )
        fig_monthly = px.bar(
            monthly_df,
            x="year_month",
            y=["net_sales_amount", "gross_profit"],
            barmode="group",
            title="Xu hướng Doanh thu thuần & Lợi nhuận gộp theo Tháng",
            labels={"value": "Giá trị", "year_month": "Tháng", "variable": "Chỉ số"},
        )
        st.plotly_chart(fig_monthly, use_container_width=True)

        col_left, col_right = st.columns(2)
        with col_left:
            dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            dow_df = (
                sales_filtered.groupby("day_name", as_index=False)["net_sales_amount"]
                .sum()
                .set_index("day_name")
                .reindex(dow_order)
                .reset_index()
            )
            fig_dow = px.bar(
                dow_df,
                x="day_name",
                y="net_sales_amount",
                title="Doanh thu thuần theo Thứ trong tuần",
                labels={"day_name": "Thứ", "net_sales_amount": "Doanh thu thuần"},
            )
            st.plotly_chart(fig_dow, use_container_width=True)

        with col_right:
            div_df = sales_filtered.groupby("product_division", as_index=False)["net_sales_amount"].sum()
            fig_div = px.pie(
                div_df,
                names="product_division",
                values="net_sales_amount",
                hole=0.4,
                title="Tỷ trọng Doanh thu thuần theo Ngành hàng (Division)",
            )
            st.plotly_chart(fig_div, use_container_width=True)

    # ==================== TAB 2: SẢN PHẨM & KHUYẾN MÃI ====================
    with tab2:
        col_a, col_b = st.columns(2)
        with col_a:
            st_summary = stype_filtered.groupby("sales_type_name", as_index=False)[
                ["net_sales", "gross_profit", "net_qty"]
            ].sum()
            fig_st = px.bar(
                st_summary.sort_values("net_sales", ascending=False),
                x="sales_type_name",
                y=["net_sales", "gross_profit"],
                barmode="group",
                title="Hiệu quả Doanh thu & Lợi nhuận theo Hình thức giá (Sales Type)",
                labels={"sales_type_name": "Loại giá bán", "value": "Giá trị"},
            )
            st.plotly_chart(fig_st, use_container_width=True)

        with col_b:
            cat_summary = (
                sales_filtered.groupby(["product_division", "product_category"], as_index=False)[
                    ["net_sales_amount", "gross_profit", "net_qty_sold"]
                ]
                .sum()
                .sort_values("net_sales_amount", ascending=False)
                .head(10)
            )
            fig_cat = px.bar(
                cat_summary,
                x="net_sales_amount",
                y="product_category",
                color="product_division",
                orientation="h",
                title="Top 10 Danh mục (Category) có Doanh thu thuần cao nhất",
                labels={"net_sales_amount": "Doanh thu thuần", "product_category": "Danh mục"},
            )
            fig_cat.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_cat, use_container_width=True)

        st.subheader("Top 15 Sản phẩm (SKU) bán chạy nhất theo Doanh thu thuần")
        top_skus = (
            sales_filtered.groupby(["product_no", "product_description", "product_category"], as_index=False)[
                ["gross_qty_sold", "return_qty", "net_qty_sold", "net_sales_amount", "gross_profit"]
            ]
            .sum()
            .sort_values("net_sales_amount", ascending=False)
            .head(15)
        )
        st.dataframe(top_skus, use_container_width=True, hide_index=True)

    # ==================== TAB 3: TỒN KHO HIỆN HÀNH ====================
    with tab3:
        st.info(
            "Dữ liệu tồn kho dưới đây phản ánh trạng thái hiện hành (`is_current = 1`, ngày kết thúc hiệu lực `9999-12-31`), "
            "đảm bảo không cộng trùng qua các khoảng thời gian lịch sử."
        )

        total_on_hand = int(inv_filtered["qty_on_hand"].sum())
        total_retail_val = inv_filtered["stocks_selling_amount"].sum()
        total_cost_val = inv_filtered["cost_of_stocks"].sum()
        active_inv_skus = inv_filtered["product_no"].nunique()

        ic1, ic2, ic3, ic4 = st.columns(4)
        ic1.metric("Số SKU trong danh mục tồn", f"{active_inv_skus:,}")
        ic2.metric("Tổng số lượng tồn (On-Hand)", f"{total_on_hand:,}")
        ic3.metric("Giá trị tồn theo giá vốn", f"{total_cost_val:,.2f}")
        ic4.metric("Giá trị tồn theo giá bán", f"{total_retail_val:,.2f}")

        st.divider()

        col_i1, col_i2 = st.columns(2)
        with col_i1:
            inv_status_df = inv_filtered.groupby("stock_status", as_index=False)[
                ["qty_on_hand", "cost_of_stocks"]
            ].sum()
            fig_inv_status = px.pie(
                inv_status_df,
                names="stock_status",
                values="cost_of_stocks",
                title="Cơ cấu Giá trị vốn tồn kho theo Trạng thái (Stock Status)",
            )
            st.plotly_chart(fig_inv_status, use_container_width=True)

        with col_i2:
            inv_cat_df = (
                inv_filtered.groupby(["product_division", "product_category"], as_index=False)[
                    ["qty_on_hand", "cost_of_stocks"]
                ]
                .sum()
                .sort_values("cost_of_stocks", ascending=False)
                .head(10)
            )
            fig_inv_cat = px.bar(
                inv_cat_df,
                x="cost_of_stocks",
                y="product_category",
                color="product_division",
                orientation="h",
                title="Top 10 Danh mục chiếm Giá trị vốn tồn kho lớn nhất",
                labels={"cost_of_stocks": "Giá trị vốn tồn", "product_category": "Danh mục"},
            )
            fig_inv_cat.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_inv_cat, use_container_width=True)

        st.subheader("Chi tiết danh mục tồn kho hiện hành")
        st.dataframe(
            inv_filtered[
                [
                    "product_no",
                    "product_description",
                    "product_category",
                    "supplier_name",
                    "stock_status",
                    "effective_from_date",
                    "qty_on_hand",
                    "cost_of_stocks",
                    "stocks_selling_amount",
                ]
            ].sort_values("cost_of_stocks", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

    # ==================== TAB 4: DỰ BÁO ML & HỖ TRỢ QUYẾT ĐỊNH ====================
    with tab4:
        st.subheader("1. Đánh giá Mô hình Dự báo Nhu cầu (Temporal Split: 8 tuần kiểm thử cuối)")
        col_m1, col_m2 = st.columns([1.2, 1.8])
        with col_m1:
            st.dataframe(df_metrics, use_container_width=True, hide_index=True)
            st.caption(
                "Lưu ý kỹ thuật: Sử dụng WAPE thay cho MAPE truyền thống để tránh lỗi chia cho 0 ở các tuần "
                "danh mục nhỏ không phát sinh đơn hàng. Mô hình Random Forest vượt qua cả hai Baseline."
            )

        with col_m2:
            forecast_cats = sorted(df_forecast["product_category"].unique().tolist())
            chosen_cat = st.selectbox("Chọn Danh mục (Product Category) để xem chuỗi dự báo tuần:", forecast_cats)

            cat_ts = df_forecast[df_forecast["product_category"] == chosen_cat].sort_values("week_start")
            fig_fc = go.Figure()

            hist_part = cat_ts[cat_ts["split_type"].isin(["TRAIN_HISTORY", "TEST_BACKTEST"])]
            test_part = cat_ts[cat_ts["split_type"] == "TEST_BACKTEST"]
            fut_part = cat_ts[cat_ts["split_type"] == "FORECAST_FUTURE"]

            fig_fc.add_trace(
                go.Scatter(
                    x=hist_part["week_start"],
                    y=hist_part["actual_qty"],
                    mode="lines+markers",
                    name="Thực tế bán ra (Actual Gross Qty)",
                    line=dict(color="#1f77b4", width=2),
                )
            )
            fig_fc.add_trace(
                go.Scatter(
                    x=test_part["week_start"],
                    y=test_part["predicted_qty"],
                    mode="lines+markers",
                    name="Dự báo kiểm thử (Test Backtest)",
                    line=dict(color="#ff7f0e", width=2, dash="dash"),
                )
            )
            fig_fc.add_trace(
                go.Scatter(
                    x=fut_part["week_start"],
                    y=fut_part["predicted_qty"],
                    mode="lines+markers",
                    name="Dự báo 4 tuần tới (Future Forecast)",
                    line=dict(color="#2ca02c", width=3),
                )
            )
            fig_fc.update_layout(
                title=f"Chuỗi thời gian & Dự báo nhu cầu theo tuần — {chosen_cat}",
                xaxis_title="Tuần bắt đầu (Thứ Hai)",
                yaxis_title="Số lượng bán (Gross Qty)",
                hovermode="x unified",
            )
            st.plotly_chart(fig_fc, use_container_width=True)

        st.divider()
        st.subheader("2. Tín hiệu Hỗ trợ Kế hoạch Tồn kho (4 Tuần Tới)")
        st.warning(
            "Miễn trừ trách nhiệm nghiệp vụ: Các cảnh báo dưới đây được tính toán dựa trên quy tắc phân tích của dự án "
            "(so sánh tổng nhu cầu dự báo 4 tuần tới từ mô hình ML với lượng tồn kho hiện hành), mang tính chất tham khảo "
            "hỗ trợ quyết định và không tự động tạo đơn đặt hàng."
        )

        safety_factor = st.slider(
            "Hệ số dự phòng an toàn (Safety Buffer Multiplier cho nhu cầu 4 tuần tới):",
            min_value=0.8,
            max_value=2.0,
            value=1.0,
            step=0.1,
        )

        future_4w = (
            df_forecast[df_forecast["split_type"] == "FORECAST_FUTURE"]
            .groupby(["product_division", "product_category"], as_index=False)["predicted_qty"]
            .sum()
            .rename(columns={"predicted_qty": "forecast_demand_4w"})
        )
        inv_by_cat = (
            df_inv.groupby(["product_division", "product_category"], as_index=False)["qty_on_hand"]
            .sum()
            .rename(columns={"qty_on_hand": "current_on_hand_qty"})
        )

        decision_df = future_4w.merge(inv_by_cat, on=["product_division", "product_category"], how="left")
        decision_df["current_on_hand_qty"] = decision_df["current_on_hand_qty"].fillna(0).astype(int)
        decision_df["required_stock_target"] = (decision_df["forecast_demand_4w"] * safety_factor).round(1)
        decision_df["net_inventory_gap"] = (
            decision_df["current_on_hand_qty"] - decision_df["required_stock_target"]
        ).round(1)

        def classify_alert(row):
            if row["current_on_hand_qty"] < row["required_stock_target"]:
                return "⚠️ Nguy cơ thiếu hàng (Cần xem xét bổ sung)"
            if row["forecast_demand_4w"] > 0 and row["current_on_hand_qty"] >= row["forecast_demand_4w"] * 3.0:
                return "📦 Tồn kho cao (Tồn >= 3x nhu cầu 4 tuần)"
            return "✅ Cân đối (Đủ đáp ứng nhu cầu)"

        decision_df["decision_signal"] = decision_df.apply(classify_alert, axis=1)
        decision_df = decision_df.sort_values("net_inventory_gap", ascending=True)

        st.dataframe(decision_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
    