# Hệ thống Kho Dữ Liệu Phân Tích Doanh Số, Tồn Kho và Dự Báo Nhu Cầu Bán Lẻ (Store STR-1006)

## 1. Giới thiệu Dự án

Dự án xây dựng một giải pháp **Data Warehouse (Kho dữ liệu)** hoàn chỉnh ở quy mô cá nhân chạy trên môi trường Windows local, tích hợp từ khâu tiếp nhận dữ liệu thô, làm sạch và chuẩn hóa (ETL), thiết kế mô hình đa chiều (Dimensional Modeling), phân tích truy vấn OLAP, trực quan hóa Business Intelligence (BI) cho đến ứng dụng Machine Learning dự báo nhu cầu bán hàng và hỗ trợ ra quyết định tồn kho.

### Mục tiêu cốt lõi
1. **Data Warehouse & ETL:** Xây dựng quy trình ETL có khả năng chạy lại an toàn (idempotent), nạp dữ liệu vào mô hình **Constellation Schema (Galaxy Schema)** trên MySQL và đối soát tự động 100% số liệu với nguồn.
2. **SQL Analytics & OLAP:** Xây dựng tầng Semantic Views chuẩn hóa định nghĩa KPI và thực hiện các truy vấn phân tích đa chiều (`Roll-up`, `Drill-down`, `Slice`, `Dice`).
3. **Business Intelligence (BI):** Xây dựng ứng dụng Dashboard tương tác bằng **Streamlit** và **Plotly**, đối chiếu khớp số liệu với tầng SQL.
4. **Machine Learning & Hỗ trợ quyết định:** Xây dựng mô hình dự báo nhu cầu bán hàng theo tuần (`Weekly Demand Forecasting`) tuân thủ chia tập theo thời gian (`Temporal Split`), đánh giá định lượng với Baseline và kết hợp dữ liệu tồn kho hiện hành để đưa ra cảnh báo thiếu hàng/tồn cao.

---

## 2. Nguồn Dữ Liệu và Phạm Vi Nghiệp Vụ

* **Tên Dataset:** Retail Transactions and Stocks Data
* **Nguồn dữ liệu chính thức (Mendeley Data):** https://data.mendeley.com/datasets/27x8mjm8k4/1
* **Tệp dữ liệu đầu vào (`data/raw/`):** `retail-transactions-and-stocks-data.zip`
  * **Mã kiểm tra toàn vẹn (`SHA-256`):** `f65cb8ace7d2d7864986dde91ae658311cd334e5d6c742d3a9f9f8bfc9675480`
  * `retail_sales_ml_apl.csv`: 125.751 dòng, 17 cột (0 dòng trùng lặp).
  * `retail_inventory_ml_apl.csv`: 284.755 dòng, 18 cột (0 dòng trùng lặp).
* **Phạm vi nghiệp vụ:** Giới hạn phân tích trên **một cửa hàng duy nhất là `STR-1006`** (được lựa chọn qua bước Data Profiling vì có mật độ giao dịch cao nhất: **5.904 dòng Sales** và **11.142 dòng Inventory**, 323 ngày hoạt động từ `2025-06-01` đến `2026-04-24`, tỷ lệ khớp mã SKU giữa hai bảng đạt **95,0%**).
* **Kênh bán hàng & Loại hình cửa hàng:** Kênh `Channel Alpha`, mô hình `Retail Storefront`.
* **Các quy tắc dữ liệu đã xác minh và xử lý:**
  1. **Quy ước hàng trả lại (`Is Return = 1`):** Các thước đo `Qty Sold`, `Sales Amount` và `Cogs` trên dòng trả hàng đã mang **dấu âm sẵn** từ nguồn. Do đó, phép cộng tổng `SUM()` trực tiếp cho ra giá trị thuần (`Net Sales`, `Net Qty`, `Net Cogs`). Riêng số lượt mua hàng (`Purchase Transactions`) được lọc điều kiện `is_return = 0`.
  2. **Grain của bảng Sales vs Inventory:** `fact_sales` lưu dữ liệu tổng hợp theo tổ hợp chiều trong ngày (Fully Additive), trong khi `fact_inventory_interval` lưu trạng thái tồn kho theo khoảng thời gian hiệu lực `Start Date` – `End Date` (Semi-Additive). Hai bảng không được `JOIN` trực tiếp mà xử lý độc lập qua CTE hoặc truy vấn theo thời điểm (`As-Of Date`) để tránh nhân bản dữ liệu (fan-out).
  3. **Ngày Sentinel (`9999-12-31`):** Biểu thị bản ghi tồn kho đang còn hiệu lực tại thời điểm chốt dữ liệu (`is_current = 1`).

---

## 3. Kiến trúc Phân tầng Dữ liệu & Mô hình Kho Dữ liệu

### Luồng xử lý dữ liệu (End-to-End Pipeline)
```text
Tầng 1: RAW DATA (data/raw/retail-transactions-and-stocks-data.zip - Bất biến)
       │
       ▼  [etl/run_etl.py]
Tầng 2: STAGING (data/staging/*.csv & MySQL stg_sales, stg_inventory)
       │
       ▼  Làm sạch, chuẩn hóa & ánh xạ Surrogate Key
Tầng 3: CORE DATA WAREHOUSE (MySQL retail_dw - Constellation Schema)
  ├── Conformed Dimensions: dim_date, dim_product, dim_store, dim_supplier, dim_sales_type
  └── Fact Tables: fact_sales, fact_inventory_interval
       │
       ├──────────────────────────────────────┐
       ▼                                      ▼
Tầng 4A: SEMANTIC VIEWS & PROCESSED     Tầng 4B: MACHINE LEARNING FORECASTING
(vw_daily_product_sales,                (ml/run_forecasting.py:
 vw_current_inventory,                   Feature Engineering -> Temporal Split
 vw_weekly_product_sales,                -> Random Forest / Gradient Boosting
 data/processed/mart_*.csv)              -> ml_model_metrics, ml_weekly_demand_forecast)
       │                                      │
       └──────────────────┬───────────────────┘
                          ▼
Tầng 5: CONSUMPTION & REPORTING
  ├── BI Dashboard tương tác: bi/app.py (Streamlit + Plotly)
  └── Báo cáo tổng hợp & Biểu đồ tĩnh: reports/final_project_report.md & reports/figures/*.png
```

### Danh mục bảng trong Database `retail_dw`

| Tên bảng / View | Loại | Mô tả & Grain |
| :--- | :--- | :--- |
| `stg_sales` | Staging | Bản sao thô dữ liệu bán hàng của `STR-1006` (5.904 dòng). |
| `stg_inventory` | Staging | Bản sao thô dữ liệu tồn kho của `STR-1006` (11.142 dòng). |
| `dim_date` | Dimension | 329 bản ghi ngày (`2025-06-01` đến `2026-04-24` + ngày sentinel `9999-12-31`). |
| `dim_product` | Dimension | 2.068 sản phẩm hợp nhất từ Sales và Inventory (4 cấp phân loại). |
| `dim_store` | Dimension | Thông tin cửa hàng `STR-1006` (`Retail Storefront`, `Channel Alpha`). |
| `dim_supplier` | Dimension | 30 nhà cung cấp sản phẩm. |
| `dim_sales_type` | Dimension | 5 loại hình giá bán (`Full Price`, `Promo`, `Markdown Tier 1/2`, `Clearance`). |
| `fact_sales` | Fact | Grain: `[Ngày, Sản phẩm, Cửa hàng, NCC, Loại giá, Cờ trả hàng, Lý do trả]`. |
| `fact_inventory_interval` | Fact | Grain: `[Ngày bắt đầu, Ngày kết thúc, Sản phẩm, Cửa hàng, NCC, Trạng thái tồn]`. |
| `vw_daily_product_sales` | Semantic View | Tổng hợp doanh thu gộp, trả hàng, doanh thu thuần, giá vốn và lợi nhuận gộp theo ngày/sản phẩm. |
| `vw_current_inventory` | Semantic View | Trạng thái tồn kho hiện hành (`is_current = 1`). |
| `vw_weekly_product_sales` | Semantic View | Chuỗi thời gian bán hàng tổng hợp theo tuần ISO. |
| `ml_model_metrics` | ML Output | Bảng so sánh chỉ số `MAE`, `RMSE`, `WAPE_pct` giữa các mô hình trên tập Test. |
| `ml_weekly_demand_forecast` | ML Output | Chuỗi lịch sử, kết quả backtest 8 tuần cuối và dự báo nhu cầu 4 tuần tiếp theo. |

---

## 4. Cấu trúc Thư mục Dự án

```text
retail-dw/
├── Claude.md                                      # Tài liệu kế hoạch, quy tắc và ràng buộc dự án
├── README.md                                      # Tài liệu hướng dẫn cài đặt, chạy và nghiệm thu
├── requirements.txt                               # Danh sách thư viện Python phụ thuộc
├── .env.example                                   # File mẫu cấu hình biến môi trường kết nối MySQL
├── data/
│   ├── raw/
│   │   └── retail-transactions-and-stocks-data.zip # Gói dữ liệu nguồn gốc (không chỉnh sửa)
│   ├── staging/
│   │   ├── stg_sales_str1006.csv                  # Dữ liệu Staging Sales đã lọc STR-1006
│   │   └── stg_inventory_str1006.csv              # Dữ liệu Staging Inventory đã lọc STR-1006
│   └── processed/
│       ├── mart_daily_product_sales.csv           # Data Mart doanh số theo ngày & sản phẩm
│       ├── mart_current_inventory.csv             # Data Mart tồn kho hiện hành
│       └── mart_ml_weekly_forecast.csv            # Data Mart chuỗi thời gian & dự báo ML
├── database/
│   ├── ddl/
│   │   └── 01_create_schema.sql                   # Script SQL khởi tạo Database, Staging, Dim, Fact
│   ├── views/
│   │   └── 02_create_analytics_views.sql          # Script SQL tạo Semantic Views
│   └── analytics/
│       └── 03_olap_queries.sql                    # Bộ 8 truy vấn phân tích KPI và OLAP
├── etl/
│   └── run_etl.py                                 # Pipeline ETL và đối soát dữ liệu tự động
├── ml/
│   └── run_forecasting.py                         # Huấn luyện mô hình ML và sinh dự báo 4 tuần tới
├── bi/
│   └── app.py                                     # Ứng dụng Web Dashboard Streamlit (4 tab chức năng)
├── reports/
│   ├── final_project_report.md                    # Báo cáo tổng kết kỹ thuật tự động xuất từ dữ liệu thật
│   └── figures/                                   # Thư mục chứa 5 biểu đồ PNG (300 DPI) phục vụ báo cáo
└── scripts/
    ├── pipeline.py                                # Script điều phối chạy toàn bộ Pipeline từ đầu đến cuối
    ├── profile_dataset.py                         # Script kiểm kê và phân tích chất lượng dữ liệu gốc
    ├── run_sql_analytics.py                       # Script thực thi và in kết quả truy vấn SQL/OLAP
    └── generate_report.py                         # Script xuất phân tầng dữ liệu, vẽ biểu đồ & xuất báo cáo
```

---

## 5. Hướng dẫn Cài đặt và Vận hành (Windows)

### Yêu cầu hệ thống
* Hệ điều hành: Windows 10/11
* Python: Phiên bản `3.11` – `3.13`
* Hệ quản trị CSDL: MySQL Server `8.0+` đang hoạt động trên máy local

### Bước 1: Tạo môi trường ảo và cài đặt thư viện
Mở PowerShell tại thư mục gốc `retail-dw\` và chạy:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install matplotlib tabulate
```

### Bước 2: Cấu hình kết nối MySQL
Tạo file `.env` từ file mẫu `.env.example`:
```powershell
Copy-Item .env.example .env
```
Mở file `.env` và điều chỉnh thông số kết nối thực tế trên máy của bạn:
```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=mat_khau_mysql_cua_ban
MYSQL_DATABASE=retail_dw
TARGET_STORE_ID=STR-1006
RAW_ZIP_PATH=data/raw/retail-transactions-and-stocks-data.zip
```

### Bước 3: Chạy toàn bộ Pipeline tự động (Khuyến nghị)
Chạy một lệnh duy nhất từ thư mục gốc `retail-dw\` để thực thi tuần tự từ kiểm kê dữ liệu $\rightarrow$ nạp ETL & đối soát MySQL $\rightarrow$ tạo Semantic Views & truy vấn OLAP $\rightarrow$ huấn luyện mô hình ML $\rightarrow$ xuất dữ liệu phân tầng và báo cáo:
```powershell
python scripts/pipeline.py
```
*(Hoặc có thể chạy lẻ từng bước nếu cần kiểm thử riêng biệt: `scripts/profile_dataset.py` $\rightarrow$ `etl/run_etl.py` $\rightarrow$ `scripts/run_sql_analytics.py` $\rightarrow$ `ml/run_forecasting.py` $\rightarrow$ `scripts/generate_report.py`).*

### Bước 4: Khởi chạy BI Dashboard & Hệ thống Hỗ trợ Quyết định
```powershell
python -m streamlit run bi/app.py
```
Truy cập trình duyệt tại địa chỉ `http://localhost:8501` để tương tác với 4 phân hệ:
1. **Tổng quan Doanh số:** Theo dõi KPI chính, xu hướng doanh thu/lợi nhuận theo tháng, phân bổ theo thứ trong tuần và cơ cấu ngành hàng.
2. **Sản phẩm & Khuyến mãi:** Phân tích hiệu quả các mức giá bán (`Full Price`, `Promo`, `Markdown`, `Clearance`) và bảng xếp hạng danh mục/SKU.
3. **Quản trị Tồn kho:** Theo dõi số lượng tồn, giá trị vốn và giá trị bán lẻ tại trạng thái hiện hành (`is_current = 1`).
4. **Dự báo ML & Hỗ trợ Quyết định:** So sánh sai số mô hình với Baseline, xem biểu đồ dự báo nhu cầu 4 tuần tiếp theo và theo dõi tín hiệu cảnh báo thiếu hàng/tồn kho cao.

---

## 6. Tóm tắt Kết quả Thực nghiệm Đã Kiểm chứng

* **Chỉ số kinh doanh tổng hợp (`STR-1006`):**
  * Doanh thu gộp (`Gross Sales`): `514.665,31` | Giá trị trả hàng: `29.103,87` | Doanh thu thuần (`Net Sales`): `485.561,44`
  * Lợi nhuận gộp (`Gross Profit`): `225.775,14` (Biên lợi nhuận gộp: `43,87%`)
  * Sản lượng thuần (`Net Qty Sold`): `5.619` sản phẩm | Tỷ lệ trả hàng theo số lượng: `5,15%`
* **Hiệu năng mô hình dự báo nhu cầu (Tập kiểm thử 8 tuần cuối từ `2026-02-23` đến `2026-04-19`):**
  * `Random Forest Regressor`: **MAE = 3,750** | **RMSE = 5,029** | **WAPE = 48,24%** (tốt nhất, vượt qua cả hai Baseline).
  * `Gradient Boosting Regressor`: **MAE = 3,853** | **RMSE = 4,931** | **WAPE = 49,55%**.
  * `Baseline 1: Naive (Last Week)`: **MAE = 3,925** | **RMSE = 5,262** | **WAPE = 50,48%**.
  * `Baseline 2: 4-Week Moving Avg`: **MAE = 3,960** | **RMSE = 5,151** | **WAPE = 50,94%**.

---

## 7. Giới hạn và Lưu ý Nghiệp vụ

1. **Đơn vị tiền tệ:** Dataset nguồn không quy định đơn vị tiền tệ cụ thể (USD, EUR hay đơn vị giả định); toàn bộ báo cáo và dashboard giữ nguyên giá trị số gốc.
2. **Đơn vị dự báo ML:** Do mật độ bán ở cấp SKU đơn lẻ thấp (trung bình 1–2 sản phẩm/tuần đối với nhóm bán chạy), bài toán dự báo nhu cầu được thực hiện ở cấp **Danh mục sản phẩm (`Product Category`) theo tuần** để đảm bảo độ ổn định của chuỗi thời gian.
3. **Tín hiệu hỗ trợ quyết định:** Các ngưỡng cảnh báo thiếu hàng hoặc tồn kho cao trong Dashboard là quy tắc phân tích phục vụ tham khảo kế hoạch tồn kho, không thay thế chính sách đặt hàng vận hành thực tế.