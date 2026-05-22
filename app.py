import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import altair as alt

# ==========================================
# 1. 頁面設定與 API 初始化
# ==========================================
st.set_page_config(page_title="TAIWAN iCarbon 車隊戰略中樞", layout="wide", page_icon="🚚")
st.title("🚚 車隊戰略、ESG 與資產決策中樞")

api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    st.error("找不到 API Key，請確認 .streamlit/secrets.toml 設定。")
    st.stop()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🧹 模組一：AI 清洗", 
    "📊 模組二：成本決策", 
    "🍃 模組三：ESG 碳排", 
    "🏆 模組四：分潤引擎",
    "🔍 模組五：調度抓漏",
    "🔄 模組六：汰舊換新 ROI"
])

# ==========================================
# [頁籤 1] 模組一：資料清洗
# ==========================================
with tab1:
    st.header("Step 1: 上傳原始物流報表 (支援多檔)")
    uploaded_files = st.file_uploader("請拖曳或選擇檔案", type=["xlsx", "csv"], accept_multiple_files=True)

    if uploaded_files:
        dfs = []
        for file in uploaded_files:
            if file.name.endswith('.csv'):
                dfs.append(pd.read_csv(file))
            else:
                dfs.append(pd.read_excel(file))
        
        df_raw = pd.concat(dfs, ignore_index=True)
        st.success(f"✅ 成功合併 {len(uploaded_files)} 個檔案，共 {len(df_raw)} 筆資料！")
        st.dataframe(df_raw.astype(str))

        st.header("Step 2: 選擇要交給 AI 處理的欄位")
        all_columns = df_raw.columns.tolist()
        selected_raw_columns = st.multiselect("請選擇要保留的欄位：", options=all_columns, default=all_columns)

        if st.button("🚀 執行 AI 資料清洗與標準化", type="primary"):
            if not selected_raw_columns:
                st.warning("⚠️ 請至少選擇一個欄位！")
            else:
                with st.spinner("AI 正在閱讀並解構報表，請稍候..."):
                    df_filtered = df_raw[selected_raw_columns]
                    csv_text = df_filtered.to_csv(index=False)
                    
                    json_schema = {
                        "date": "YYYY-MM-DD",
                        "vehicle_type": "字串(如 3.49噸, 15噸)",
                        "driver_name": "字串(負責司機姓名, 若無則填 '未知')",
                        "license_plate": "字串(車牌)",
                        "eco_standard": "字串(環保期數如 4期, 5期, 六期, 若無填 '未知')",
                        "weight_ton": "純數字(載重量_噸，去除單位，若無則填 0)",
                        "fuel_cost": "純數字(油資金額，若無則填 0)",
                        "fuel_liters": "純數字(加油公升數，若無明確數值則填 null)",
                        "maintenance_cost": "純數字(維修保養費，若無則填 0)",
                        "mileage_km": "純數字(行駛公里數，若無則填 0)",
                        "fuel_type": "字串(如 柴油, 95無鉛)"
                    }
                    
                    prompt = f"""
                    你是一個專業的資料庫工程師。請閱讀以下的 CSV 原始資料，並將其清洗、萃取並對應到目標 JSON 結構。
                    規則：
                    1. 如果找不到數值請填 null 或 0。
                    2. 數字欄位必須是純數字，去除所有單位。
                    3. 載重量若為 kg，請自動除以 1000 轉為噸。
                    4. 直接回傳 JSON Array，絕對不要加上 markdown 標籤。
                    目標 JSON Schema 結構：{json.dumps(json_schema, ensure_ascii=False)}
                    原始 CSV 資料：\n{csv_text}
                    """
                    try:
                        response = model.generate_content(prompt)
                        result_text = response.text.replace("```json", "").replace("```", "").strip()
                        cleaned_data = json.loads(result_text)
                        df_cleaned = pd.DataFrame(cleaned_data)
                        
                        st.success("✅ AI 清洗完成！資料已同步傳送至後續模組。")
                        st.dataframe(df_cleaned)
                        st.session_state['cleaned_df'] = df_cleaned
                    except Exception as e:
                        st.error(f"解析錯誤：{e}")

# ==========================================
# [頁籤 2] 模組二：車種分級成本決策
# ==========================================
with tab2:
    st.header("💡 總體擁有成本 (TCO) 與延噸公里 (車種分級版)")
    
    if 'cleaned_df' not in st.session_state:
        st.info("請先至「模組一」上傳資料並執行 AI 清洗。")
    else:
        df = st.session_state['cleaned_df'].copy()
        for col in ['mileage_km', 'weight_ton', 'fuel_cost', 'fuel_liters', 'maintenance_cost']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df['ton_km'] = df['mileage_km'] * df['weight_ton'] if 'mileage_km' in df.columns and 'weight_ton' in df.columns else 0
        df['vehicle_type'] = df['vehicle_type'].fillna('未分類') if 'vehicle_type' in df.columns else '未分類'
        
        vehicle_types = df['vehicle_type'].unique().tolist()
        v_tabs = st.tabs(vehicle_types)
        
        fleet_summary = {}
        grand_inhouse_total = 0
        grand_outsource_total = 0
        report_lines = []
        
        for i, v_type in enumerate(vehicle_types):
            with v_tabs[i]:
                st.subheader(f"🚛 【{v_type}】車隊營運分析")
                v_df = df[df['vehicle_type'] == v_type]
                v_ton_km = v_df['ton_km'].sum()
                v_mileage = v_df['mileage_km'].sum()
                v_fuel_cost_hist = v_df['fuel_cost'].sum()
                v_real_liters = v_df['fuel_liters'].sum() if 'fuel_liters' in v_df.columns else 0

                st.markdown("##### 📍 真實效能評估")
                col_hist1, col_hist2 = st.columns(2)
                with col_hist1:
                    v_hist_price = st.number_input(f"當時 {v_type} 的平均油價 (元/公升)", value=28.5, step=0.5, key=f"hist_{v_type}")
                
                v_total_liters = v_real_liters if v_real_liters > 0 else (v_fuel_cost_hist / v_hist_price if v_hist_price > 0 else 0)
                v_liters_per_ton_km = v_total_liters / v_ton_km if v_ton_km > 0 else 0
                v_km_per_liter = v_mileage / v_total_liters if v_total_liters > 0 else 0

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("總行駛里程", f"{v_mileage:,.0f} km")
                c2.metric("總延噸公里", f"{v_ton_km:,.0f} Ton-km")
                c3.metric("真實平均油耗", f"{v_km_per_liter:,.2f} km/L")
                c4.metric("單位運輸能耗", f"{v_liters_per_ton_km:,.4f} L/噸公里")

                st.markdown("##### 📍 內部固定成本攤提")
                f_col1, f_col2, f_col3 = st.columns(3)
                with f_col1:
                    v_salary = st.number_input(f"{v_type} - 司機總薪資", value=50000, step=1000, key=f"sal_{v_type}")
                with f_col2:
                    v_depreciation = st.number_input(f"{v_type} - 折舊攤提", value=15000, step=1000, key=f"dep_{v_type}")
                with f_col3:
                    v_insurance = st.number_input(f"{v_type} - 保險規費", value=3000, step=1000, key=f"ins_{v_type}")
                
                v_fixed_cost = v_salary + v_depreciation + v_insurance

                st.markdown("##### 📍 外部委外報價設定")
                o_col1, o_col2, o_col3 = st.columns(3)
                with o_col1:
                    v_out_rate = st.number_input(f"{v_type} - 委外每噸公里單價", value=3.5 if "15" in v_type else 8.0, step=0.1, key=f"out_{v_type}")
                with o_col2:
                    v_out_admin = st.number_input(f"{v_type} - 委外行政管理費", value=2000, step=1000, key=f"admin_{v_type}")
                with o_col3:
                    v_base_price = st.number_input(f"{v_type} - 委外【油價基準】", value=30.0, step=0.5, key=f"base_{v_type}")

                v_inhouse_normalized_fuel = v_total_liters * v_base_price
                v_inhouse_total = v_inhouse_normalized_fuel + v_fixed_cost
                v_outsource_total = (v_ton_km * v_out_rate) + v_out_admin
                
                grand_inhouse_total += v_inhouse_total
                grand_outsource_total += v_outsource_total
                fleet_summary[v_type] = {'liters': v_total_liters, 'mileage': v_mileage, 'ton_km': v_ton_km}
                
                st.info(f"👉 【{v_type}】每噸公里真實成本：**${(v_inhouse_total/v_ton_km if v_ton_km > 0 else 0):,.2f}** 元 | 委外平均：**${(v_outsource_total/v_ton_km if v_ton_km > 0 else 0):,.2f}** 元")
                st.bar_chart(pd.DataFrame({"總成本": [v_inhouse_total, v_outsource_total]}, index=[f"自有 {v_type}", f"委外 {v_type}"]))
                
                report_lines.append(f"【{v_type} 車隊】")
                report_lines.append(f" - 總延噸公里：{v_ton_km:,.0f} | 總耗油量：{v_total_liters:,.1f} L | 單位能耗：{v_liters_per_ton_km:,.4f} L/Ton-km")
                report_lines.append(f" - 自有標準化總成本：${v_inhouse_total:,.0f} (每噸公里 ${v_inhouse_total/v_ton_km if v_ton_km>0 else 0:,.2f})")
                report_lines.append(f" - 委外預估總成本：${v_outsource_total:,.0f} (每噸公里 ${v_outsource_total/v_ton_km if v_ton_km>0 else 0:,.2f})")
                report_lines.append(f" - 小結：{'保留自有較優' if v_inhouse_total < v_outsource_total else '建議委外較優'}\n")

        st.session_state['fleet_summary'] = fleet_summary

        st.divider()
        st.header("🏆 企業全局總結 (Executive Summary)")
        ex_col1, ex_col2, ex_col3 = st.columns(3)
        ex_col1.metric("企業全自建總成本", f"${grand_inhouse_total:,.0f}")
        ex_col2.metric("企業全委外總成本", f"${grand_outsource_total:,.0f}")
        
        diff = grand_inhouse_total - grand_outsource_total
        if diff < 0:
            ex_col3.metric("全局最優策略", "維持全自建", delta=f"總計省下 ${abs(diff):,.0f}")
        else:
            ex_col3.metric("全局最優策略", "建議全面委外", delta=f"總計可省 ${abs(diff):,.0f}", delta_color="inverse")

        final_report = "=========================================\n物流車隊 TCO 與延噸公里 (多車種分級評估報告)\n=========================================\n\n"
        final_report += "\n".join(report_lines)
        final_report += "=========================================\n"
        final_report += f"【企業全局總結】\n - 全自建總成本：${grand_inhouse_total:,.0f}\n - 全委外總成本：${grand_outsource_total:,.0f}\n"
        final_report += f" - 最終建議：{'維持自建' if grand_inhouse_total < grand_outsource_total else '啟動委外'}\n"

        st.download_button(label="⬇️ 下載多維度戰情評估報告 (.txt)", data=final_report, file_name="車隊分級評估報告.txt", mime="text/plain", type="primary")

# ==========================================
# [頁籤 3] 模組三：ESG 碳排 
# ==========================================
with tab3:
    st.header("🍃 車隊碳排放與 ESG 成本衝擊分析 (依車種)")
    
    if 'fleet_summary' not in st.session_state or not st.session_state['fleet_summary']:
        st.info("請先至「模組一」與「模組二」完成清洗與油耗推算。")
    else:
        fleet_summary = st.session_state['fleet_summary']
        
        st.subheader("1. 各車種範疇一 (Scope 1) 碳排解析")
        emission_factor = st.number_input("柴油/無鉛碳排係數 (kg CO2e / 公升)", value=2.61, step=0.01)
        
        esg_records = []
        total_carbon_ton_all = 0
        
        for v_type, metrics in fleet_summary.items():
            carbon_kg = metrics['liters'] * emission_factor
            carbon_ton = carbon_kg / 1000
            total_carbon_ton_all += carbon_ton
            
            esg_records.append({
                "車種": v_type,
                "碳排放量 (kg CO2e)": round(carbon_kg, 1),
                "每噸公里碳排 (kg/Ton-km)": round(carbon_kg / metrics['ton_km'] if metrics['ton_km'] > 0 else 0, 4)
            })
            
        st.dataframe(pd.DataFrame(esg_records), use_container_width=True)
        st.bar_chart(pd.DataFrame(esg_records).set_index("車種")["碳排放量 (kg CO2e)"])

        st.divider()

        st.subheader("2. 內部碳定價與「碳費」衝擊")
        carbon_tax_rate = st.number_input("預估碳費費率 (新台幣 / 每公噸)", value=300, step=50)
        carbon_tax_cost = total_carbon_ton_all * carbon_tax_rate
        
        st.warning(f"💸 **企業總潛在碳費成本：** 若依每公噸 {carbon_tax_rate} 元徵收，企業將面臨額外 **${carbon_tax_cost:,.0f} 元** 的財務負擔。")
        st.info("透過上述的【每噸公里碳排】指標，您可以清楚看出哪一種車型是『碳排怪獸』。建議優先汰換該車型，或將該車型的運單轉交綠色物流商！")

# ==========================================
# [頁籤 4] 模組四：節油分潤引擎 (修復 ton_km 運算，司機列表正常顯示)
# ==========================================
with tab4:
    st.header("🏆 司機績效與節油分潤引擎")
    
    if 'cleaned_df' not in st.session_state:
        st.info("請先至「模組一」上傳資料並執行 AI 清洗。")
    else:
        df = st.session_state['cleaned_df'].copy()
        
        # 確保必要欄位存在並轉換為數字，重新計算 ton_km
        for col in ['mileage_km', 'weight_ton', 'fuel_liters']:
            if col not in df.columns: df[col] = 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        df['ton_km'] = df['mileage_km'] * df['weight_ton']
            
        if 'driver_name' not in df.columns: df['driver_name'] = '未知'
        df['driver_name'] = df['driver_name'].fillna('未知')
        if 'vehicle_type' not in df.columns: df['vehicle_type'] = '未分類'
        df['vehicle_type'] = df['vehicle_type'].fillna('未分類')
        
        driver_stats = df.groupby(['vehicle_type', 'driver_name']).agg(
            ton_km=('ton_km', 'sum'),
            fuel_liters=('fuel_liters', 'sum'),
            mileage=('mileage_km', 'sum')
        ).reset_index()
        
        driver_stats = driver_stats[driver_stats['ton_km'] > 0]
        driver_stats['efficiency'] = driver_stats['fuel_liters'] / driver_stats['ton_km']
        
        all_drivers = driver_stats['driver_name'].unique().tolist()
        
        st.markdown("本系統採用**「雙軌比較邏輯」**，請依據公司政策選擇結算模式（團隊標準 或 自我歷史標準），啟動獎金分潤機制！")
        st.divider()
        
        col_query1, col_query2 = st.columns(2)
        with col_query1:
            selected_driver = st.selectbox("👤 請選擇要查詢的司機：", all_drivers)
        
        if selected_driver:
            driver_data = driver_stats[driver_stats['driver_name'] == selected_driver].iloc[0]
            d_v_type = driver_data['vehicle_type']
            d_efficiency = driver_data['efficiency']
            d_ton_km = driver_data['ton_km']
            
            peer_df = driver_stats[driver_stats['vehicle_type'] == d_v_type].copy()
            peer_df['rank'] = peer_df['efficiency'].rank(method='min')
            N_peers = len(peer_df)
            actual_median = peer_df['efficiency'].median()
            
            d_rank = peer_df[peer_df['driver_name'] == selected_driver]['rank'].values[0]
            d_pr = (1 - (d_rank - 0.5) / N_peers) * 100 if N_peers > 0 else 100
            
            st.subheader("⚙️ 獎金結算參數設定")
            reward_mode = st.radio("🏆 選擇獎金結算模式 (雙軌制二擇一)：", ["模式 A：團隊中位數挑戰 (與公司標準比)", "模式 B：個人自我突破 (與過去自己比)"])
            
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                if "模式 A" in reward_mode:
                    target_efficiency = st.number_input("🎯 公司設定之中位數標準 (L/噸公里)", value=float(actual_median), step=0.001, format="%.4f")
                    target_label = "公司中位數標準"
                else:
                    target_efficiency = st.number_input("📉 司機過往三個月平均油耗 (L/噸公里)", value=float(d_efficiency * 1.1), step=0.001, format="%.4f")
                    target_label = "個人歷史基準"
            with col_b2:
                current_fuel_price = st.number_input("⛽ 當前油價單價 (用以計算省下金額)", value=30.0, step=0.5)
            with col_b3:
                profit_share_ratio = st.slider("🤝 司機分潤比例 (%)", min_value=10, max_value=100, value=40, step=5)
            
            st.divider()

            st.subheader(f"📊 {selected_driver} 的當月效能儀表板 (駕駛車型：{d_v_type})")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("當前運輸能耗", f"{d_efficiency:,.4f}", "L / Ton-km", delta_color="inverse")
            
            diff_to_target = target_efficiency - d_efficiency
            if diff_to_target > 0:
                m2.metric(f"目標：{target_label}", f"{target_efficiency:,.4f}", f"領先 {diff_to_target:,.4f}")
            else:
                m2.metric(f"目標：{target_label}", f"{target_efficiency:,.4f}", f"落後 {abs(diff_to_target):,.4f}", delta_color="inverse")
            
            m3.metric("真實 PR 值 (全車隊排名)", f"PR {d_pr:.0f}", f"擊敗 {d_pr:.0f}% 司機")
            success_prob = 95 if d_pr >= 80 else (75 if d_pr >= 50 else (40 if d_pr >= 25 else 15))
            m4.metric("結算日獎金達標機率", f"{success_prob}%")
            st.progress(success_prob / 100)

            st.markdown(f"#### 💰 分潤結算結果 ({reward_mode})")
            saved_liters = (target_efficiency - d_efficiency) * d_ton_km
            if saved_liters > 0:
                bonus = saved_liters * current_fuel_price * (profit_share_ratio / 100)
                st.success(f"✅ **【挑戰成功】** 您低於設定的「{target_label}」！共為公司省下 {saved_liters:.1f} 公升燃油。預計分潤獎金：**${bonus:,.0f}**")
            else:
                st.warning(f"❌ **【未達標】** 您的油耗高於設定的「{target_label}」。再減少 {abs(saved_liters):.1f} 公升即可達標領取獎金！")
            
            st.divider()
            st.subheader("💡 達標行動建議 (AI 行為指導)")
            if d_pr >= 80:
                st.markdown("🌟 **傳奇駕駛表現！** 您目前的駕駛習慣極佳，是車隊的模範。\n* **保持優勢：** 繼續維持目前的巡航速度與良好的胎壓管理。")
            elif d_pr >= 50:
                st.markdown("👍 **表現優良，仍有突破空間！**\n* **降低怠速：** 減少 10 分鐘怠速不熄火，就能穩穩進入 PR 80！\n* **平穩煞車：** 預判前方紅綠燈，使用引擎煞車代替急煞。")
            else:
                st.markdown("⚠️ **能效偏低，立即行動可大幅提升獎金！**\n* **黃金右腳：** 高速行駛時請開啟定速巡航，避免時速忽快忽慢。\n* **車輛定保：** 若已改善習慣但油耗仍高，請申請提早檢查車輛。")

# ==========================================
# [頁籤 5] 模組五：調度派車異常抓漏
# ==========================================
with tab5:
    st.header("🔍 派車健康度四象限矩陣 (Dispatch Health Quadrant)")
    
    if 'cleaned_df' not in st.session_state:
        st.info("請先至「模組一」上傳資料並執行 AI 清洗。")
    else:
        df_diag = st.session_state['cleaned_df'].copy()
        
        for col in ['weight_ton', 'mileage_km']:
            if col not in df_diag.columns: df_diag[col] = 0
            df_diag[col] = pd.to_numeric(df_diag[col], errors='coerce').fillna(0)
            
        df_diag['max_capacity'] = df_diag['vehicle_type'].str.extract(r'(\d+\.?\d*)').astype(float)
        df_diag['max_capacity'] = df_diag['max_capacity'].fillna(1.0) 
        df_diag['load_factor'] = (df_diag['weight_ton'] / df_diag['max_capacity']) * 100
        
        st.markdown("透過調整下方滑桿，動態界定您的企業對「長短途」與「高低載重」的標準，AI 將瞬間抓出調度異常的趟次。")
        
        col_t1, col_t2 = st.columns(2)
        with col_t1: x_threshold = st.slider("📏 路線長度分界點 (公里)", min_value=10, max_value=300, value=100, help="超過此數值視為長途，低於視為短途。")
        with col_t2: y_threshold = st.slider("📦 載重率分界點 (%)", min_value=10, max_value=100, value=50, help="低於此百分比視為低載重 (空間浪費)。")

        def get_quadrant(row):
            if row['mileage_km'] >= x_threshold and row['load_factor'] >= y_threshold: return '🌟 Q1: 黃金營運 (長途滿載)'
            elif row['mileage_km'] < x_threshold and row['load_factor'] >= y_threshold: return '⚠️ Q2: 大材小用 (短途滿載)'
            elif row['mileage_km'] < x_threshold and row['load_factor'] < y_threshold: return '🚨 Q3: 虧損出血 (短途空載)'
            else: return '💸 Q4: 運空氣 (長途空載)'

        df_diag['quadrant'] = df_diag.apply(get_quadrant, axis=1)

        color_scale = alt.Scale(
            domain=['🌟 Q1: 黃金營運 (長途滿載)', '⚠️ Q2: 大材小用 (短途滿載)', '🚨 Q3: 虧損出血 (短途空載)', '💸 Q4: 運空氣 (長途空載)'],
            range=['#10b981', '#f59e0b', '#ef4444', '#3b82f6']
        )

        scatter_chart = alt.Chart(df_diag).mark_circle(size=120, opacity=0.7).encode(
            x=alt.X('mileage_km', title='單趟行駛里程 (km)'),
            y=alt.Y('load_factor', title='載重空間利用率 (%)', scale=alt.Scale(domain=[0, 120])),
            color=alt.Color('quadrant', scale=color_scale, legend=alt.Legend(title="派車健康度", orient='bottom')),
            tooltip=[
                alt.Tooltip('date', title='出車日期'),
                alt.Tooltip('driver_name', title='負責司機'),
                alt.Tooltip('vehicle_type', title='派發車種'),
                alt.Tooltip('mileage_km', title='里程 (km)'),
                alt.Tooltip('weight_ton', title='載重 (噸)'),
                alt.Tooltip('load_factor', title='載重率 (%)', format='.1f')
            ]
        ).interactive()

        x_rule = alt.Chart(pd.DataFrame({'x': [x_threshold]})).mark_rule(color='red', strokeDash=[5,5]).encode(x='x')
        y_rule = alt.Chart(pd.DataFrame({'y': [y_threshold]})).mark_rule(color='red', strokeDash=[5,5]).encode(y='y')

        st.altair_chart(scatter_chart + x_rule + y_rule, use_container_width=True)

        st.divider()
        st.subheader("🚨 調度異常抓漏清單 (Action Required)")
        st.markdown("以下趟次落入 **Q3 (虧損出血)** 與 **Q4 (運空氣)** 區間，請立即檢視派車合理性，或考慮轉發給小車/回頭車。")
        
        outliers_df = df_diag[df_diag['quadrant'].isin(['🚨 Q3: 虧損出血 (短途空載)', '💸 Q4: 運空氣 (長途空載)'])]
        
        if not outliers_df.empty:
            display_cols = ['date', 'driver_name', 'vehicle_type', 'mileage_km', 'weight_ton', 'load_factor', 'quadrant']
            outliers_display = outliers_df[display_cols].copy()
            outliers_display['load_factor'] = outliers_display['load_factor'].apply(lambda x: f"{x:.1f}%")
            outliers_display.columns = ['日期', '司機', '車種', '里程(km)', '載重(噸)', '載重率', '診斷結果']
            
            st.dataframe(outliers_display, use_container_width=True)
            st.warning(f"⚠️ 系統偵測到本月共有 **{len(outliers_df)}** 筆異常調度。這嚴重拖累了車隊整體的 `L / 噸公里` 效能與碳排指標！")
        else:
            st.success("🎉 太棒了！在當前設定的標準下，您的車隊沒有出現嚴重的調度異常。")

# ==========================================
# [頁籤 6] 模組六：車輛汰舊換新 ROI (硬體效能交叉分析)
# ==========================================
with tab6:
    st.header("🔄 車輛汰舊換新與硬體效能評估 (Asset ROI)")
    
    if 'cleaned_df' not in st.session_state:
        st.info("請先至「模組一」上傳資料並執行 AI 清洗。")
    else:
        df_asset = st.session_state['cleaned_df'].copy()
        for col in ['mileage_km', 'weight_ton', 'fuel_liters', 'maintenance_cost']:
            if col in df_asset.columns:
                df_asset[col] = pd.to_numeric(df_asset[col], errors='coerce').fillna(0)
        
        if 'eco_standard' not in df_asset.columns: df_asset['eco_standard'] = '未知'
        if 'maintenance_cost' not in df_asset.columns: df_asset['maintenance_cost'] = 0
        df_asset['eco_standard'] = df_asset['eco_standard'].fillna('未知')
        df_asset['ton_km'] = df_asset['mileage_km'] * df_asset['weight_ton']
        
        # --- 1. 硬體世代交叉分析 (依環保期數) ---
        st.subheader("1. 車隊資產健康度診斷 (依環保期數/車齡)")
        
        asset_stats = df_asset.groupby(['vehicle_type', 'eco_standard']).agg(
            total_ton_km=('ton_km', 'sum'),
            total_liters=('fuel_liters', 'sum'),
            total_mileage=('mileage_km', 'sum'),
            total_maint=('maintenance_cost', 'sum')
        ).reset_index()
        
        asset_stats = asset_stats[asset_stats['total_ton_km'] > 0]
        asset_stats['efficiency (L/Ton-km)'] = asset_stats['total_liters'] / asset_stats['total_ton_km']
        asset_stats['maint_per_km (元/km)'] = asset_stats['total_maint'] / asset_stats['total_mileage']
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("**⛽ 各世代燃油效能比較 (越低越好)**")
            bar_fuel = alt.Chart(asset_stats).mark_bar(color='#f59e0b').encode(
                x='eco_standard:N', y='efficiency (L/Ton-km):Q', column='vehicle_type:N',
                tooltip=['vehicle_type', 'eco_standard', 'efficiency (L/Ton-km)']
            ).properties(width=150, height=300)
            st.altair_chart(bar_fuel)
            
        with col_c2:
            st.markdown("**🔧 各世代維修成本比較 (越低越好)**")
            bar_maint = alt.Chart(asset_stats).mark_bar(color='#ef4444').encode(
                x='eco_standard:N', y='maint_per_km (元/km):Q', column='vehicle_type:N',
                tooltip=['vehicle_type', 'eco_standard', 'maint_per_km (元/km)']
            ).properties(width=150, height=300)
            st.altair_chart(bar_maint)

        st.divider()

        # --- 2. 汰舊換新 ROI 精算機 ---
        st.subheader("2. 汰舊換新 ROI 精算機 (新購車輛財務決策)")
        st.markdown("評估『老舊車輛持續營運的隱藏成本 (高油耗+高維修+高碳費)』是否已大於『購買新車的貸款攤提』。")
        
        if 'license_plate' not in df_asset.columns: df_asset['license_plate'] = '未知車牌'
        plates = df_asset['license_plate'].unique().tolist()
        
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.markdown("#### 🚨 淘汰目標 (舊車現況)")
            selected_old_car = st.selectbox("請選擇欲評估汰換的車輛 (車牌)：", plates)
            annual_mileage = st.number_input("預估該車輛『未來一年』行駛里程 (km)：", value=50000, step=5000)
            annual_weight = st.number_input("預估該車輛『未來一年』載運總噸數 (噸)：", value=1500, step=100)
            
            old_car_data = df_asset[df_asset['license_plate'] == selected_old_car]
            o_miles = old_car_data['mileage_km'].sum()
            o_liters = old_car_data['fuel_liters'].sum()
            o_maint = old_car_data['maintenance_cost'].sum()
            
            o_l_per_km = o_liters / o_miles if o_miles > 0 else 0.35 
            o_maint_per_km = o_maint / o_miles if o_miles > 0 else 3.0 
            
            st.info(f"📍 歷史數據萃取：\n- 該車每公里耗油：{o_l_per_km:.3f} L\n- 該車每公里維修：${o_maint_per_km:.1f}")

        with col_r2:
            st.markdown("#### ✨ 投資目標 (新車預估)")
            new_car_price = st.number_input("新車購置總價 (元)：", value=2500000, step=100000)
            new_car_years = st.number_input("預計折舊攤提年限 (年)：", value=5, step=1)
            
            st.markdown("預估新車效能提升：")
            n_l_per_km = st.number_input("預估新車每公里耗油 (L/km)：", value=float(o_l_per_km * 0.75), step=0.01) 
            n_maint_per_km = st.number_input("預估新車每公里維修 (元/km)：", value=0.5, step=0.1) 
            
        st.markdown("#### 🌍 全域經濟參數")
        col_e1, col_e2 = st.columns(2)
        with col_e1: roi_fuel_price = st.number_input("預估未來油價 (元/L)", value=30.0, step=0.5)
        with col_e2: roi_carbon_tax = st.number_input("碳費單價 (元/噸 CO2e)", value=300, step=50)

        # 進行年度財務結算
        old_annual_fuel_cost = annual_mileage * o_l_per_km * roi_fuel_price
        old_annual_maint_cost = annual_mileage * o_maint_per_km
        old_annual_carbon_cost = (annual_mileage * o_l_per_km * 2.61 / 1000) * roi_carbon_tax
        old_total_operating_cost = old_annual_fuel_cost + old_annual_maint_cost + old_annual_carbon_cost

        new_annual_fuel_cost = annual_mileage * n_l_per_km * roi_fuel_price
        new_annual_maint_cost = annual_mileage * n_maint_per_km
        new_annual_carbon_cost = (annual_mileage * n_l_per_km * 2.61 / 1000) * roi_carbon_tax
        new_annual_depreciation = new_car_price / new_car_years
        new_total_cost = new_annual_fuel_cost + new_annual_maint_cost + new_annual_carbon_cost + new_annual_depreciation

        annual_savings = old_total_operating_cost - (new_annual_fuel_cost + new_annual_maint_cost + new_annual_carbon_cost)
        roi_diff = old_total_operating_cost - new_total_cost

        st.divider()
        st.subheader("💰 汰舊換新年度財務對決 (Annual ROI Impact)")
        
        roi_df = pd.DataFrame({
            "成本項目": ["年度油資", "年度維修保養", "年度碳費", "年度折舊攤提", "總計 (TCO)"],
            f"老車 ({selected_old_car})": [f"${old_annual_fuel_cost:,.0f}", f"${old_annual_maint_cost:,.0f}", f"${old_annual_carbon_cost:,.0f}", "$0", f"${old_total_operating_cost:,.0f}"],
            "換購新車": [f"${new_annual_fuel_cost:,.0f}", f"${new_annual_maint_cost:,.0f}", f"${new_annual_carbon_cost:,.0f}", f"${new_annual_depreciation:,.0f}", f"${new_total_cost:,.0f}"]
        })
        st.table(roi_df)

        if roi_diff > 0:
            st.success(f"🎉 **強烈建議換車！** 換新車每年省下的營運與維護費高達 **${annual_savings:,.0f}**，不僅完全 Cover 掉買新車的年度折舊，每年還能多幫公司賺進 **${roi_diff:,.0f}** 的淨利！")
        else:
            st.warning(f"⚖️ **暫緩換車或重新議價。** 雖然新車省油，但省下的費用仍不足以抵銷每年 **${new_annual_depreciation:,.0f}** 的新車折舊。建議老車繼續服役，或尋找更低單價的替代車款。")