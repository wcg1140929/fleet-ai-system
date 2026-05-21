import streamlit as st
import pandas as pd
import google.generativeai as genai
import json

# ==========================================
# 1. 頁面設定與 API 初始化 (使用 Secrets)
# ==========================================
st.set_page_config(page_title="車隊自建與委外評估系統", layout="wide")
st.title("🚚 車隊自建 vs. 委外 決策評估系統")

api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    st.error("找不到 API Key，請確認 .streamlit/secrets.toml 設定。")
    st.stop()

tab1, tab2 = st.tabs(["🧹 模組一：資料匯入與 AI 清洗", "📊 模組二：自建 vs 委外 成本決策"])

# ==========================================
# [頁籤 1] 模組一：資料清洗 (支援多檔合併與動態欄位)
# ==========================================
with tab1:
    st.header("Step 1: 上傳原始物流報表 (支援多檔)")
    st.markdown("您可以一次選取多個月份的 Excel 或 CSV 檔案，系統將自動為您合併。")
    
    # 【升級 1】：加入 accept_multiple_files=True 支援多檔上傳
    uploaded_files = st.file_uploader("請拖曳或選擇檔案", type=["xlsx", "csv"], accept_multiple_files=True)

    if uploaded_files: # 當有檔案上傳時
        dfs = []
        for file in uploaded_files:
            # 依據副檔名讀取資料
            if file.name.endswith('.csv'):
                dfs.append(pd.read_csv(file))
            else:
                dfs.append(pd.read_excel(file))
        
        # 【升級 1】：自動合併所有上傳的報表
        df_raw = pd.concat(dfs, ignore_index=True)
            
        st.success(f"✅ 成功合併 {len(uploaded_files)} 個檔案，共 {len(df_raw)} 筆資料！")
        st.write("👀 **合併後資料預覽 (前 5 筆)：**")
        st.dataframe(df_raw.head().astype(str))

        st.header("Step 2: 選擇要交給 AI 處理的欄位")
        st.markdown("系統已自動抓取報表中的所有欄位。請**取消勾選**不需要的欄位（如：備註、電話），以加速 AI 處理並提高準確度。")
        
        # 【升級 2】：動態讀取真實欄位，並使用多選框 (multiselect) 讓使用者挑選
        all_columns = df_raw.columns.tolist()
        
        # 預設幫使用者全選，讓他們自己拿掉不要的
        selected_raw_columns = st.multiselect(
            "請選擇要保留的欄位：", 
            options=all_columns, 
            default=all_columns
        )

        if st.button("🚀 執行 AI 資料清洗與標準化", type="primary"):
            if not selected_raw_columns:
                st.warning("⚠️ 請至少選擇一個欄位！")
            else:
                with st.spinner("AI 正在閱讀並解構報表，請稍候..."):
                    # 只取使用者勾選的欄位，並轉為 CSV 文字給 AI
                    df_filtered = df_raw[selected_raw_columns]
                    csv_text = df_filtered.head(20).to_csv(index=False) # 測試期先取前20筆
                    
                    # 定義系統模組二需要的標準格式 (Target Schema)
                    json_schema = {
                        "date": "標準化為 YYYY-MM-DD",
                        "license_plate": "字串，例如 ABC-1234",
                        "fuel_cost": "純數字(若無則填0)",
                        "maintenance_cost": "純數字(若無則填0)",
                        "mileage_km": "純數字(若無則填0)"
                    }
                    
                    prompt = f"""
                    你是一個專業的資料庫工程師。請閱讀以下的 CSV 原始資料，並將其清洗、萃取並對應到目標 JSON 結構。
                    規則：
                    1. 如果找不到數值請填 null 或 0。
                    2. 數字欄位必須是純數字，去除所有單位（如元、km）。
                    3. 直接回傳 JSON Array，絕對不要加上 markdown 標籤。
                    
                    目標 JSON Schema 結構：{json.dumps(json_schema, ensure_ascii=False)}
                    原始 CSV 資料：\n{csv_text}
                    """
                    
                    try:
                        response = model.generate_content(prompt)
                        result_text = response.text.replace("```json", "").replace("```", "").strip()
                        cleaned_data = json.loads(result_text)
                        df_cleaned = pd.DataFrame(cleaned_data)
                        
                        st.success("✅ AI 清洗完成！資料已自動傳送至【模組二】。")
                        st.dataframe(df_cleaned)
                        
                        # 將清洗好的資料存入 Session State
                        st.session_state['cleaned_df'] = df_cleaned
                        
                    except Exception as e:
                        st.error(f"解析錯誤：{e}\n請重試或檢查欄位選擇是否包含足夠的數據。")

# ==========================================
# [頁籤 2] 模組二：成本決策與視覺化 (與上次完全相同)
# ==========================================
with tab2:
    st.header("💡 總體擁有成本 (TCO) 比較分析")
    
    if 'cleaned_df' not in st.session_state:
        st.info("請先至「模組一」上傳資料並執行 AI 清洗，以取得基礎營運數據。")
    else:
        df = st.session_state['cleaned_df']
        
        st.subheader("1. 您的自有車隊現況 (總體擁有成本評估)")
        total_trips = len(df)
        total_fuel = df['fuel_cost'].sum() if 'fuel_cost' in df.columns else 0
        
        st.markdown("##### 📍 變動成本 (來自 AI 清洗數據)")
        col1, col2, col3 = st.columns(3)
        col1.metric("分析趟次", f"{total_trips} 趟")
        col2.metric("總油資 (變動成本)", f"${total_fuel:,.0f}")
        col3.metric("單趟平均油資", f"${total_fuel/total_trips:,.0f}" if total_trips>0 else "$0")

        st.markdown("##### 📍 固定成本 (請輸入該區間之費用)")
        fixed_col1, fixed_col2, fixed_col3 = st.columns(3)
        with fixed_col1:
            driver_salary = st.number_input("司機總薪資 (元)", value=60000, step=1000)
        with fixed_col2:
            vehicle_depreciation = st.number_input("車輛折舊攤提 (元)", value=25000, step=1000)
        with fixed_col3:
            insurance_fees = st.number_input("保險與規費攤提 (元)", value=5000, step=1000)
            
        inhouse_fixed_cost = driver_salary + vehicle_depreciation + insurance_fees
        inhouse_total = total_fuel + inhouse_fixed_cost

        st.info(f"**自有車隊真實總成本 (TCO)：** 變動成本 ${total_fuel:,.0f} + 固定成本 ${inhouse_fixed_cost:,.0f} = **${inhouse_total:,.0f}**")

        st.subheader("2. 模擬委外車隊報價")
        st.markdown("請輸入物流商提供的報價參數，系統將自動以您目前的出貨樣態進行換算。")
        
        outsource_col1, outsource_col2 = st.columns(2)
        with outsource_col1:
            outsource_base_fee = st.number_input("外部物流 - 每趟基本出車費 (元)", value=1200)
        with outsource_col2:
            outsource_admin_fee = st.number_input("每月系統對接與行政管理費 (元)", value=5000)

        outsource_total = (total_trips * outsource_base_fee) + outsource_admin_fee
        
        st.subheader("3. 成本比較決策")
        
        chart_data = pd.DataFrame(
            {"總成本 (元)": [inhouse_total, outsource_total]},
            index=["自有車隊 (真實 TCO)", "委外車隊 (模擬)"]
        )
        
        st.bar_chart(chart_data, color="#2E86C1")
        
        if inhouse_total < outsource_total:
            st.success(f"🏆 結論：目前維持 **自有車隊** 較為划算！委外將增加約 ${(outsource_total - inhouse_total):,.0f} 元的成本。")
        else:
            st.warning(f"⚠️ 結論：建議考慮 **物流委外**！現行自建車隊成本超出了 ${(inhouse_total - outsource_total):,.0f} 元。")