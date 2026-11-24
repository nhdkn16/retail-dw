import hashlib
import zipfile
from pathlib import Path
import pandas as pd

ZIP_PATH = Path("data/raw/retail-transactions-and-stocks-data.zip")
SALES_CSV = "Retail Transactions and Stocks Data/retail_sales_ml_apl.csv"
INV_CSV = "Retail Transactions and Stocks Data/retail_inventory_ml_apl.csv"


def get_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def run_profiling() -> None:
    if not ZIP_PATH.exists():
        print(f"Khong tim thay file ZIP tai: {ZIP_PATH.resolve()}")
        return

    print(f"SHA-256 ZIP: {get_sha256(ZIP_PATH)}")

    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        with zf.open(SALES_CSV) as f_sales:
            df_sales = pd.read_csv(f_sales)
        with zf.open(INV_CSV) as f_inv:
            df_inv = pd.read_csv(f_inv)

    print("\n--- TONG QUAN DU LIEU ---")
    print(f"Sales shape: {df_sales.shape} | Duplicate rows: {df_sales.duplicated().sum()}")
    print(f"Inventory shape: {df_inv.shape} | Duplicate rows: {df_inv.duplicated().sum()}")

    print("\n--- KIEM TRA QUY UOC TRA HANG (IS RETURN = 1) ---")
    returns_df = df_sales[df_sales["Is Return"] == 1]
    print(returns_df[["Qty Sold", "Sales Amount", "Cogs", "Number of Transactions"]].describe())

    print("\n--- SO SANH TOP 5 STORE ID ---")
    top_stores = df_sales["Store"].value_counts().head(5).index.tolist()
    for store_id in top_stores:
        s_sub = df_sales[df_sales["Store"] == store_id]
        i_sub = df_inv[df_inv["Store"] == store_id]
        s_skus = set(s_sub["Product No"].unique())
        i_skus = set(i_sub["Product No"].unique())
        overlap_pct = (len(s_skus & i_skus) / len(s_skus) * 100) if s_skus else 0

        print(
            f"Store: {store_id} | Sales rows: {len(s_sub)} | Inv rows: {len(i_sub)} | "
            f"Active days: {s_sub['Transaction Date'].nunique()} | "
            f"Sales SKUs: {len(s_skus)} | Inv SKUs: {len(i_skus)} | "
            f"SKU overlap: {overlap_pct:.1f}% | "
            f"Date range: {s_sub['Transaction Date'].min()} -> {s_sub['Transaction Date'].max()}"
        )


if __name__ == "__main__":
    run_profiling()
    