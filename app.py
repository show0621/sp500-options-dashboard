import streamlit as st

# 設定網頁標題與圖示
st.set_page_config(page_title="北區國稅局TP撰寫小助手", layout="wide")

# 自定義標題區
st.title("🛡️ 北區國稅局 TP 撰寫小助手")
st.info("本系統將參考既有範例規格，協助產出符合邏輯之移轉訂價相關報告初稿。")

# --- 側邊欄：功能選擇 ---
with st.sidebar:
    st.header("功能選單")
    selected_option = st.radio(
        "請選擇要執行的功能：",
        [
            "1. 功能分析報告撰擬",
            "2. 風險分析報告撰擬",
            "3. 常規交易原則案況說明",
            "4. 常規交易原則查核撰擬"
        ]
    )
    st.divider()
    st.caption("建議操作：貼上個案資料後點擊『產出報告』。")

# --- 核心邏輯區：定義範例規格與邏輯 ---
# 提示：未來你可以將這些字串替換成你實際的公務範例
def get_template_logic(feature_type):
    if feature_type == "功能分析":
        return "【範例邏輯：功能分析】應包含受控交易參與方之研發、採購、製造、銷售等職能描述，並區分主要與次要功能。"
    elif feature_type == "風險分析":
        return "【範例邏輯：風險分析】應涵蓋市場風險、庫存風險、信用風險等，並分析風險承擔者與補償機制。"
    elif feature_type == "案況說明":
        return "【範例邏輯：案況說明】需釐清交易流程圖、資金流向及各參與方之契約義務。"
    elif feature_type == "查核撰擬":
        return "【範例邏輯：查核撰擬】重點在於常規交易範圍之選取、可比性調整之合理性說明。"
    return ""

# --- 主要操作介面 ---
st.subheader(f"當前執行：{selected_option}")

# 根據選項顯示說明
description_map = {
    "1. 功能分析報告撰擬": "請貼上「功能分析表格」內容（5000字以內）：",
    "2. 風險分析報告撰擬": "請貼上「風險分析表格」內容（5000字以內）：",
    "3. 常規交易原則案況說明": "請貼上「交易流程及背景」內容（5000字以內）：",
    "4. 常規交易原則查核撰擬": "請貼上「受控交易說明」內容（5000字以內）："
}

user_input = st.text_area(
    description_map[selected_option],
    height=350,
    max_chars=5000,
    placeholder="在此貼上個案資料..."
)

# 按鈕觸發
if st.button("🚀 產出貼身報告", type="primary"):
    if not user_input.strip():
        st.warning("請先輸入資料喔！")
    else:
        with st.spinner("正在結合範例規格與個案邏輯，請稍候..."):
            # 這裡模擬報告生成的邏輯處理
            feature_key = selected_option.split(". ")[1].replace("報告撰擬", "").replace("撰擬", "")
            logic_ref = get_template_logic(feature_key)
            
            st.success("報告已產出！")
            st.divider()
            
            # 顯示結果區塊
            st.markdown("### 📄 產出報告結果 (草案)")
            
            # 範例輸出架構 (這部分可串接 LLM 或 規則替換)
            result_content = f"""
            ### {selected_option} - 個案報告
            
            **【參考範例邏輯】** {logic_ref}
            
            **【個案內容摘要】** {user_input[:200]}... (已根據個案貼身調整內容)
            
            **【報告建議草案】**
            1. 依據本局查核範例規格，本案受控交易之實質經濟行為分析如下...
            2. 針對個案所述之「{user_input[:20]}」，符合常規交易原則之說明如下...
            3. 結論：本案經評估後，建議...
            """
            st.markdown(result_content)
            
            # 提供複製/下載按鈕
            st.button("📋 複製報告全文", on_click=lambda: st.write("已模擬複製"))
