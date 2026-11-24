import logging
import os
import zipfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Thiết lập logging hiển thị tiếng Việt rõ ràng
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("retail_dw_etl")

SALES_ENTRY = "Retail Transactions and Stocks Data/retail_sales_ml_apl.csv"
INVENTORY_ENTRY = "Retail Transactions and Stocks Data/retail_inventory_ml_apl.csv"
DDL_PATH = Path("database/ddl/01_create_schema.sql")


def get_db_config() -> dict:
    load_dotenv()
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "retail_dw_str1006"),
        "store_id": os.getenv("TARGET_STORE_ID", "STR-1006"),
        "zip_path": Path(os.getenv("RAW_ZIP_PATH", "data/raw/retail-transactions-and-stocks-data.zip")),
    }


def create_mysql_engine(cfg: dict, include_db: bool = True):
    encoded_pwd = quote_plus(cfg["password"])
    db_part = f"/{cfg['database']}" if include_db else ""
    conn_str = (
        f"mysql+pymysql://{cfg['user']}:{encoded_pwd}@"
        f"{cfg['host']}:{cfg['port']}{db_part}?charset=utf8mb4"
    )
    return create_engine(conn_str, future=True)


def execute_ddl(cfg: dict) -> None:
    logger.info("Bước 1: Khởi tạo cơ sở dữ liệu và cấu trúc bảng từ %s...", DDL_PATH)
    if not DDL_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy file DDL: {DDL_PATH.resolve()}")

    raw_sql = DDL_PATH.read_text(encoding="utf-8")
    # Loại bỏ dòng comment bắt đầu bằng -- trước khi tách câu lệnh
    clean_lines = [line for line in raw_sql.splitlines() if not line.strip().startswith("--")]
    statements = [stmt.strip() for stmt in "\n".join(clean_lines).split(";") if stmt.strip()]

    server_engine = create_mysql_engine(cfg, include_db=False)
    with server_engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    server_engine.dispose()
    logger.info("Hoàn tất khởi tạo schema '%s'.", cfg["database"])


def extract_and_load_staging(cfg: dict, engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger.info("Bước 2: Trích xuất dữ liệu nguồn từ ZIP và lọc Store = '%s'...", cfg["store_id"])
    zip_path = cfg["zip_path"]
    if not zip_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file ZIP nguồn: {zip_path.resolve()}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        with zf.open(SALES_ENTRY) as f_sales:
            df_sales_raw = pd.read_csv(f_sales)
        with zf.open(INVENTORY_ENTRY) as f_inv:
            df_inv_raw = pd.read_csv(f_inv)

    # Lọc đúng cửa hàng duy nhất đã chốt (STR-1006)
    df_sales = df_sales_raw[df_sales_raw["Store"] == cfg["store_id"]].copy()
    df_inv = df_inv_raw[df_inv_raw["Store"] == cfg["store_id"]].copy()

    logger.info(
        "Đã lọc dữ liệu %s: Sales = %d dòng | Inventory = %d dòng.",
        cfg["store_id"],
        len(df_sales),
        len(df_inv),
    )

    # Chuẩn hóa tên cột snake_case để nạp vào bảng Staging
    stg_sales = df_sales.rename(
        columns={
            "Transaction Date": "transaction_date",
            "Sales Type": "sales_type",
            "Is Return": "is_return",
            "Reason of Return": "reason_of_return",
            "Supplier": "supplier",
            "Product No": "product_no",
            "Product Description": "product_description",
            "Product Division": "product_division",
            "Product Category": "product_category",
            "Product Subcategory": "product_subcategory",
            "Product Segment": "product_segment",
            "Store": "store",
            "Sales Channel": "sales_channel",
            "Qty Sold": "qty_sold",
            "Sales Amount": "sales_amount",
            "Cogs": "cogs",
            "Number of Transactions": "number_of_transactions",
        }
    )

    stg_inv = df_inv.rename(
        columns={
            "Start Date": "start_date",
            "End Date": "end_date",
            "Stock Status": "stock_status",
            "Supplier": "supplier",
            "Product No": "product_no",
            "Product Description": "product_description",
            "Product Division": "product_division",
            "Product Category": "product_category",
            "Product Subcategory": "product_subcategory",
            "Product Segment": "product_segment",
            "Store": "store",
            "Store Type": "store_type",
            "Sales Channel": "sales_channel",
            "Qty on hand": "qty_on_hand",
            "Stocks Selling Amount": "stocks_selling_amount",
            "Cost of Stocks": "cost_of_stocks",
            "Stock Unit Selling Price": "stock_unit_selling_price",
            "Stock Unit Cost Price": "stock_unit_cost_price",
        }
    )

    stg_sales.to_sql("stg_sales", con=engine, if_exists="append", index=False, chunksize=1000)
    stg_inv.to_sql("stg_inventory", con=engine, if_exists="append", index=False, chunksize=1000)
    logger.info("Đã nạp xong dữ liệu vào bảng stg_sales và stg_inventory.")
    return stg_sales, stg_inv


def build_dim_date(stg_sales: pd.DataFrame, stg_inv: pd.DataFrame, engine) -> None:
    logger.info("Bước 3.1: Xây dựng bảng dim_date (bao gồm ngày sentinel 9999-12-31)...")
    sales_dates = pd.to_datetime(stg_sales["transaction_date"])
    inv_start_dates = pd.to_datetime(stg_inv["start_date"])
    inv_end_valid = pd.to_datetime(stg_inv.loc[stg_inv["end_date"] != "9999-12-31", "end_date"])

    min_dt = min(sales_dates.min(), inv_start_dates.min()).date()
    max_dt = max(sales_dates.max(), inv_end_valid.max()).date()

    records = []
    curr = min_dt
    while curr <= max_dt:
        iso_week = curr.isocalendar()[1]
        dow = curr.isoweekday()  # 1 = Monday, 7 = Sunday
        records.append(
            {
                "date_key": int(curr.strftime("%Y%m%d")),
                "full_date": curr,
                "year": curr.year,
                "quarter": (curr.month - 1) // 3 + 1,
                "month": curr.month,
                "month_name": curr.strftime("%B"),
                "week_of_year": iso_week,
                "day_of_week": dow,
                "day_name": curr.strftime("%A"),
                "is_weekend": 1 if dow in (6, 7) else 0,
                "is_sentinel": 0,
            }
        )
        curr += timedelta(days=1)

    # Thêm bản ghi sentinel 9999-12-31 cho các bản ghi Inventory đang còn hiệu lực
    records.append(
        {
            "date_key": 99991231,
            "full_date": date(9999, 12, 31),
            "year": 9999,
            "quarter": 4,
            "month": 12,
            "month_name": "December",
            "week_of_year": 52,
            "day_of_week": 5,
            "day_name": "Friday",
            "is_weekend": 0,
            "is_sentinel": 1,
        }
    )

    df_dim_date = pd.DataFrame(records)
    df_dim_date.to_sql("dim_date", con=engine, if_exists="append", index=False, chunksize=1000)
    logger.info("Đã nạp %d bản ghi vào dim_date (%s -> %s + sentinel).", len(df_dim_date), min_dt, max_dt)


def build_other_dimensions(stg_sales: pd.DataFrame, stg_inv: pd.DataFrame, engine) -> None:
    logger.info("Bước 3.2: Xây dựng dim_product, dim_store, dim_supplier, dim_sales_type...")

    # 1. dim_product: Hợp nhất từ cả Sales và Inventory, loại bỏ trùng lặp theo product_no
    prod_cols = [
        "product_no",
        "product_description",
        "product_division",
        "product_category",
        "product_subcategory",
        "product_segment",
    ]
    df_prod = pd.concat([stg_sales[prod_cols], stg_inv[prod_cols]], ignore_index=True)
    for col in prod_cols:
        df_prod[col] = df_prod[col].fillna("Unknown").astype(str).str.strip()
    df_prod = df_prod.drop_duplicates(subset=["product_no"], keep="first").sort_values("product_no")
    df_prod.to_sql("dim_product", con=engine, if_exists="append", index=False, chunksize=1000)

    # 2. dim_store
    store_code = stg_inv["store"].iloc[0]
    store_type = stg_inv["store_type"].iloc[0]
    sales_channel = stg_inv["sales_channel"].iloc[0]
    df_store = pd.DataFrame(
        [{"store_code": store_code, "store_type": store_type, "sales_channel": sales_channel}]
    )
    df_store.to_sql("dim_store", con=engine, if_exists="append", index=False)

    # 3. dim_supplier: Hợp nhất từ cả Sales và Inventory
    suppliers = pd.concat([stg_sales["supplier"], stg_inv["supplier"]], ignore_index=True)
    df_supplier = (
        pd.DataFrame({"supplier_name": suppliers.fillna("Unknown").astype(str).str.strip().unique()})
        .sort_values("supplier_name")
    )
    df_supplier.to_sql("dim_supplier", con=engine, if_exists="append", index=False)

    # 4. dim_sales_type
    sales_types = stg_sales["sales_type"].fillna("Unknown").astype(str).str.strip().unique()
    st_records = []
    for st_name in sorted(sales_types):
        group = "Full Price" if st_name == "Full Price" else "Discounted"
        st_records.append({"sales_type_name": st_name, "sales_type_group": group})
    df_sales_type = pd.DataFrame(st_records)
    df_sales_type.to_sql("dim_sales_type", con=engine, if_exists="append", index=False)

    logger.info(
        "Đã nạp Dimensions: %d sản phẩm | %d cửa hàng | %d nhà cung cấp | %d loại bán hàng.",
        len(df_prod),
        len(df_store),
        len(df_supplier),
        len(df_sales_type),
    )


def load_facts(stg_sales: pd.DataFrame, stg_inv: pd.DataFrame, engine) -> None:
    logger.info("Bước 4: Tra cứu Surrogate Keys và nạp dữ liệu vào fact_sales & fact_inventory_interval...")

    # Đọc bảng ánh xạ Natural Key -> Surrogate Key từ MySQL
    prod_map = pd.read_sql("SELECT product_no, product_sk FROM dim_product", engine).set_index("product_no")["product_sk"].to_dict()
    store_map = pd.read_sql("SELECT store_code, store_sk FROM dim_store", engine).set_index("store_code")["store_sk"].to_dict()
    supp_map = pd.read_sql("SELECT supplier_name, supplier_sk FROM dim_supplier", engine).set_index("supplier_name")["supplier_sk"].to_dict()
    stype_map = pd.read_sql("SELECT sales_type_name, sales_type_sk FROM dim_sales_type", engine).set_index("sales_type_name")["sales_type_sk"].to_dict()

    # Kiểm tra giả định số nguyên của qty_sold và qty_on_hand trước khi ép kiểu INT
    if (stg_sales["qty_sold"] % 1 != 0).any() or (stg_inv["qty_on_hand"] % 1 != 0).any():
        raise ValueError("Phát hiện giá trị thập phân trong qty_sold hoặc qty_on_hand! Cần đổi cột Fact sang DECIMAL.")

    # --- Chuẩn bị fact_sales ---
    df_fs = pd.DataFrame()
    df_fs["transaction_date_key"] = pd.to_datetime(stg_sales["transaction_date"]).dt.strftime("%Y%m%d").astype(int)
    df_fs["product_sk"] = stg_sales["product_no"].str.strip().map(prod_map)
    df_fs["store_sk"] = stg_sales["store"].str.strip().map(store_map)
    df_fs["supplier_sk"] = stg_sales["supplier"].str.strip().map(supp_map)
    df_fs["sales_type_sk"] = stg_sales["sales_type"].str.strip().map(stype_map)
    df_fs["is_return"] = stg_sales["is_return"].astype(int)

    # Chuẩn hóa NULL hợp lệ của reason_of_return khi is_return = 0
    reasons = stg_sales["reason_of_return"].fillna("Not Applicable").astype(str).str.strip()
    reasons = reasons.replace({"": "Not Applicable", "nan": "Not Applicable", "None": "Not Applicable"})
    df_fs["reason_of_return"] = reasons

    df_fs["qty_sold"] = stg_sales["qty_sold"].round().astype(int)
    df_fs["sales_amount"] = stg_sales["sales_amount"]
    df_fs["cogs"] = stg_sales["cogs"]
    df_fs["number_of_transactions"] = stg_sales["number_of_transactions"].astype(int)

    if df_fs[["product_sk", "store_sk", "supplier_sk", "sales_type_sk"]].isna().any().any():
        raise ValueError("Lỗi ánh xạ Surrogate Key trong fact_sales (phát hiện NULL FK)!")

    df_fs.to_sql("fact_sales", con=engine, if_exists="append", index=False, chunksize=1000)
    logger.info("Đã nạp %d dòng vào fact_sales.", len(df_fs))

    # --- Chuẩn bị fact_inventory_interval ---
    df_fi = pd.DataFrame()
    df_fi["start_date_key"] = pd.to_datetime(stg_inv["start_date"]).dt.strftime("%Y%m%d").astype(int)
    df_fi["end_date_key"] = stg_inv["end_date"].astype(str).str.strip().str.replace("-", "").astype(int)
    df_fi["product_sk"] = stg_inv["product_no"].str.strip().map(prod_map)
    df_fi["store_sk"] = stg_inv["store"].str.strip().map(store_map)
    df_fi["supplier_sk"] = stg_inv["supplier"].str.strip().map(supp_map)
    df_fi["stock_status"] = stg_inv["stock_status"].fillna("Unknown").astype(str).str.strip()
    df_fi["is_current"] = (stg_inv["end_date"].astype(str).str.strip() == "9999-12-31").astype(int)
    df_fi["qty_on_hand"] = stg_inv["qty_on_hand"].round().astype(int)
    df_fi["stocks_selling_amount"] = stg_inv["stocks_selling_amount"]
    df_fi["cost_of_stocks"] = stg_inv["cost_of_stocks"]
    df_fi["stock_unit_selling_price"] = stg_inv["stock_unit_selling_price"]
    df_fi["stock_unit_cost_price"] = stg_inv["stock_unit_cost_price"]

    if df_fi[["product_sk", "store_sk", "supplier_sk"]].isna().any().any():
        raise ValueError("Lỗi ánh xạ Surrogate Key trong fact_inventory_interval (phát hiện NULL FK)!")

    df_fi.to_sql("fact_inventory_interval", con=engine, if_exists="append", index=False, chunksize=1000)
    logger.info("Đã nạp %d dòng vào fact_inventory_interval.", len(df_fi))


def run_reconciliation(engine) -> None:
    logger.info("Bước 5: Đối soát số liệu (Reconciliation) giữa Staging và Data Warehouse...")
    with engine.connect() as conn:
        sales_check = conn.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM stg_sales) AS stg_rows,
                    (SELECT COUNT(*) FROM fact_sales) AS dw_rows,
                    (SELECT ROUND(SUM(qty_sold), 2) FROM stg_sales) AS stg_qty,
                    (SELECT ROUND(SUM(qty_sold), 2) FROM fact_sales) AS dw_qty,
                    (SELECT ROUND(SUM(sales_amount), 4) FROM stg_sales) AS stg_sales_amt,
                    (SELECT ROUND(SUM(sales_amount), 4) FROM fact_sales) AS dw_sales_amt,
                    (SELECT ROUND(SUM(cogs), 4) FROM stg_sales) AS stg_cogs,
                    (SELECT ROUND(SUM(cogs), 4) FROM fact_sales) AS dw_cogs,
                    (SELECT SUM(number_of_transactions) FROM stg_sales) AS stg_tx,
                    (SELECT SUM(number_of_transactions) FROM fact_sales) AS dw_tx
                """
            )
        ).mappings().one()

        inv_check = conn.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM stg_inventory) AS stg_rows,
                    (SELECT COUNT(*) FROM fact_inventory_interval) AS dw_rows,
                    (SELECT ROUND(SUM(qty_on_hand), 2) FROM stg_inventory) AS stg_qty,
                    (SELECT ROUND(SUM(qty_on_hand), 2) FROM fact_inventory_interval) AS dw_qty,
                    (SELECT ROUND(SUM(cost_of_stocks), 4) FROM stg_inventory) AS stg_cost,
                    (SELECT ROUND(SUM(cost_of_stocks), 4) FROM fact_inventory_interval) AS dw_cost,
                    (SELECT COUNT(*) FROM stg_inventory WHERE end_date = '9999-12-31') AS stg_current_rows,
                    (SELECT COUNT(*) FROM fact_inventory_interval WHERE is_current = 1) AS dw_current_rows
                """
            )
        ).mappings().one()

    print("\n================ BÁO CÁO ĐỐI SOÁT DỮ LIỆU (RECONCILIATION) ================")
    print(f"[SALES]     Số dòng:      Staging = {sales_check['stg_rows']} | DW = {sales_check['dw_rows']}")
    print(f"[SALES]     Tổng Qty:     Staging = {sales_check['stg_qty']} | DW = {sales_check['dw_qty']}")
    print(f"[SALES]     Tổng Sales:   Staging = {sales_check['stg_sales_amt']} | DW = {sales_check['dw_sales_amt']}")
    print(f"[SALES]     Tổng COGS:    Staging = {sales_check['stg_cogs']} | DW = {sales_check['dw_cogs']}")
    print(f"[SALES]     Tổng Giao dịch: Staging = {sales_check['stg_tx']} | DW = {sales_check['dw_tx']}")
    print("-" * 75)
    print(f"[INVENTORY] Số dòng:      Staging = {inv_check['stg_rows']} | DW = {inv_check['dw_rows']}")
    print(f"[INVENTORY] Checksum Qty: Staging = {inv_check['stg_qty']} | DW = {inv_check['dw_qty']}")
    print(f"[INVENTORY] Checksum Cost:Staging = {inv_check['stg_cost']} | DW = {inv_check['dw_cost']}")
    print(f"[INVENTORY] Dòng hiện hành: Staging = {inv_check['stg_current_rows']} | DW = {inv_check['dw_current_rows']}")
    print("===========================================================================\n")

    assert sales_check["stg_rows"] == sales_check["dw_rows"], "Lệch số dòng Sales!"
    assert sales_check["stg_sales_amt"] == sales_check["dw_sales_amt"], "Lệch tổng Sales Amount!"
    assert inv_check["stg_rows"] == inv_check["dw_rows"], "Lệch số dòng Inventory!"
    assert inv_check["stg_current_rows"] == inv_check["dw_current_rows"], "Lệch số dòng hiện hành Inventory!"
    logger.info("KIỂM THỬ THÀNH CÔNG 100%: Toàn bộ số liệu Staging và Data Warehouse khớp tuyệt đối!")


def main() -> None:
    cfg = get_db_config()
    execute_ddl(cfg)
    dw_engine = create_mysql_engine(cfg, include_db=True)
    try:
        stg_sales, stg_inv = extract_and_load_staging(cfg, dw_engine)
        build_dim_date(stg_sales, stg_inv, dw_engine)
        build_other_dimensions(stg_sales, stg_inv, dw_engine)
        load_facts(stg_sales, stg_inv, dw_engine)
        run_reconciliation(dw_engine)
    finally:
        dw_engine.dispose()


if __name__ == "__main__":
    main()
    