import logging
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("master_pipeline")

PIPELINE_STEPS = [
    ("Giai đoạn 1: Kiểm kê & Profiling dữ liệu nguồn", "scripts/profile_dataset.py"),
    ("Giai đoạn 3: Chạy ETL & Nạp Data Warehouse (MySQL)", "etl/run_etl.py"),
    ("Giai đoạn 4: Khởi tạo Semantic Views & Truy vấn OLAP", "scripts/run_sql_analytics.py"),
    ("Giai đoạn 6: Huấn luyện ML & Dự báo nhu cầu tuần", "ml/run_forecasting.py"),
    ("Giai đoạn 8: Xuất phân tầng dữ liệu, Biểu đồ & Báo cáo MD", "scripts/generate_report.py"),
]


def main() -> None:
    start_all = time.time()
    logger.info("================ BẮT ĐẦU CHẠY PIPELINE TỔNG THỂ ================")

    for step_name, script_path in PIPELINE_STEPS:
        logger.info(">>> Đang thực thi: %s (%s)", step_name, script_path)
        t0 = time.time()
        result = subprocess.run([sys.executable, script_path], check=False)
        if result.returncode != 0:
            logger.error("LỖI tại bước '%s' (exit code %d). Dừng pipeline!", step_name, result.returncode)
            sys.exit(result.returncode)
        logger.info("<<< Hoàn tất '%s' trong %.2fs.\n", step_name, time.time() - t0)

    logger.info("================ HOÀN THÀNH TOÀN BỘ PIPELINE TRONG %.2fs ================", time.time() - start_all)
    logger.info("Kiểm tra kết quả tại:")
    logger.info("  - Tầng dữ liệu Staging:   data/staging/")
    logger.info("  - Tầng dữ liệu Processed: data/processed/")
    logger.info("  - Biểu đồ báo cáo (PNG):  reports/figures/")
    logger.info("  - Báo cáo tổng hợp (MD):  reports/final_project_report.md")
    logger.info("  - Khởi chạy BI Dashboard: python -m streamlit run bi/app.py")


if __name__ == "__main__":
    main()
    