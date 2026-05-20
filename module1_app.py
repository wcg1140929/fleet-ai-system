import streamlit as st
import pandas as pd
import google.generativeai as genai
import json

# ==========================================
# 1. 頁面設定與 API 初始化 (使用 Secrets)
# ==========================================
st.set_page_config(page_title="車隊自建與委外評估系統", layout="wide")
st.title("🚚 車隊自建 vs. 委外 決策評估系統")

# 從 Streamlit secrets 自動讀取 API Key (不再需要側邊欄輸入)
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    st.error("找不到 API Key，請確認 .streamlit/secrets.toml 設定。")
    st.stop()

# 建立頁籤，將系統分為兩大模組
tab1, tab2 = st.tabs(["🧹 模組一：資料匯入與 AI 清洗", "📊 模組二：自建 vs 委外 成本決策"])

# ==========================================
# [頁籤 1] 模組一：資料清洗
# ==========================================
with tab1:
    st.header("Step 1: 上傳原始物流報表")
    uploaded_file = st.file_uploader("支援 Excel (.xlsx) 或 CSV 格式", type=["xlsx", "csv"])

    if uploaded_file is not None:
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)
            
        st.write("👀 **原始資料預覽 (前 5 筆)：**")
        # 修正 PyArrow 混合型態報錯：強制轉為字串 (astype(str)) 顯示
        st.dataframe(df_raw.head().astype(str))

        st.header("Step 2: 選擇需要 AI 萃取的關鍵欄位")
        col1, col2 = st.columns(2)
        with col1:
            need_date = st.checkbox("出車日期 (Date)", value=True)
            need_plate = st.checkbox("車牌號碼 (License Plate)", value=True)
            need_mileage = st.checkbox("行駛里程 (Mileage)", value=True)
        with col2:
            need_fuel = st.checkbox("加油金額 (Fuel Cost)", value=True)
            need_maint = st.checkbox("維修保養 (Maintenance)")

        if st.button("🚀 執行 AI 資料清洗與標準化", type="primary"):
            with st.spinner("AI 正在閱讀並解構報表，請稍候..."):
                json_schema = {}
                if need_date: json_schema["date"] = "標準化為 YYYY-MM-DD"
                if need_plate: json_schema["license_plate"] = "字串，例如 ABC-1234"
                if need_fuel: json_schema["fuel_cost"] = "純數字"
                if need_maint: json_schema["maintenance_cost"] = "純數字"
                if need_mileage: json_schema["mileage_km"] = "純數字"

                csv_text = df_raw.head(20).to_csv(index=False)
                
                prompt = f"""
                你是一個專業的資料庫工程師。請閱讀以下的 CSV 原始資料，並按照 JSON 結構萃取。
                規則：
                1. 如果找不到數值請填 null。
                2. 數字欄位必須是純數字。
                3. 直接回傳 JSON Array，絕對不要加上 markdown 標籤。
                目標 JSON Schema 結構：{json.dumps(json_schema, ensure_ascii=False)}
                原始 CSV：\n{csv_text}
                """
                
                try:
                    response = model.generate_content(prompt)
                    # 清除 AI 假會加上的 markdown 標籤
                    result_text = response.text.replace("```json", "").replace("```", "").strip()
                    cleaned_data = json.loads(result_text)
                    df_cleaned = pd.DataFrame(cleaned_data)
                    
                    st.success("✅ AI 清洗完成！資料已自動傳送至【模組二】。")
                    st.dataframe(df_cleaned)
                    
                    # 【關鍵一步】：將清洗好的資料存入 Session State，讓模組二可以讀取
                    st.session_state['cleaned_df'] = df_cleaned
                    
                except Exception as e:
                    st.error(f"解析錯誤：{e}")

# ==========================================
# [頁籤 2] 模組二：成本決策與視覺化
# ==========================================
with tab2:
    st.header("💡 總體擁有成本 (TCO) 比較分析")
    
    # 檢查模組一是否已經有清洗好的資料
    if 'cleaned_df' not in st.session_state:
        st.info("請先至「模組一」上傳資料並執行 AI 清洗，以取得基礎營運數據。")
    else:
        df = st.session_state['cleaned_df']
        
        # --- 自動計算自有車隊變動數據 ---
        st.subheader("1. 您的自有車隊現況 (總體擁有成本評估)")
        total_trips = len(df)  # 總趟次
        total_fuel = df['fuel_cost'].sum() if 'fuel_cost' in df.columns else 0 # 總油資
        
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

        # --- 讓使用者輸入委外報價 ---
        st.subheader("2. 模擬委外車隊報價")
        st.markdown("請輸入物流商提供的報價參數，系統將自動以您目前的出貨樣態進行換算。")
        
        outsource_col1, outsource_col2 = st.columns(2)
        with outsource_col1:
            outsource_base_fee = st.number_input("外部物流 - 每趟基本出車費 (元)", value=1200)
        with outsource_col2:
            outsource_admin_fee = st.number_input("每月系統對接與行政管理費 (元)", value=5000)

        # 試算：如果這些趟次全部委外，要花多少錢？
        outsource_total = (total_trips * outsource_base_fee) + outsource_admin_fee
        
        # --- 成本試算與視覺化圖表 ---
        st.subheader("3. 成本比較決策")
        
        # 使用 Streamlit 內建的簡單長條圖呈現比較
        chart_data = pd.DataFrame(
            {"總成本 (元)": [inhouse_total, outsource_total]},
            index=["自有車隊 (真實 TCO)", "委外車隊 (模擬)"]
        )
        
        st.bar_chart(chart_data, color="#2E86C1")
        
        if inhouse_total < outsource_total:
            st.success(f"🏆 結論：目前維持 **自有車隊** 較為划算！委外將增加約 ${(outsource_total - inhouse_total):,.0f} 元的成本。")
        else:
            st.warning(f"⚠️ 結論：建議考慮 **物流委外**！現行自建車隊成本超出了 ${(inhouse_total - outsource_total):,.0f} 元。")