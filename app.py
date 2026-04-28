import streamlit as st
from docx import Document
from PyPDF2 import PdfReader
from openai import OpenAI

# ==========================================
# 1. 設定 Open WebUI 的連線資訊 (局內專用)
# ==========================================
OPEN_WEBUI_BASE_URL = "http://10.98.250.115:3000/api/v1"  
OPEN_WEBUI_API_KEY = "sk-dummy-key-for-internal-use"  # 免驗證通關金鑰
MODEL_NAME = "gemma4-e4b" 

# 初始化 OpenAI 客戶端，將目標指向局內伺服器
try:
    client = OpenAI(
        base_url=OPEN_WEBUI_BASE_URL,
        api_key=OPEN_WEBUI_API_KEY
    )
except Exception as e:
    st.error(f"AI 客戶端初始化失敗，請檢查網路連線：{e}")

# ==========================================
# 2. 網頁基本設定與輔助工具
# ==========================================
st.set_page_config(page_title="北區國稅局TP撰寫小助手", layout="wide")

def extract_text(uploaded_file):
    if uploaded_file is None: return ""
    try:
        ext = uploaded_file.name.split(".")[-1].lower()
        if ext == "docx":
            doc = Document(uploaded_file)
            return "\n".join([p.text for p in doc.paragraphs])
        elif ext == "pdf":
            return "\n".join([page.extract_text() for page in PdfReader(uploaded_file).pages if page.extract_text()])
    except Exception as e:
        st.error(f"檔案讀取失敗：{e}")
        return ""
    return ""

# ==========================================
# 3. 核心 AI 生成邏輯
# ==========================================
def generate_tp_report_with_ai(option, case_data, ref_data):
    # 防呆機制：如果沒有上傳範例，給予預設提示
    if not ref_data:
        ref_data = "未提供範例，請直接依據標準公文格式與移轉訂價查核準則撰寫。"

    # 針對不同功能，給予 AI 不同的「系統人設與規則」
    if "1. 功能分析" in option:
        system_prompt = """
        你是北區國稅局移轉訂價查核的資深專家。
        你的任務是根據使用者提供的【個案資料】，參考【官方範例格式】的語氣、排版與文字邏輯，撰寫一份客製化的「功能分析報告」。
        
        【嚴格要求】：
        1. 必須嚴格列出並對標 11 項標準職能：1.研究與發展、2.產品設計、3.採購與原物料管理、4.製造加工裝配及測試、5.行銷配銷及廣告、6.運送倉儲及存貨管理、7.品質管理、8.產品服務、9.訓練及人員管理服務、10.信用及收款、11.管理財務及法律服務。
        2. 在每一項職能下，請務必根據【個案資料】的內容，具體說明雙方公司（例如母公司與子公司）實際負責的作業與參與程度。
        3. 絕對不可以輸出「(依據案況分析其在此項目的主要職能)」這類佔位符號，你必須真的把分析內容寫出來。如果個案資料未提及該項職能，請寫「依據案況，雙方未顯著執行此功能」或合理推斷。
        4. 語氣客觀嚴謹，直接輸出報告本文，不要有任何問候語或結語。
        """
    elif "2. 風險分析" in option:
        system_prompt = "你是北區國稅局移轉訂價專家。請參考【官方範例格式】，針對【個案資料】撰寫「風險分析報告」，需涵蓋市場、庫存、信用等風險，並釐清承擔者。"
    elif "3. 常規交易原則案況說明" in option:
        system_prompt = "你是北區國稅局移轉訂價專家。請參考【官方範例格式】，將【個案資料】轉化為條理分明的「案況說明」，釐清交易流程與資金流向。"
    elif "4. 常規交易原則查核撰擬" in option:
        system_prompt = "你是北區國稅局移轉訂價專家。請參考【官方範例格式】，針對【個案資料】撰寫「查核報告」，說明常規交易範圍之選取與可比性調整之合理性。"
    else:
        system_prompt = "你是專業的稅務查核助手，請整理以下資料。"

    user_prompt = f"【官方範例格式】（請模仿此語氣與架構）：\n{ref_data}\n\n====================\n\n【個案資料】（請從此處萃取事實進行填寫）：\n{case_data}"

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2  # 較低的溫度可讓報告更嚴謹、不隨意幻想
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"連線內部 AI 發生錯誤，請確認 IP 網址是否正確且伺服器正常運作中。\n錯誤詳細資訊：{e}"

# ==========================================
# 4. 前端介面設計
# ==========================================
st.title("🛡️ 北區國稅局 TP 撰寫小助手")
st.info(f"🟢 已連線至局內 AI 伺服器 (模型: {MODEL_NAME})")

with st.sidebar:
    st.header("⚙️ 功能選單")
    selected_option = st.radio(
        "請選擇功能：",
        ["1. 功能分析報告撰擬", "2. 風險分析報告撰擬", "3. 常規交易原則案況說明", "4. 常規交易原則查核撰擬"]
    )
    st.divider()
    ref_file = st.file_uploader("上傳參考範例 (Word/PDF)", type=["docx", "pdf"])
    template_text = extract_text(ref_file)
    if template_text:
        st.success("✅ 範例檔案讀取成功！")

st.subheader(f"當前執行：{selected_option}")
user_input = st.text_area(
    "請貼上個案案況（例如：公司簡介、交易合約摘要或內部流程描述）：", 
    height=300,
    placeholder="在此貼上您查核到的個案事實..."
)

# ==========================================
# 5. 執行與輸出區塊
# ==========================================
if st.button("🚀 產出貼身報告", type="primary"):
    if not user_input.strip():
        st.error("請先輸入個案案況！")
    else:
        with st.spinner("🧠 局內 AI 正在閱讀案況並對標格式中，這可能需要幾十秒，請稍候..."):
            
            # 呼叫 AI 生成報告
            report_result = generate_tp_report_with_ai(selected_option, user_input, template_text)
            
            st.success("✨ 報告已產出！")
            st.divider()
            
            # 顯示結果
            st.markdown("### 📄 產出結果草案")
            st.markdown(report_result)
            
            st.divider()
            # 提供純文字下載
            st.download_button(
                label="📥 下載產出結果 (.txt)", 
                data=report_result, 
                file_name=f"{selected_option.split('. ')[1]}_AI草案.txt"
            )
