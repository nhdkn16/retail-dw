# Claude.md --- Kế hoạch dự án Data Warehouse phân tích doanh số và tồn kho

> **Vai trò của file:** Tài liệu định hướng và quy định làm việc chính
> thức cho AI Agent tham gia dự án. Agent phải đọc toàn bộ file này
> trước khi phân tích dataset, đề xuất kiến trúc hoặc chỉnh sửa mã
> nguồn.
>
> **Tên đề tài:** Xây dựng kho dữ liệu phân tích doanh số và quản lý tồn
> kho nhằm dự báo nhu cầu hàng hóa trong bán lẻ.
>
> **Phiên bản tài liệu:** 1.0\
> **Trạng thái:** Đã chọn dataset; chưa bắt đầu triển khai.

------------------------------------------------------------------------

## 1. Tổng quan dự án

### 1.1. Mục tiêu

Xây dựng một dự án Data Warehouse ở quy mô cá nhân, sử dụng dữ liệu bán
lẻ để:

1.  Tích hợp và tổ chức dữ liệu bán hàng, sản phẩm và tồn kho trong một
    kho dữ liệu tập trung.
2.  Phân tích doanh số và tình trạng tồn kho bằng SQL/OLAP.
3.  Xây dựng dashboard BI để trình bày các chỉ số kinh doanh.
4.  Ứng dụng Machine Learning để dự báo nhu cầu bán hàng của sản phẩm.
5.  Trình bày kết quả dự báo và các tín hiệu hỗ trợ lập kế hoạch tồn
    kho.

Dự án phải thể hiện rõ vai trò của ba thành phần:

-   **Data Warehouse:** nền tảng tích hợp, làm sạch, lưu trữ và tổ chức
    dữ liệu phân tích.
-   **Business Intelligence (BI):** báo cáo, KPI, dashboard và phân tích
    đa chiều.
-   **Machine Learning (ML):** dự báo nhu cầu dựa trên dữ liệu lịch sử
    và đánh giá định lượng mô hình.

### 1.2. Quy mô và ranh giới

-   Quy mô triển khai: một cá nhân, một máy local.
-   Phạm vi nghiệp vụ: **một cửa hàng duy nhất** được lựa chọn từ
    dataset.
-   Không xây dựng hệ thống quản lý bán hàng/POS vận hành thực tế.
-   Không xây dựng ERP, hệ thống quản lý nhà cung cấp hoặc hệ thống đặt
    hàng tự động.
-   Không triển khai kiến trúc phân tán, microservices hoặc streaming
    nếu không có yêu cầu học thuật bắt buộc.
-   Không mở rộng sang phân tích khách hàng vì dataset hiện tại không có
    Customer ID.
-   Không giả định có nhiều kênh bán hàng để so sánh: dữ liệu hiện được
    kiểm tra chỉ có `Channel Alpha`.

### 1.3. Kết quả mong đợi

Khi hoàn thành, dự án cần có:

-   Dataset nguồn được kiểm tra và mô tả.
-   Quy trình ETL có thể chạy lại.
-   Data Warehouse với mô hình Fact/Dimension được giải thích rõ.
-   Bộ truy vấn SQL phục vụ phân tích.
-   Dashboard doanh số và tồn kho.
-   Mô hình dự báo nhu cầu, kết quả đánh giá và phần giải thích.
-   Tài liệu hướng dẫn cài đặt, chạy và kiểm thử.
-   Báo cáo mô tả quy trình, thiết kế, kết quả và giới hạn của dự án.

------------------------------------------------------------------------

## 2. Dataset được chọn và thông tin đã xác minh

### 2.1. Nguồn dữ liệu

Dataset: **Retail Transactions and Stocks Data**

Trang nguồn: https://data.mendeley.com/datasets/27x8mjm8k4/1

Dataset ZIP do người dùng cung cấp cho Agent:

`retail-transactions-and-stocks-data.zip`

Bên trong ZIP hiện có hai file CSV:

1.  `Retail Transactions and Stocks Data/retail_sales_ml_apl.csv`
2.  `Retail Transactions and Stocks Data/retail_inventory_ml_apl.csv`

**Không tải lại hoặc thay thế dataset bằng nguồn khác nếu chưa được
người dùng đồng ý.** File ZIP đính kèm là nguồn dữ liệu đầu vào chính
thức của dự án.

### 2.2. Kết quả kiểm tra sơ bộ từ file ZIP được cung cấp

Các thông tin sau đã được kiểm tra trực tiếp từ hai CSV trong file ZIP:

  -----------------------------------------------------------------------
  Thuộc tính                              Sales                 Inventory
  ------------------- ------------------------- -------------------------
  Số dòng                               125.751                   284.755

  Số cột                                     17                        18

  Ngày bắt đầu                       2025-06-01                2025-06-01

  Ngày kết thúc quan                 2026-04-24    `End Date` hợp lệ quan
  sát được                                         sát đến 2026-04-23; có
                                                  giá trị sentinel cần xử
                                                                       lý

  Số cửa hàng                                40                        40

  Số mã sản phẩm                          2.326                     2.326
  -----------------------------------------------------------------------

Thông tin bổ sung:

-   Sales có các loại `Full Price`, `Promo`, `Markdown Tier 1`,
    `Markdown Tier 2`, `Clearance`.
-   Sales có cột `Is Return`; dữ liệu sơ bộ ghi nhận 7.491 dòng có giá
    trị 1 và 118.260 dòng có giá trị 0.
-   Sales có cột `Sales Channel`, nhưng dữ liệu sơ bộ chỉ có một giá
    trị: `Channel Alpha`.
-   Inventory có `Store Type`, dữ liệu sơ bộ chỉ có `Retail Storefront`.
-   Inventory có `Start Date` và `End Date`; có 22.701 dòng chứa
    `End Date = 9999-12-31`. Đây có thể là mốc biểu diễn bản ghi còn
    hiệu lực, không được coi là ngày phát sinh giao dịch thông thường.
-   Một số cột như `Reason of Return` có thể trống đối với phần lớn hoặc
    toàn bộ bản ghi không phải hàng trả lại. Không được tự động coi các
    giá trị trống này là lỗi.

**Lưu ý:** Đây mới là kiểm tra cấu trúc và thống kê tổng quan. Agent
phải tự kiểm tra lại trên file được đính kèm, lưu kết quả profiling và
xác nhận các số liệu trước khi sử dụng chính thức.

### 2.3. Các cột nguồn

#### Sales --- `retail_sales_ml_apl.csv`

-   `Transaction Date`
-   `Sales Type`
-   `Is Return`
-   `Reason of Return`
-   `Supplier`
-   `Product No`
-   `Product Description`
-   `Product Division`
-   `Product Category`
-   `Product Subcategory`
-   `Product Segment`
-   `Store`
-   `Sales Channel`
-   `Qty Sold`
-   `Sales Amount`
-   `Cogs`
-   `Number of Transactions`

#### Inventory --- `retail_inventory_ml_apl.csv`

-   `Start Date`
-   `End Date`
-   `Stock Status`
-   `Supplier`
-   `Product No`
-   `Product Description`
-   `Product Division`
-   `Product Category`
-   `Product Subcategory`
-   `Product Segment`
-   `Store`
-   `Store Type`
-   `Sales Channel`
-   `Qty on hand`
-   `Stocks Selling Amount`
-   `Cost of Stocks`
-   `Stock Unit Selling Price`
-   `Stock Unit Cost Price`

### 2.4. Chọn một cửa hàng

Yêu cầu nghiệp vụ đã thống nhất: **toàn bộ phân tích chính phải giới hạn
trong một cửa hàng cụ thể**.

Thống kê sơ bộ theo số dòng Sales:

-   `STR-1006`: 5.904 dòng Sales; 11.142 dòng Inventory.
-   `STR-1198`: 4.995 dòng Sales; 11.582 dòng Inventory.
-   `STR-1010`: 4.916 dòng Sales; 9.992 dòng Inventory.

`STR-1006` là ứng viên ban đầu vì có số dòng Sales cao nhất trong thống
kê sơ bộ và dữ liệu Inventory tương đối lớn. Tuy nhiên:

-   Đây **chưa phải lựa chọn cuối cùng**.
-   Agent phải so sánh mức độ đầy đủ của ngày, số sản phẩm, độ phủ dữ
    liệu Sales/Inventory, số bản ghi bất thường và khả năng ghép dữ
    liệu.
-   Có thể đề xuất `STR-1198` hoặc cửa hàng khác nếu profiling chứng
    minh dữ liệu phù hợp hơn.
-   Không được gộp nhiều cửa hàng để tăng số lượng dữ liệu.
-   Chỉ chốt Store ID sau khi trình bày bảng so sánh và nêu lý do. Nếu
    Agent có quyền tự triển khai mà không cần hỏi, chọn cửa hàng tốt
    nhất theo tiêu chí nêu trên và ghi rõ quyết định trong tài liệu.

### 2.5. Các rủi ro dữ liệu phải xác minh

1.  **Grain của Sales:** xác định một dòng là giao dịch, nhóm giao dịch,
    hay dữ liệu tổng hợp theo một tổ hợp chiều. Không được mặc định một
    dòng tương ứng một đơn hàng.
2.  **Grain của Inventory:** xác định một dòng là khoảng hiệu lực tồn
    kho, bản ghi trạng thái hay một dạng snapshot. Không được cộng
    `Qty on hand` của mọi dòng một cách trực tiếp.
3.  **End Date sentinel:** xử lý `9999-12-31` có chủ đích, giữ nguyên
    giá trị nguồn trong raw/staging và chuẩn hóa ở lớp phù hợp.
4.  **Returns:** xác định ý nghĩa của `Is Return`, `Qty Sold`,
    `Sales Amount` và `Cogs` trên dòng trả hàng. Không tự ý đổi dấu hoặc
    loại bỏ dòng trả hàng trước khi hiểu quy ước dữ liệu.
5.  **Sales và Inventory:** xác minh khóa ghép và khoảng thời gian có
    thể đối chiếu. Không giả định hai file có cùng grain.
6.  **Thiếu dữ liệu:** phân biệt NULL hợp lệ, giá trị không áp dụng và
    dữ liệu lỗi.
7.  **Tính liên tục thời gian:** kiểm tra ngày thiếu, ngày không có giao
    dịch và sản phẩm không phát sinh bán hàng. Không tự động điền 0 nếu
    chưa phân biệt được "không bán" với "thiếu dữ liệu".
8.  **Đơn vị và ý nghĩa tiền tệ:** kiểm tra tài liệu dataset hoặc phân
    tích giá trị. Không tự gán USD/VND nếu nguồn không xác nhận.
9.  **Tính xác thực:** không tự tuyên bố dữ liệu là dữ liệu thực, dữ
    liệu giả lập hay dữ liệu ẩn danh nếu tài liệu nguồn không chứng minh
    điều đó. Phải mô tả đúng theo nguồn.

------------------------------------------------------------------------

## 3. Mục tiêu nghiệp vụ và câu hỏi phân tích

Hệ thống cần hỗ trợ trả lời các câu hỏi sau, trong giới hạn dữ liệu thực
sự có:

### 3.1. Phân tích doanh số

-   Doanh thu và số lượng bán thay đổi như thế nào theo ngày, tuần,
    tháng?
-   Sản phẩm/danh mục nào có doanh thu hoặc số lượng bán cao nhất?
-   Cơ cấu doanh thu theo `Sales Type` như thế nào?
-   Tỷ lệ và giá trị hàng trả lại ra sao?
-   Giá vốn và lợi nhuận gộp có thể tính được như thế nào từ
    `Sales Amount` và `Cogs`, sau khi xác minh quy ước dữ liệu?
-   Những sản phẩm nào có xu hướng bán tăng hoặc giảm?

### 3.2. Phân tích tồn kho

-   Số lượng hàng tồn theo sản phẩm và danh mục là bao nhiêu tại một
    thời điểm xác định?
-   Sản phẩm nào có lượng tồn cao/thấp?
-   Giá trị tồn kho theo giá bán và giá vốn là bao nhiêu?
-   Tồn kho thay đổi theo các khoảng hiệu lực như thế nào?
-   Sản phẩm nào có dấu hiệu thiếu hàng hoặc tồn kho cao, nếu dữ liệu đủ
    để xác định?

Không được gọi một sản phẩm là "tồn lâu" nếu không có dữ liệu đủ để tính
tuổi tồn kho. Không được khẳng định "stockout" chỉ dựa vào doanh số thấp
hoặc tồn kho thấp nếu thiếu định nghĩa/ngưỡng nghiệp vụ.

### 3.3. Dự báo nhu cầu

-   Dự báo số lượng bán theo sản phẩm cho các kỳ tiếp theo.
-   Có thể bắt đầu với dự báo tổng hợp ở cấp ngày hoặc tuần cho các sản
    phẩm có đủ lịch sử.
-   So sánh dự báo với dữ liệu thực tế trên tập kiểm tra theo thời gian.
-   Chỉ chuyển dự báo bán hàng thành gợi ý bổ sung hàng khi có dữ liệu
    tồn kho và giả định rõ ràng.

**Phân biệt bắt buộc:** `Demand Forecasting` trong dự án trước hết là dự
báo nhu cầu/số lượng bán. Đây không tự động đồng nghĩa với dự báo tồn
kho hoặc tối ưu lượng đặt hàng.

------------------------------------------------------------------------

## 4. Phạm vi chức năng

### 4.1. Data Warehouse

-   Tiếp nhận hai CSV nguồn.
-   Lưu bản raw hoặc bản sao bất biến của nguồn.
-   Xây dựng staging để chuẩn hóa kiểu dữ liệu, tên cột và chất lượng dữ
    liệu.
-   Thiết kế mô hình chiều phù hợp với grain đã xác minh.
-   Tạo các bảng Dimension và Fact cần thiết.
-   Xây dựng quy trình ETL có thể chạy lại.
-   Có kiểm tra chất lượng dữ liệu và đối soát số liệu nguồn với kho dữ
    liệu.

Mô hình Star Schema chỉ được chốt sau khi xác định grain. Có thể cần
nhiều fact table với grain khác nhau, ví dụ:

-   Fact Sales: grain theo đúng cấp chi tiết của dòng Sales nguồn.
-   Fact Inventory: grain theo bản ghi sản phẩm/cửa hàng/khoảng hiệu lực
    hoặc snapshot đã xác minh.

Dimension có thể xem xét:

-   DimDate
-   DimProduct
-   DimStore (dù phạm vi phân tích cuối cùng chỉ có một Store ID,
    dimension vẫn có thể được giữ nếu hợp lý)
-   DimSupplier
-   DimSalesType
-   Các dimension khác chỉ khi dữ liệu và nhu cầu phân tích thực sự hỗ
    trợ.

Không tạo dimension giả hoặc thêm thuộc tính không có nguồn đáng tin
cậy.

### 4.2. BI và OLAP

Tối thiểu cần có:

-   Dashboard tổng quan doanh số.
-   Dashboard phân tích sản phẩm/danh mục.
-   Dashboard tồn kho.
-   Bộ KPI có định nghĩa, công thức và nguồn dữ liệu.
-   Các truy vấn OLAP minh họa Drill-down, Roll-up, Slice và Dice.

Công cụ BI sẽ được lựa chọn dựa trên môi trường local và khả năng của
người dùng. Có thể cân nhắc Power BI hoặc một dashboard Python phù hợp.
Không triển khai nhiều công cụ BI cùng lúc nếu không tạo thêm giá trị.

### 4.3. Machine Learning

Phạm vi vừa sức cá nhân:

1.  Xây dựng baseline đơn giản, ví dụ Naive Forecast hoặc Moving
    Average.
2.  Chọn một mô hình ML chính phù hợp dữ liệu sau khi phân tích, ví dụ
    Random Forest hoặc XGBoost.
3.  Tạo đặc trưng thời gian và đặc trưng lịch sử chỉ từ dữ liệu quá khứ.
4.  Chia tập train/validation/test theo thời gian, không random split
    làm rò rỉ tương lai.
5.  Đánh giá bằng các metric phù hợp như MAE, RMSE và/hoặc WAPE. Giải
    thích hạn chế của MAPE khi actual bằng 0 hoặc gần 0.
6.  So sánh mô hình ML với baseline.
7.  Trình bày dự báo theo sản phẩm/kỳ thời gian và giới hạn của mô hình.

Không bắt buộc triển khai Deep Learning. Không chọn mô hình phức tạp chỉ
để làm dự án có vẻ nâng cao.

### 4.4. Hỗ trợ quyết định

Có thể trình bày các cảnh báo hoặc gợi ý mang tính hỗ trợ, ví dụ:

-   Nhu cầu dự báo cao hơn lượng tồn hiện có.
-   Sản phẩm có doanh số tăng nhưng lượng tồn thấp.
-   Sản phẩm có tồn kho cao so với tốc độ bán.

Mọi ngưỡng cảnh báo phải được giải thích, cấu hình được và ghi rõ là quy
tắc phân tích của dự án, không phải chính sách vận hành thực tế của nhà
bán lẻ.

------------------------------------------------------------------------

## 5. Kiến trúc và công nghệ định hướng

### 5.1. Luồng kiến trúc

`CSV nguồn → Raw/Staging → ETL → Data Warehouse → SQL/OLAP → BI Dashboard`

Nhánh Machine Learning:

`Dữ liệu đã kiểm tra → Feature Engineering → Train/Test theo thời gian → Model Evaluation → Forecast Output → Dashboard/Decision Support`

### 5.2. Công nghệ đề xuất

Đây là lựa chọn mặc định để Agent đánh giá, không phải yêu cầu bất biến:

-   Hệ điều hành: Windows 11.
-   IDE: Visual Studio Code.
-   Ngôn ngữ xử lý dữ liệu: Python.
-   Data processing: pandas, NumPy.
-   Database: PostgreSQL được ưu tiên cho kho dữ liệu local; có thể đề
    xuất MySQL nếu có lý do rõ ràng và tương thích tốt hơn với môi
    trường.
-   ML: scikit-learn; XGBoost chỉ thêm khi thực sự cần.
-   BI: Power BI hoặc Streamlit; chỉ chọn một hướng chính sau khi đánh
    giá.
-   Quản lý môi trường: `venv` và `requirements.txt`.
-   SQL và script ETL phải được lưu trong source code, không chỉ thao
    tác thủ công trong giao diện.

Agent phải kiểm tra phiên bản Python và khả năng tương thích thư viện
trước khi tạo môi trường. Ưu tiên phiên bản ổn định có hỗ trợ đầy đủ,
tránh chọn phiên bản Python quá mới khiến thư viện ML không tương thích.

------------------------------------------------------------------------

## 6. Kế hoạch triển khai theo giai đoạn

Không bỏ qua giai đoạn kiểm tra dữ liệu. Không triển khai tất cả trong
một lần nếu chưa xác nhận các quyết định nền tảng.

### Giai đoạn 0 --- Tiếp nhận và kiểm kê

-   Đọc toàn bộ `Claude.md`.
-   Xác nhận có file ZIP và hai CSV.
-   Kiểm tra cấu trúc thư mục, dung lượng, encoding, delimiter, header.
-   Không sửa hoặc ghi đè file nguồn.
-   Tạo bản ghi nhận dataset và checksum nếu phù hợp.

**Đầu ra:** báo cáo kiểm kê đầu vào.

### Giai đoạn 1 --- Data Profiling và chốt phạm vi một cửa hàng

-   Đọc schema và kiểu dữ liệu.
-   Kiểm tra số dòng, NULL, duplicate, min/max ngày, giá trị phân loại.
-   Phân tích từng Store ID trong Sales và Inventory.
-   So sánh độ phủ thời gian, số sản phẩm, số dòng và khả năng ghép dữ
    liệu.
-   Kiểm tra grain của cả hai file.
-   Đề xuất và chốt một Store ID.
-   Ghi rõ mọi giới hạn dữ liệu.

**Đầu ra:** `docs/data_profile.md`, bảng so sánh Store ID, quyết định
phạm vi và data dictionary sơ bộ.

**Điều kiện hoàn thành:** biết chính xác dữ liệu đại diện cho điều gì và
có thể phân tích đáng tin cậy đến mức nào.

### Giai đoạn 2 --- Phân tích yêu cầu và thiết kế Data Warehouse

-   Chuyển câu hỏi nghiệp vụ thành KPI và truy vấn cần hỗ trợ.
-   Xác định grain trước khi thiết kế Fact.
-   Thiết kế Star Schema hoặc mô hình phù hợp có giải thích.
-   Xác định khóa chính, khóa ngoại, surrogate key nếu cần.
-   Xác định quy tắc xử lý hàng trả lại, khoảng hiệu lực tồn kho và ngày
    sentinel.
-   Vẽ ERD/Star Schema và mô tả luồng dữ liệu.

**Đầu ra:** tài liệu yêu cầu, data dictionary, sơ đồ mô hình và quyết
định thiết kế.

**Điều kiện hoàn thành:** mọi Fact có grain rõ ràng; không có quan hệ
hoặc phép cộng số liệu mơ hồ.

### Giai đoạn 3 --- Xây dựng ETL và Data Warehouse

-   Tạo database/schema.
-   Tạo bảng staging, dimension, fact.
-   Viết ETL theo từng bước rõ ràng.
-   Làm sạch và chuẩn hóa dữ liệu có quy tắc.
-   Nạp dữ liệu theo trình tự phù hợp.
-   Có log, xử lý lỗi và khả năng chạy lại an toàn.
-   Đối soát số liệu giữa source, staging và warehouse.

**Đầu ra:** SQL DDL, Python ETL, dữ liệu đã nạp và báo cáo kiểm thử ETL.

### Giai đoạn 4 --- SQL Analytics và OLAP

-   Viết truy vấn KPI.
-   Phân tích theo thời gian, sản phẩm, danh mục và các chiều có sẵn.
-   Minh họa Drill-down, Roll-up, Slice, Dice.
-   Kiểm tra tính đúng đắn của phép tổng hợp, đặc biệt với Inventory.

**Đầu ra:** thư mục SQL analytics và tài liệu giải thích kết quả.

### Giai đoạn 5 --- BI Dashboard

-   Xác định người dùng và câu hỏi dashboard cần trả lời.
-   Thiết kế bố cục tổng quan và các trang phân tích.
-   Xây dựng KPI, bộ lọc và biểu đồ.
-   Đối chiếu các con số trên dashboard với truy vấn SQL.
-   Trình bày rõ Store ID và khoảng thời gian được phân tích.

**Đầu ra:** dashboard chạy được và hướng dẫn sử dụng.

### Giai đoạn 6 --- Machine Learning Forecasting

-   Chọn sản phẩm có đủ lịch sử dữ liệu.
-   Xác định tần suất dự báo (ngày/tuần) dựa trên độ phủ dữ liệu.
-   Tạo chuỗi thời gian và feature.
-   Tạo baseline.
-   Huấn luyện mô hình ML.
-   Đánh giá theo temporal split và metric phù hợp.
-   So sánh mô hình, phân tích sai số và lưu dự báo.

**Đầu ra:** mã nguồn huấn luyện/dự báo, metric, biểu đồ
actual-vs-predicted và giải thích mô hình.

### Giai đoạn 7 --- Tích hợp và hỗ trợ quyết định

-   Kết nối kết quả forecast với dashboard.
-   Xây dựng quy tắc cảnh báo thiếu hàng/tồn cao nếu dữ liệu hỗ trợ.
-   Nêu rõ giả định, ngưỡng và giới hạn.
-   Không tự động thực hiện đặt hàng.

**Đầu ra:** dashboard/tính năng hỗ trợ quyết định tích hợp.

### Giai đoạn 8 --- Kiểm thử, tài liệu và bàn giao

-   Kiểm thử ETL, dữ liệu, truy vấn, dashboard và ML.
-   Kiểm tra khả năng chạy lại từ đầu.
-   Viết README hướng dẫn setup/run.
-   Viết báo cáo dự án và chuẩn bị nội dung trình bày.
-   Kiểm tra source tree và loại bỏ file tạm/artefact không cần thiết.

**Đầu ra:** source code hoàn chỉnh, tài liệu, kết quả kiểm thử và hướng
dẫn bàn giao.

------------------------------------------------------------------------

## 7. Quy tắc và ràng buộc bắt buộc cho Agent

### 7.1. Quy tắc làm việc

1.  Đọc `Claude.md` trước khi làm bất kỳ việc gì.
2.  Làm theo từng giai đoạn; không tự ý nhảy sang giai đoạn sau khi điều
    kiện đầu ra chưa đạt.
3.  Trước khi thay đổi kiến trúc hoặc công nghệ đã thống nhất, phải nêu
    lý do và tác động.
4.  Khi thiếu thông tin, kiểm tra dataset/tài liệu trước; không tự bịa
    dữ liệu.
5.  Phân biệt rõ:
    -   Thông tin đã xác minh từ dataset.
    -   Giả định thiết kế.
    -   Đề xuất của Agent.
    -   Kết quả thực nghiệm.
6.  Không tuyên bố một chức năng đã hoàn thành nếu chưa chạy và kiểm
    thử.
7.  Không dùng số liệu minh họa như thể là kết quả thật.
8.  Giải thích các thuật ngữ kỹ thuật và quyết định thiết kế bằng tiếng
    Việt.

### 7.2. Quy tắc chỉnh sửa file

1.  Chỉ tạo hoặc chỉnh sửa các file thực sự cần thiết cho giai đoạn hiện
    tại.
2.  Không viết lại toàn bộ project khi chỉ cần sửa một phần.
3.  Không xóa file hoặc thay đổi cấu trúc hiện hữu nếu chưa giải thích
    và được chấp thuận.
4.  Không ghi đè dataset gốc.
5.  Không đưa file dữ liệu lớn, virtual environment, cache, model
    artifact không cần thiết vào Git.
6.  Mỗi giai đoạn phải liệt kê:
    -   File tạo mới.
    -   File chỉnh sửa.
    -   Mục đích từng file.
    -   Lệnh chạy/kiểm thử.
    -   Kết quả kiểm thử.
7.  Nếu đóng gói ZIP cập nhật, chỉ đưa các file mới hoặc đã sửa cần bàn
    giao; không đóng gói lại toàn bộ source không liên quan.
8.  Luôn ghi rõ đường dẫn đích để người dùng biết file cần đặt ở đâu.

### 7.3. Quy tắc dữ liệu

1.  Raw data phải được bảo toàn.
2.  Không xóa dòng chỉ vì chưa hiểu ý nghĩa.
3.  Mọi quy tắc làm sạch phải được ghi lại và có thể tái thực hiện.
4.  Không suy diễn đơn vị tiền tệ, múi giờ, ý nghĩa mã hoặc định nghĩa
    nghiệp vụ.
5.  Không cộng tồn kho từ các khoảng thời gian chồng lấn nếu chưa xác
    định cách xử lý.
6.  Không join Fact Sales và Fact Inventory trực tiếp theo Product/Store
    rồi cộng các measure mà không kiểm soát fan-out.
7.  Không tạo dữ liệu khách hàng, đơn hàng, cửa hàng, nhà cung cấp hoặc
    thuộc tính không có trong nguồn.
8.  Khi lọc một cửa hàng, phải áp dụng nhất quán cho cả Sales và
    Inventory.
9.  Ghi rõ các bản ghi bị loại, lý do và số lượng.
10. Đảm bảo truy vấn tổng hợp không đếm trùng `Number of Transactions`.

### 7.4. Quy tắc Machine Learning

1.  Không dùng dữ liệu tương lai để tạo feature cho quá khứ.
2.  Không random split chuỗi thời gian.
3.  Không dùng dữ liệu test để lựa chọn mô hình hoặc tuning.
4.  Phải có baseline.
5.  Phải báo cáo metric trên tập test và mô tả cách chia dữ liệu.
6.  Không khẳng định mô hình dự báo tốt chỉ dựa trên một biểu đồ.
7.  Xử lý ngày thiếu và actual bằng 0 có chủ đích.
8.  Không gọi dự báo số lượng bán là dự báo tồn kho.
9.  Chỉ đưa ra gợi ý bổ sung hàng khi có logic và giả định tồn kho rõ
    ràng.

### 7.5. Quy tắc giao tiếp và báo cáo

-   Ngôn ngữ trao đổi, tài liệu hướng dẫn và giải thích: tiếng Việt.
-   Tên biến, tên hàm, tên class, tên file và identifier trong code:
    tiếng Anh.
-   Nội dung log/output hướng đến người dùng có thể dùng tiếng Việt.
-   Hướng dẫn phải theo từng bước, phù hợp người học đang triển khai dự
    án cá nhân.
-   Không đưa ra quá nhiều lựa chọn kỹ thuật mà không có khuyến nghị.
-   Khi có nhiều phương án, so sánh ngắn gọn và đề xuất một phương án
    mặc định.
-   Cuối mỗi giai đoạn phải có phần tổng kết và xác nhận điều kiện để
    chuyển tiếp.

------------------------------------------------------------------------

## 8. Cấu trúc thư mục định hướng

Đây là cấu trúc tham khảo. Chỉ tạo thư mục khi có nội dung thực tế;
không tạo hàng loạt file rỗng.

``` text
retail-sales-inventory-dw/
├── Claude.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── data/
│   ├── raw/                 # Dataset gốc, không chỉnh sửa
│   ├── staging/             # Dữ liệu trung gian nếu cần
│   └── processed/           # Dữ liệu đã xử lý nếu cần
├── database/
│   ├── ddl/
│   ├── views/
│   └── analytics/
├── etl/
│   ├── extract/
│   ├── transform/
│   └── load/
├── ml/
│   ├── features/
│   ├── training/
│   ├── evaluation/
│   └── forecasting/
├── bi/
├── docs/
│   ├── data_profile.md
│   ├── data_dictionary.md
│   ├── architecture.md
│   ├── data_model.md
│   ├── etl_design.md
│   ├── kpi_definitions.md
│   └── testing.md
├── tests/
└── scripts/
```

Nếu Agent làm việc trên một project đã có sẵn, phải kiểm tra cấu trúc
hiện tại trước và thích nghi; không ép di chuyển toàn bộ source vào cấu
trúc này.

------------------------------------------------------------------------

## 9. Tiêu chí nghiệm thu tổng thể

Dự án chỉ được xem là hoàn thành khi đáp ứng các điều kiện:

### Data

-   Đã xác định và ghi rõ Store ID duy nhất.
-   Đã mô tả grain của Sales và Inventory.
-   Đã có data dictionary.
-   Đã xử lý các giá trị ngày đặc biệt và hàng trả lại theo quy tắc có
    căn cứ.
-   Có báo cáo đối soát số dòng và measure giữa nguồn với warehouse.

### Data Warehouse và ETL

-   Có sơ đồ mô hình dữ liệu.
-   Có Fact/Dimension với grain được định nghĩa.
-   ETL chạy lại được và không nạp trùng ngoài ý muốn.
-   Có kiểm tra khóa, NULL, duplicate và referential integrity phù hợp.

### BI và OLAP

-   Dashboard có KPI được định nghĩa.
-   Có phân tích doanh số và tồn kho trong phạm vi dữ liệu hỗ trợ.
-   Có ví dụ truy vấn OLAP.
-   Số liệu dashboard đối chiếu được với SQL.

### Machine Learning

-   Có baseline và ít nhất một mô hình ML.
-   Có temporal split.
-   Có metric và kết quả test.
-   Có biểu đồ so sánh actual/predicted.
-   Có mô tả giới hạn và điều kiện sử dụng dự báo.

### Bàn giao

-   Có README hướng dẫn cài đặt và chạy.
-   Có danh sách file và vai trò.
-   Có hướng dẫn tái tạo kết quả.
-   Không chứa thông tin bí mật hoặc file môi trường cá nhân.

------------------------------------------------------------------------

## 10. Việc Agent cần làm đầu tiên

Khi nhận được `Claude.md` và file ZIP dataset, **không bắt đầu xây dựng
hệ thống ngay**.

Thứ tự bắt buộc:

1.  Đọc toàn bộ `Claude.md`.
2.  Kiểm tra ZIP và xác nhận hai CSV.
3.  Thực hiện Giai đoạn 0 và Giai đoạn 1.
4.  Lập báo cáo profiling, bao gồm:
    -   schema và kiểu dữ liệu;
    -   số dòng, số cột;
    -   khoảng ngày;
    -   NULL, duplicate và giá trị bất thường;
    -   grain của từng file;
    -   phân bố Store ID;
    -   mức độ khớp giữa Sales và Inventory;
    -   đề xuất một Store ID phù hợp nhất.
5.  Đưa ra kết luận liệu dataset có đủ điều kiện triển khai đề tài hay
    cần điều chỉnh phạm vi.

**Chưa thiết kế Star Schema cuối cùng, chưa tạo database, chưa viết ETL,
chưa xây Dashboard và chưa huấn luyện ML ở bước đầu tiên.**

Sau khi hoàn tất báo cáo Giai đoạn 1, Agent phải dừng và trình bày kết
quả để người dùng quyết định bước tiếp theo.
