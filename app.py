import streamlit as st
from docx import Document
from PyPDF2 import PdfReader
import io

# 1. 設定網頁標題與版面
st.set_page_config(page_title="北區國稅局TP撰寫小助手", layout="wide")

# 2. 檔案讀取輔助函式
def extract_text_from_upload(uploaded_file):
    if uploaded_file is None:
        return ""
    
    file_details = uploaded_file.name.split(".")
    extension = file_details[-1].lower()
    
    if extension == "docx":
        doc = Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs])
    elif extension == "pdf":
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    return ""

# 3. 標題與資訊區
st.title("🛡️ 北區國稅局 TP 撰寫小助手")
st.info("系統會參考您上傳的「範例規格」，針對個案內容進行貼身撰擬。")

# 4. 側邊欄：功能選擇與範例上傳
with st.sidebar:
    st.header("⚙️ 功能選單")
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
    st.header("📂 參考範例上傳")
    ref_file = st.file_uploader(
        f"請上傳「{selected_option.split('. ')[1]}」的範例格式 (Word 或 PDF)",
        type=["docx", "pdf"]
    )
    
    if ref_file:
        st.success(f"已讀取：{ref_file.name}")
        # 提取範例文字備用
        template_content = extract_text_from_upload(ref_file)
    else:
        st.warning("請上傳範例檔案以獲取最佳撰寫效果。")
        template_content = ""

# 5. 主要操作介面
st.subheader(f"當前執行：{selected_option}")

# 根據選項動態設定說明文字
prompt_hints = {
    "1. 功能分析報告撰擬": "請貼上個案之功能分析表格或職能描述：",
    "2. 風險分析報告撰擬": "請貼上個案之風險分析數據或內容：",
    "3. 常規交易原則案況說明": "請貼上個案交易背景與流程說明：",
    "4. 常規交易原則查核撰擬": "請貼上受控交易之查核具體事證："
}

user_input = st.text_area(
    prompt_hints[selected_option],
    height=300,
    max_chars=5000,
    placeholder="請在此貼上個案內容，系統將結合上傳之範例進行撰寫..."
)

# 6. 報告產出邏輯
if st.button("🚀 產出貼身報告", type="primary"):
    if not user_input.strip():
        st.error("請先貼上個案資料！")
    elif not ref_file:
        st.warning("提醒：您未上傳範例，系統將使用一般通用格式生成。")
        
    with st.spinner("正在分析範例規格並套用至個案中..."):
        st.divider()
        st.markdown("### 📄 產出報告結果 (草案)")
        
        # 這裡模擬 AI 結合「範例文字」與「個案文字」的邏輯
        # 實務上您可以將 template_content 與 user_input 一併傳給 LLM API
        
        col1, col2 = st.columns(2)
        with col1:
            st.caption("✅ 參考範例規格確認")
            if template_content:
                st.text_area("偵測到的範例文字片段：", template_content[:300] + "...", height=100, disabled=True)
            else:
                st.write("無上傳範例，使用系統預設邏輯。")
        
        with col2:
            st.caption("✅ 個案資料摘要")
            st.write(f"輸入字數：{len(user_input)} 字")

        # 最終呈現區
        st.success("報告撰寫完成！")
        
        final_draft = f"""
        【{selected_option} - 擬稿】
        
        一、 依據您上傳之「{ref_file.name if ref_file else '通用規格'}」格式：
        二、 針對本個案「{user_input[:20]}...」之查核意見如下：
        
        (以下為模擬生成的貼身報告內容)
        1. 職能分析：經查本案參與方...
        2. 風險分配：符合範例中關於{ "範例邏輯萃取" if ref_file else "一般常規" }之規範...
        3. 結論：本案建議...
        
        --------------------------------------------
        (以上內容可直接複製至 Word 進行後續微調)
        """
        st.info(final_draft)
        
        # 下載按鈕 (純文字版)
        st.download_button(
            label="📥 下載報告草案 (.txt)",
            data=final_draft,
            file_name=f"{selected_option}_產出結果.txt",
            mime="text/plain"
        )
