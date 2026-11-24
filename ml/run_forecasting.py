import logging
import os
from datetime import timedelta
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("retail_dw_ml")


def get_engine():
    load_dotenv()
    user = os.getenv("MYSQL_USER", "root")
    pwd = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    db = os.getenv("MYSQL_DATABASE", "retail_dw")
    return create_engine(f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4", future=True)


def prepare_weekly_dataset(engine) -> pd.DataFrame:
    """
    Trích xuất dữ liệu bán hàng theo ngày và tổng hợp thành chuỗi thời gian tuần (Thứ 2 -> Chủ Nhật)
    cho các Product Category hoạt động liên tục.
    """
    logger.info("Bước 1: Trích xuất dữ liệu lịch sử bán hàng từ Data Warehouse...")
    query = """
        SELECT
            d.full_date,
            p.product_division,
            p.product_category,
            SUM(CASE WHEN f.is_return = 0 THEN f.qty_sold ELSE 0 END) AS gross_qty,
            AVG(CASE WHEN f.is_return = 0 AND f.qty_sold > 0 THEN f.sales_amount / f.qty_sold END) AS avg_unit_price,
            SUM(CASE WHEN f.is_return = 0 AND st.sales_type_group = 'Discounted' THEN f.qty_sold ELSE 0 END) AS discounted_qty
        FROM fact_sales f
        JOIN dim_date d ON f.transaction_date_key = d.date_key
        JOIN dim_product p ON f.product_sk = p.product_sk
        JOIN dim_sales_type st ON f.sales_type_sk = st.sales_type_sk
        GROUP BY d.full_date, p.product_division, p.product_category
    """
    df = pd.read_sql(text(query), engine)
    df["full_date"] = pd.to_datetime(df["full_date"])

    # Quy đổi mỗi ngày về ngày Thứ Hai đầu tuần (Monday-anchored week)
    df["week_start"] = df["full_date"] - pd.to_timedelta(df["full_date"].dt.weekday, unit="D")

    # Chỉ giữ các tuần trọn vẹn 7 ngày (2025-06-02 -> 2026-04-19 = 46 tuần trọn vẹn)
    full_weeks = pd.date_range(start="2025-06-02", end="2026-04-19", freq="7D")

    # Chọn các Category có lịch sử bán hàng đủ dày (tổng >= 100 sản phẩm bán ra)
    cat_totals = df.groupby(["product_division", "product_category"])["gross_qty"].sum().reset_index()
    active_cats = cat_totals[cat_totals["gross_qty"] >= 100][["product_division", "product_category"]]
    logger.info("Số danh mục (Product Category) đủ lịch sử để huấn luyện: %d danh mục.", len(active_cats))

    # Tạo lưới đầy đủ [Category x 46 tuần] để điền 0 cho tuần không phát sinh đơn (Zero-filling có kiểm soát)
    grid = active_cats.assign(key=1).merge(pd.DataFrame({"week_start": full_weeks, "key": 1}), on="key").drop("key", axis=1)

    weekly_agg = (
        df.groupby(["product_division", "product_category", "week_start"], as_index=False)
        .agg(
            actual_qty=("gross_qty", "sum"),
            avg_unit_price=("avg_unit_price", "mean"),
            discounted_qty=("discounted_qty", "sum"),
        )
    )

    panel = grid.merge(weekly_agg, on=["product_division", "product_category", "week_start"], how="left")
    panel["actual_qty"] = panel["actual_qty"].fillna(0.0)
    panel["discounted_qty"] = panel["discounted_qty"].fillna(0.0)
    panel["discount_share"] = np.where(panel["actual_qty"] > 0, panel["discounted_qty"] / panel["actual_qty"], 0.0)

    # Điền giá trung bình bằng ffill/bfill theo từng category
    panel = panel.sort_values(["product_category", "week_start"]).reset_index(drop=True)
    panel["avg_unit_price"] = panel.groupby("product_category")["avg_unit_price"].transform(lambda s: s.ffill().bfill())

    return panel


def create_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tạo đặc trưng thời gian và đặc trưng trễ CHỈ TỪ QUÁ KHỨ (sử dụng shift >= 1).
    """
    feat = df.copy().sort_values(["product_category", "week_start"]).reset_index(drop=True)

    # Đặc trưng thời gian (Calendar features)
    iso_cal = feat["week_start"].dt.isocalendar()
    feat["week_of_year"] = iso_cal.week.astype(int)
    feat["month"] = feat["week_start"].dt.month
    feat["quarter"] = feat["week_start"].dt.quarter
    feat["sin_week"] = np.sin(2 * np.pi * feat["week_of_year"] / 52.0)
    feat["cos_week"] = np.cos(2 * np.pi * feat["week_of_year"] / 52.0)

    # Đặc trưng trễ (Lag features - tuyệt đối dùng shift >= 1 để chống data leakage)
    grp = feat.groupby("product_category")["actual_qty"]
    feat["lag_1"] = grp.shift(1)
    feat["lag_2"] = grp.shift(2)
    feat["lag_3"] = grp.shift(3)
    feat["lag_4"] = grp.shift(4)

    # Trung bình trượt & độ lệch chuẩn 4 tuần quá khứ (shift(1) trước khi rolling)
    feat["rolling_mean_4w"] = grp.transform(lambda s: s.shift(1).rolling(4, min_periods=1).mean())
    feat["rolling_std_4w"] = grp.transform(lambda s: s.shift(1).rolling(4, min_periods=1).std()).fillna(0.0)
    feat["prev_discount_share"] = feat.groupby("product_category")["discount_share"].shift(1).fillna(0.0)
    feat["prev_unit_price"] = feat.groupby("product_category")["avg_unit_price"].shift(1).bfill()

    # Mã hóa Category thành biến số
    feat["category_code"] = feat["product_category"].astype("category").cat.codes

    return feat


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = mean_absolute_error(y_true, y_pred)
    rmse = root_mean_squared_error(y_true, y_pred)
    wape = (np.sum(np.abs(y_true - y_pred)) / np.sum(y_true) * 100.0) if np.sum(y_true) > 0 else np.nan
    return {"MAE": round(float(mae), 3), "RMSE": round(float(rmse), 3), "WAPE_pct": round(float(wape), 2)}


def recursive_future_forecast(
    history_panel: pd.DataFrame, model, feature_cols: list[str], horizon_weeks: int = 4
) -> pd.DataFrame:
    """
    Dự báo cuốn chiếu (Recursive Forecasting) cho 4 tuần tương lai sau tuần cuối cùng của dữ liệu.
    """
    sim_df = history_panel.copy()
    last_week = sim_df["week_start"].max()
    categories = sim_df[["product_division", "product_category", "avg_unit_price"]].drop_duplicates("product_category")

    future_rows = []
    for step in range(1, horizon_weeks + 1):
        next_week = last_week + timedelta(days=7 * step)
        step_grid = categories.copy()
        step_grid["week_start"] = next_week
        step_grid["actual_qty"] = np.nan
        step_grid["discounted_qty"] = 0.0
        step_grid["discount_share"] = 0.0

        temp_panel = pd.concat([sim_df, step_grid], ignore_index=True)
        temp_feat = create_features(temp_panel)
        target_slice = temp_feat[temp_feat["week_start"] == next_week].copy()

        preds = np.maximum(0.0, model.predict(target_slice[feature_cols]))
        target_slice["actual_qty"] = np.round(preds, 2)
        target_slice["predicted_qty"] = np.round(preds, 2)

        # Cập nhật lại vào sim_df để làm lag cho tuần kế tiếp
        sim_df = pd.concat(
            [sim_df, target_slice[["product_division", "product_category", "week_start", "actual_qty", "avg_unit_price", "discounted_qty", "discount_share"]]],
            ignore_index=True,
        )
        future_rows.append(target_slice[["product_division", "product_category", "week_start", "predicted_qty"]])

    res = pd.concat(future_rows, ignore_index=True)
    res["split_type"] = "FORECAST_FUTURE"
    res["actual_qty"] = np.nan
    return res


def main() -> None:
    engine = get_engine()
    panel = prepare_weekly_dataset(engine)
    feat_df = create_features(panel)

    # Loại bỏ 4 tuần đầu tiên chưa đủ lag_4 để huấn luyện công bằng
    model_df = feat_df.dropna(subset=["lag_4"]).copy()

    # Chia tập theo thời gian (Temporal Split): 8 tuần cuối làm Test Set
    unique_weeks = sorted(model_df["week_start"].unique())
    split_week = unique_weeks[-8]
    train_df = model_df[model_df["week_start"] < split_week].copy()
    test_df = model_df[model_df["week_start"] >= split_week].copy()

    logger.info(
        "Bước 2: Chia tập theo thời gian (Temporal Split) | Train: %d tuần (< %s) | Test: %d tuần (>= %s).",
        train_df["week_start"].nunique(),
        str(split_week.date()),
        test_df["week_start"].nunique(),
        str(split_week.date()),
    )

    feature_cols = [
        "category_code",
        "week_of_year",
        "month",
        "quarter",
        "sin_week",
        "cos_week",
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_4",
        "rolling_mean_4w",
        "rolling_std_4w",
        "prev_discount_share",
        "prev_unit_price",
    ]

    X_train, y_train = train_df[feature_cols], train_df["actual_qty"].values
    X_test, y_test = test_df[feature_cols], test_df["actual_qty"].values

    # 1. Đánh giá Baseline Models trên tập Test
    metrics_list = []

    pred_naive = test_df["lag_1"].values
    metrics_list.append({"model_name": "Baseline 1: Naive (Last Week)", **compute_metrics(y_test, pred_naive)})

    pred_ma4 = test_df["rolling_mean_4w"].values
    metrics_list.append({"model_name": "Baseline 2: 4-Week Moving Avg", **compute_metrics(y_test, pred_ma4)})

    # 2. Huấn luyện các mô hình Machine Learning
    rf_model = RandomForestRegressor(n_estimators=200, max_depth=8, min_samples_leaf=3, random_state=42)
    rf_model.fit(X_train, y_train)
    pred_rf = np.maximum(0.0, rf_model.predict(X_test))
    metrics_list.append({"model_name": "ML 1: Random Forest Regressor", **compute_metrics(y_test, pred_rf)})

    gb_model = GradientBoostingRegressor(n_estimators=150, learning_rate=0.05, max_depth=4, random_state=42)
    gb_model.fit(X_train, y_train)
    pred_gb = np.maximum(0.0, gb_model.predict(X_test))
    metrics_list.append({"model_name": "ML 2: Gradient Boosting Regressor", **compute_metrics(y_test, pred_gb)})

    metrics_df = pd.DataFrame(metrics_list).sort_values("MAE").reset_index(drop=True)
    print("\n================ KẾT QUẢ ĐÁNH GIÁ MÔ HÌNH TRÊN TẬP TEST (8 TUẦN CUỐI) ================")
    print(metrics_df.to_string(index=False))
    print("======================================================================================\n")

    # Chọn mô hình ML tốt nhất (có MAE thấp nhất giữa RF và GB)
    ml_only = metrics_df[metrics_df["model_name"].str.startswith("ML")]
    best_model_name = ml_only.iloc[0]["model_name"]
    best_model = rf_model if "Random Forest" in best_model_name else gb_model
    logger.info("Bước 3: Chọn mô hình chính '%s' để tái huấn luyện toàn bộ dữ liệu và dự báo 4 tuần tới...", best_model_name)

    # Tạo bảng kết quả trên tập Test để vẽ biểu đồ Actual vs Predicted
    test_out = test_df[["product_division", "product_category", "week_start", "actual_qty"]].copy()
    test_out["predicted_qty"] = np.round(pred_rf if "Random Forest" in best_model_name else pred_gb, 2)
    test_out["split_type"] = "TEST_BACKTEST"

    # Tái huấn luyện trên toàn bộ dữ liệu lịch sử để dự báo 4 tuần tương lai
    best_model.fit(model_df[feature_cols], model_df["actual_qty"].values)
    future_out = recursive_future_forecast(panel, best_model, feature_cols, horizon_weeks=4)

    # Kết hợp dữ liệu lịch sử Train + Test + Future Forecast để lưu vào MySQL
    train_out = train_df[["product_division", "product_category", "week_start", "actual_qty"]].copy()
    train_out["predicted_qty"] = np.nan
    train_out["split_type"] = "TRAIN_HISTORY"

    final_forecast_df = pd.concat([train_out, test_out, future_out], ignore_index=True)
    final_forecast_df["model_used"] = best_model_name

    # Lưu kết quả vào MySQL
    metrics_df.to_sql("ml_model_metrics", con=engine, if_exists="replace", index=False)
    final_forecast_df.to_sql("ml_weekly_demand_forecast", con=engine, if_exists="replace", index=False)
    logger.info(
        "Bước 4: Đã lưu kết quả ML vào MySQL (bảng 'ml_model_metrics' và 'ml_weekly_demand_forecast': %d dòng).",
        len(final_forecast_df),
    )
    engine.dispose()


if __name__ == "__main__":
    main()
    