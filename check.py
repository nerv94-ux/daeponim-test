import streamlit as st
import pandas as pd
import io
from datetime import datetime
import calendar

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V16", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V16 - 엑셀 내보내기 포함)")

# --- [유틸리티 함수] ---
def to_num(val):
    if pd.isna(val): return 0
    if isinstance(val, (int, float)): return val
    clean = str(val).replace(',', '').replace('원', '').replace(' ', '').strip()
    try: return float(clean)
    except: return 0

# --- [마켓별 개별 분석 엔진] ---
def analyze_market_file(file):
    fname = file.name
    try:
        # 1. 스마트스토어 상세 내역
        if "스마트스토어" in fname and "상세내역" in fname:
            df = pd.read_csv(file)
            for c in ['과세매출','면세매출','신용카드매출전표','현금(소득공제)','현금(지출증빙)','기타']:
                df[c] = df[c].apply(to_num)
            t_df, f_df = df[df['과세매출']>0], df[df['면세매출']>0]
            return {
                "과세_신용": t_df['신용카드매출전표'].sum(),
                "과세_현금": t_df['현금(소득공제)'].sum() + t_df['현금(지출증빙)'].sum(),
                "과세_기타": t_df['기타'].sum(),
                "면세_신용": f_df['신용카드매출전표'].sum(),
                "면세_현금": f_df['현금(소득공제)'].sum() + f_df['현금(지출증빙)'].sum(),
                "면세_기타": f_df['기타'].sum()
            }

        # 2. 쿠팡 결제수단별 매출내역
        elif "쿠팡" in fname:
            df = pd.read_csv(file)
            for c in ['신용카드(판매)','현금(판매)','기타(판매)','신용카드(환불)','현금(환불)','기타(환불)']:
                df[c] = df[c].apply(to_num)
            df['신용'] = df['신용카드(판매)'] - df['신용카드(환불)']
            df['현금'] = df['현금(판매)'] - df['현금(환불)']
            df['기타'] = df['기타(판매)'] - df['기타(환불)']
            t_df, f_df = df[df['과세유형']=='TAX'], df[df['과세유형']=='FREE']
            return {
                "과세_신용": t_df['신용'].sum(), "과세_현금": t_df['현금'].sum(), "과세_기타": t_df['기타'].sum(),
                "면세_신용": f_df['신용'].sum(), "면세_현금": f_df['현금'].sum(), "면세_기타": f_df['기타'].sum()
            }

        # 3. 토스 건별 정산
        elif "토스" in fname:
            df = pd.read_csv(file)
            df['금액'] = df['결제수단 결제 금액'].apply(to_num)
            def classify(name):
                if any(x in str(name) for x in ['커피', '오르조']): return 'TAX'
                if any(x in str(name) for x in ['양배추', '당근']): return 'FREE'
                return 'TAX'
            df['유형'] = df['상품명'].apply(classify)
            t_df, f_df = df[df['유형']=='TAX'], df[df['유형']=='FREE']
            def get_sum(sub):
                card = sub[sub['결제수단'].str.contains('카드', na=False)]['금액'].sum()
                cash = sub[sub['결제수단'].str.contains('계좌|가상', na=False)]['금액'].sum()
                return card, cash, sub['금액'].sum() - (card+cash)
            tc, th, tg = get_sum(t_df)
            fc, fh, fg = get_sum(f_df)
            return {"과세_신용": tc, "과세_현금": th, "과세_기타": tg, "면세_신용": fc, "면세_현금": fh, "면세_기타": fg}

        # 4. 11번가 일자별 매출
        elif "11번가" in fname:
            df = pd.read_csv(file, skiprows=5)
            for c in ['신용카드결제','현금영수증(소득공제용)','현금영수증(지출증빙용)','기타결제금액']:
                df[c] = df[c].apply(to_num)
            # 11번가는 가공품 위주로 우선 분류
            return {
                "과세_신용": df['신용카드결제'].sum(), 
                "과세_현금": df['현금영수증(소득공제용)'].sum() + df['현금영수증(지출증빙용)'].sum(),
                "과세_기타": df['기타결제금액'].sum(),
                "면세_신용": 0, "면세_현금": 0, "면세_기타": 0
            }

    except Exception as e:
        st.error(f"⚠️ {fname} 분석 중 오류: {e}")
    return None

# --- [메인 레이아웃] ---
with st.sidebar:
    st.header("📅 정산 기간")
    target_year = st.selectbox("연도", [2025, 2026], index=0)
    start_m = st.selectbox("시작 월", list(range(1, 13)), index=6) # 7월
    end_m = st.selectbox("종료 월", list(range(1, 13)), index=8)   # 9월

uploaded_files = st.file_uploader("📂 정산 파일들을 한꺼번에 올려주세요 (20개 이상 가능)", accept_multiple_files=True)

if st.button("🚀 전체 통합 정산 및 엑셀 생성"):
    if uploaded_files:
        final_summary = {
            "과세": {"신용카드": 0, "현금영수증": 0, "기타": 0},
            "면세": {"신용카드": 0, "현금영수증": 0, "기타": 0}
        }
        
        for f in uploaded_files:
            res = analyze_market_file(f)
            if res:
                final_summary["과세"]["신용카드"] += res["과세_신용"]
                final_summary["과세"]["현금영수증"] += res["과세_현금"]
                final_summary["과세"]["기타"] += res["과세_기타"]
                final_summary["면세"]["신용카드"] += res["면세_신용"]
                final_summary["면세"]["현금영수증"] += res["면세_현금"]
                final_summary["면세"]["기타"] += res["면세_기타"]

        # 1. 화면 출력용 표 생성
        df_report = pd.DataFrame(final_summary).T
        df_report['합계'] = df_report.sum(axis=1)
        st.subheader(f"📊 {start_m}~{end_m}월 통합 부가세 정산 결과")
        st.table(df_report.applymap(lambda x: f"{int(x):,}원"))

        # 2. 엑셀 파일 생성 (내보내기 기능)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_report.to_excel(writer, sheet_name='부가세정산_최종')
        
        st.download_button(
            label="📥 세무사 제출용 통합 엑셀 다운로드",
            data=output.getvalue(),
            file_name=f"유기농부_부가세정산_{start_m}_{end_m}월.xlsx",
            mime="application/vnd.ms-excel"
        )
        
        # 3. 텍스트 요약 (복사용)
        st.info("💡 아래 텍스트를 복사해서 세무사님께 카톡으로 먼저 보내실 수도 있습니다.")
        st.code(f"""
[유기농부 {start_m}~{end_m}월 정산 요약]
- 과세 총합: {int(df_report.loc['과세', '합계']):,}원
- 면세 총합: {int(df_report.loc['면세', '합계']):,}원
- 전체 합계: {int(df_report['합계'].sum()):,}원
        """)
    else:
        st.warning("먼저 파일을 업로드해 주세요.")
