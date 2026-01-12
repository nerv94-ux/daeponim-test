import streamlit as st
import pandas as pd
import io

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V17", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V17 - 인코딩 & 모듈 수정본)")

# --- [유틸리티: 인코딩 무시하고 읽기] ---
def smart_read_csv(file):
    # 한국어 CSV가 주로 사용하는 3가지 인코딩을 순차적으로 시도합니다.
    for enc in ['cp949', 'utf-8-sig', 'utf-8', 'euc-kr']:
        try:
            file.seek(0)
            return pd.read_csv(file, encoding=enc)
        except:
            continue
    return None

def to_num(val):
    if pd.isna(val): return 0
    clean = str(val).replace(',', '').replace('원', '').replace(' ', '').strip()
    try: return float(clean)
    except: return 0

# --- [마켓 분석 엔진] ---
def analyze_file(file):
    fname = file.name
    try:
        df = smart_read_csv(file)
        if df is None: return "읽기 실패 (인코딩 확인 필요)"
        
        # 1. 스마트스토어
        if "스마트스토어" in fname:
            for c in ['과세매출','면세매출','신용카드매출전표','현금(소득공제)','현금(지출증빙)','기타']:
                if c in df.columns: df[c] = df[c].apply(to_num)
            t_df, f_df = df[df['과세매출']>0], df[df['면세매출']>0]
            return {"과세_신용": t_df['신용카드매출전표'].sum(), "과세_현금": t_df['현금(소득공제)'].sum() + t_df['현금(지출증빙)'].sum(), "과세_기타": t_df['기타'].sum(),
                    "면세_신용": f_df['신용카드매출전표'].sum(), "면세_현금": f_df['현금(소득공제)'].sum() + f_df['현금(지출증빙)'].sum(), "면세_기타": f_df['기타'].sum()}
        
        # 2. 쿠팡
        elif "쿠팡" in fname:
            for c in ['신용카드(판매)','현금(판매)','기타(판매)','신용카드(환불)','현금(환불)','기타(환불)']:
                if c in df.columns: df[c] = df[c].apply(to_num)
            df['신용'] = df['신용카드(판매)'] - df.get('신용카드(환불)', 0)
            df['현금'] = df['현금(판매)'] - df.get('현금(환불)', 0)
            df['기타'] = df['기타(판매)'] - df.get('기타(환불)', 0)
            t_df, f_df = df[df['과세유형']=='TAX'], df[df['과세유형']=='FREE']
            return {"과세_신용": t_df['신용'].sum(), "과세_현금": t_df['현금'].sum(), "과세_기타": t_df['기타'].sum(),
                    "면세_신용": f_df['신용'].sum(), "면세_현금": f_df['현금'].sum(), "면세_기타": f_df['기타'].sum()}
        
        # (기타 마켓 생략 - 동일한 방식으로 보강)
    except Exception as e:
        return f"분석 오류: {e}"
    return "미지원 양식"

# --- [메인 레이아웃] ---
with st.sidebar:
    st.header("📅 정산 설정")
    target_period = st.text_input("정산 기간 (예: 2025년 3분기)", "2025년 7~9월")

uploaded_files = st.file_uploader("📂 정산 파일들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    # 업로드 파일 현황판
    st.subheader("📋 업로드된 파일 현황")
    file_status = []
    for f in uploaded_files:
        file_status.append({"파일명": f.name, "크기": f"{f.size/1024:.1f} KB", "상태": "대기 중"})
    st.table(pd.DataFrame(file_status))

    if st.button("🚀 전체 통합 정산 시작"):
        final_summary = {"과세": {"신용카드": 0, "현금영수증": 0, "기타": 0}, "면세": {"신용카드": 0, "현금영수증": 0, "기타": 0}}
        
        for f in uploaded_files:
            res = analyze_file(f)
            if isinstance(res, dict):
                for k, v in res.items():
                    cat, typ = k.split('_')
                    typ_map = {"신용": "신용카드", "현금": "현금영수증", "기타": "기타"}
                    final_data_cat = "과세" if cat == "과세" else "면세"
                    final_summary[final_data_cat][typ_map[typ]] += v
        
        # 결과 표
        df_report = pd.DataFrame(final_summary).T
        df_report['합계'] = df_report.sum(axis=1)
        st.subheader("📊 최종 정산 결과")
        st.table(df_report.applymap(lambda x: f"{int(x):,}원"))

        # 엑셀 내보내기 (xlsxwriter 에러 해결 적용)
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_report.to_excel(writer, sheet_name='최종결과')
            
            st.download_button(label="📥 세무사 제출용 엑셀 다운로드", data=output.getvalue(), file_name=f"부가세정산_{target_period}.xlsx")
        except:
            st.error("엑셀 파일 생성 중 오류가 발생했습니다. requirements.txt를 확인해 주세요.")
