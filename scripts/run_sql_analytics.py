import os
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

VIEWS_PATH = Path("database/views/02_create_analytics_views.sql")
QUERIES_PATH = Path("database/analytics/03_olap_queries.sql")


def get_engine():
    load_dotenv()
    user = os.getenv("MYSQL_USER", "root")
    pwd = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    db = os.getenv("MYSQL_DATABASE", "retail_dw")
    return create_engine(f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4", future=True)


def parse_sql_statements(file_path: Path) -> list[str]:
    raw_sql = file_path.read_text(encoding="utf-8")
    clean_lines = [line for line in raw_sql.splitlines() if not line.strip().startswith("--")]
    return [stmt.strip() for stmt in "\n".join(clean_lines).split(";") if stmt.strip()]


def main() -> None:
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1000)

    engine = get_engine()

    # 1. Tạo các Semantic Views
    print("Đang tạo các Semantic Views...")
    with engine.begin() as conn:
        for stmt in parse_sql_statements(VIEWS_PATH):
            conn.execute(text(stmt))
    print("Đã tạo thành công vw_daily_product_sales, vw_current_inventory, vw_weekly_product_sales.\n")

    # 2. Thực thi và in kết quả các truy vấn OLAP
    raw_queries = QUERIES_PATH.read_text(encoding="utf-8")
    blocks = raw_queries.split("-- [Q")
    for block in blocks[1:]:
        header_line, sql_body = block.split("\n", 1)
        title = "[Q" + header_line.strip()
        clean_lines = [l for l in sql_body.splitlines() if not l.strip().startswith("--")]
        stmt = "\n".join(clean_lines).strip().rstrip(";")
        if not stmt:
            continue

        print("=" * 90)
        print(f"KẾT QUẢ TRUY VẤN: {title}")
        print("=" * 90)
        df_res = pd.read_sql(text(stmt), engine)
        print(df_res.to_string(index=False))
        print()

    engine.dispose()


if __name__ == "__main__":
    main()
    