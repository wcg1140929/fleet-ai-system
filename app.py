import streamlit as st
import pandas as pd
import google.generativeai as genai
import json

# ==========================================
# 1. 頁面設定與 API 初始化
# ==========================================
st.set_page_config(page_title="多維度車隊戰略與 ESG 決策中樞", layout="wide", page_icon="🚚")
st.title("🚚 車隊戰略、ESG 與司機績效分潤中樞")

api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    st.error("找不到 API Key，請確認 .streamlit/secrets.toml 設定。")
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["🧹 模組一：AI 資料清洗", "📊 模組二：車種分級成本決策", "🍃 模組三：ESG 碳排", "🏆 模組四：節油分潤引擎"])

# ==========================================
# [頁籤 1] 模組一：資料清洗 (新增抓取司機姓名)
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
                        "date": "標準化為 YYYY-MM-DD",
                        "vehicle_type": "字串(如 3.49噸, 15噸, 若無則填 '未分類')",
                        "driver_name": "字串(負責司機姓名, 若無則填 '未知')",
                        "license_plate": "字串(車牌)",
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
        df = st.session_state['cleaned_df']
        for col in ['mileage_km', 'weight_ton', 'fuel_cost', 'fuel_liters']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        if 'mileage_km' in df.columns and 'weight_ton' in df.columns:
            df['ton_km'] = df['mileage_km'] * df['weight_ton']
        else:
            df['ton_km'] = 0
            
        if 'vehicle_type' not in df.columns: df['vehicle_type'] = '未分類'
        df['vehicle_type'] = df['vehicle_type'].fillna('未分類')
        
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

        # --- 企業層級總結 ---
        st.divider()
        st.header("🏆 企業全局總結 (Executive Summary)")
        
        ex_col1, ex_col2, ex_col3 = st.columns(3)
        ex_col1.metric("企業全自建總成本", f"${grand_inhouse_total:,.0f}")
        ex_col2.metric("企業全委外總成本", f"${grand_outsource_total:,.0f}")
        
        diff = grand_inhouse_total - grand_outsource_total
        if diff < 0:
            ex_col3.metric("全局最優策略", "維持全自建", delta=f"總計省下 ${abs(diff):,.0f}")
            st.success("整體而言，您的車隊依然具備強大的成本競爭力，不建議全面委外。您可以針對單一虧損車種進行局部調整。")
        else:
            ex_col3.metric("全局最優策略", "建議全面委外", delta=f"總計可省 ${abs(diff):,.0f}", delta_color="inverse")
            st.warning("整體而言，全面委外可為企業省下可觀的費用！建議立刻啟動物流商議價流程。")

        # 產生明細下載
        final_report = "=========================================\n物流車隊 TCO 與延噸公里 (多車種分級評估報告)\n=========================================\n\n"
        final_report += "\n".join(report_lines)
        final_report += "=========================================\n"
        final_report += f"【企業全局總結】\n - 全自建總成本：${grand_inhouse_total:,.0f}\n - 全委外總成本：${grand_outsource_total:,.0f}\n"
        final_report += f" - 最終建議：{'維持自建' if grand_inhouse_total < grand_outsource_total else '啟動委外'}\n"

        st.download_button(
            label="⬇️ 下載多維度戰情評估報告 (.txt)",
            data=final_report,
            file_name="車隊分級評估報告.txt",
            mime="text/plain",
            type="primary"
        )

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
# [頁籤 4] 模組四：司機績效與節油分潤引擎 (雙軌二擇一與手動中位數)
# ==========================================
with tab4:
    st.header("🏆 司機績效與節油分潤引擎")
    
    if 'cleaned_df' not in st.session_state:
        st.info("請先至「模組一」上傳資料並執行 AI 清洗。")
    else:
        df = st.session_state['cleaned_df'].copy()
        if 'driver_name' not in df.columns: df['driver_name'] = '未知'
        df['driver_name'] = df['driver_name'].fillna('未知')
        
        # 1. 建立司機綜合效能資料庫
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
            # 取得該司機的當前資料
            driver_data = driver_stats[driver_stats['driver_name'] == selected_driver].iloc[0]
            d_v_type = driver_data['vehicle_type']
            d_efficiency = driver_data['efficiency']
            d_ton_km = driver_data['ton_km']
            d_liters = driver_data['fuel_liters']
            
            # 取得同型車背景數據 (用於計算真實 PR 值)
            peer_df = driver_stats[driver_stats['vehicle_type'] == d_v_type].copy()
            peer_df['rank'] = peer_df['efficiency'].rank(method='min')
            N_peers = len(peer_df)
            actual_median = peer_df['efficiency'].median()
            
            d_rank = peer_df[peer_df['driver_name'] == selected_driver]['rank'].values[0]
            d_pr = (1 - (d_rank - 0.5) / N_peers) * 100 if N_peers > 0 else 100
            
            # --- 雙軌二擇一參數設定區 ---
            st.subheader("⚙️ 獎金結算參數設定")
            reward_mode = st.radio(
                "🏆 選擇獎金結算模式 (雙軌制二擇一)：", 
                ["模式 A：團隊中位數挑戰 (與公司標準比)", "模式 B：個人自我突破 (與過去自己比)"]
            )
            
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                if "模式 A" in reward_mode:
                    # 讓公司手動輸入中位數，預設帶入真實中位數供參考
                    target_efficiency = st.number_input("🎯 公司設定之中位數標準 (L/噸公里)", value=float(actual_median), step=0.001, format="%.4f", help="預設帶入系統計算之實際中位數，公司可依目標手動調嚴或放寬。")
                    target_label = "公司中位數標準"
                else:
                    target_efficiency = st.number_input("📉 司機過往三個月平均油耗 (L/噸公里)", value=float(d_efficiency * 1.1), step=0.001, format="%.4f")
                    target_label = "個人歷史基準"
            with col_b2:
                current_fuel_price = st.number_input("⛽ 當前油價單價 (用以計算省下金額)", value=30.0, step=0.5)
            with col_b3:
                profit_share_ratio = st.slider("🤝 司機分潤比例 (%)", min_value=10, max_value=100, value=40, step=5)
            
            st.divider()

            # --- 動態效能儀表板 ---
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

            # --- 分潤結算結果 ---
            st.markdown(f"#### 💰 分潤結算結果 ({reward_mode})")
            
            saved_liters = (target_efficiency - d_efficiency) * d_ton_km
            if saved_liters > 0:
                bonus = saved_liters * current_fuel_price * (profit_share_ratio / 100)
                st.success(f"✅ **【挑戰成功】** 您低於設定的「{target_label}」！共為公司省下 {saved_liters:.1f} 公升燃油。預計分潤獎金：**${bonus:,.0f}**")
            else:
                st.warning(f"❌ **【未達標】** 您的油耗高於設定的「{target_label}」。再減少 {abs(saved_liters):.1f} 公升即可達標領取獎金！")
            
            st.divider()

            # --- 達標行動建議 ---
            st.subheader("💡 達標行動建議 (AI 行為指導)")
            if d_pr >= 80:
                st.markdown(f"""
                🌟 **傳奇駕駛表現！** 您目前的駕駛習慣極佳，是車隊的模範。
                * **保持優勢：** 繼續維持目前的巡航速度與良好的胎壓管理。
                * **綠色貢獻：** 您的優異表現本月已為地球減少了大量 CO2 碳排放，實踐了綠色運輸！
                """)
            elif d_pr >= 50:
                st.markdown("""
                👍 **表現優良，仍有突破空間！**
                * **降低怠速：** 根據數據，您只要每天減少 10 分鐘的怠速不熄火時間，就能穩穩進入 PR 80 領取最高獎金！
                * **平穩煞車：** 預判前方紅綠燈，使用引擎煞車代替急煞，可再提升 5% 效能。
                """)
            else:
                st.markdown("""
                ⚠️ **能效偏低，立即行動可大幅提升獎金！**
                * **黃金右腳：** 高速行駛時請開啟定速巡航 (Cruise Control)，避免時速忽快忽慢。
                * **裝載確認：** 請確認貨物裝載是否平均，重心偏移會導致輪胎阻力增加，嚴重消耗燃油。
                * **車輛定保：** 若已改善駕駛習慣但油耗仍高，請向調度室申請提早進行機油/濾網更換檢查。
                """)