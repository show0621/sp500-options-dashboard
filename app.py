import streamlit as st
from docx import Document
from PyPDF2 import PdfReader

# 1. 頁面設定
st.set_page_config(page_title="北區國稅局TP撰寫小助手", layout="wide")

# 2. 檔案讀取工具
def extract_text(uploaded_file):
    if uploaded_file is None: return ""
    ext = uploaded_file.name.split(".")[-1].lower()
    if ext == "docx":
        doc = Document(uploaded_file)
        return "\n".join([p.text for p in doc.paragraphs])
    elif ext == "pdf":
        return "\n".join([page.extract_text() for page in PdfReader(uploaded_file).pages])
    return ""

# 3. 標題
st.title("🛡️ 北區國稅局 TP 撰寫小助手")
st.info("已更新：功能分析將自動對標 11 項標準職能架構產出。")

# 4. 側邊欄
with st.sidebar:
    st.header("⚙️ 功能選單")
    selected_option = st.radio(
        "請選擇功能：",
        ["1. 功能分析報告撰擬", "2. 風險分析報告撰擬", "3. 常規交易原則案況說明", "4. 常規交易原則查核撰擬"]
    )
    st.divider()
    ref_file = st.file_uploader("上傳參考範例 (Word/PDF)", type=["docx", "pdf"])
    template_text = extract_text(ref_file)

# 5. 輸入區
st.subheader(f"當前執行：{selected_option}")
user_input = st.text_area("請貼上個案案況（例如：公司簡介、交易流程或功能描述）：", height=300)

# 6. 核心生成邏輯 (針對功能分析優化)
def generate_tp_report(option, case_data, ref_data):
    # 定義功能分析的 11 個標準項
    functional_items = [
        "1. 研究與發展", "2. 產品設計", "3. 採購與原物料管理", 
        "4. 製造、加工、裝配及測試", "5. 行銷、配銷及廣告", 
        "6. 運送、倉儲及存貨管理", "7. 品質管理", "8. 產品服務", 
        "9. 訓練及人員管理服務", "10. 信用及收款", "11. 管理、財務及法律服務"
    ]
    
    if "1. 功能分析" in option:
        output = "### 功能分析說明：\n\n"
        for item in functional_items:
            output += f"**{item}**\n"
            # 這裡模擬對兩個參與方的分析邏輯
            output += f"(1) OOO公司：(依據案況分析其在此項目的主要職能...)\n"
            output += f"(2) TR公司：(依據案況分析其在此項目的參與程度...)\n\n"
        return output
    else:
        return f"針對 {option} 的通用報告草案內容..."

# 7. 產出按鈕
if st.button("🚀 產出貼身報告", type="primary"):
    if not user_input:
        st.error("請輸入個案案況！")
    else:
        with st.spinner("正在對標 11 項職能架構撰擬中..."):
            report_result = generate_tp_report(selected_option, user_input, template_text)
            
            st.success("報告已產出！")
            st.divider()
            st.markdown(report_result)
            
            # 提供下載
            st.download_button("📥 下載產出結果 (.txt)", report_result, file_name="TP分析報告.txt")
