import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="부가세 마스터 V18", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V18 - 전 마켓 통합본)")

# --- [유틸리티 함수] ---
def smart_read_csv(file):
    for enc in ['cp949', 'utf-8-sig', 'utf-8', 'euc-kr']:
        try:
            file.seek(0)
            return pd.read_csv(file, encoding=enc)
        except: continue
    return None

def to_num(val):
    if pd.isna(val): return 0
    clean = str(val).replace(',', '').replace('원', '').replace(' ', '').strip()
    try: return float(clean)
    except: return 0

# --- [마켓별 정밀 분석 엔진] ---
def analyze_file_v18(file):
    fname = file.name
    try:
        df = smart_read_csv(file)
        if df is None: return "파일 읽기 실패"
        
        # 1. 스마트스토어
        if "스마트스토어" in fname:
            cols = ['과세매출','면세매출','신용카드매출전표','현금(소득공제)','현금(지출증빙)','기타']
            for c in cols: 
                if c in df.columns: df[c] = df[c].apply(to_num)
            t_df = df[df['과세매출'] > 0]
            f_df = df[df['면세매출'] > 0]
            return {
                "과세_신용": t_df['신용카드매출전표'].sum(),
                "과세_현금": t_df['현금(소득공제)'].sum() + t_df['현금(지출증빙)'].sum(),
                "과세_기타": t_df['기타'].sum(),
                "면세_신용": f_df['신용카드매출전표'].sum(),
                "면세_현금": f_df['현금(소득공제)'].sum() + f_df['현금(지출증빙)'].sum(),
                "면세_기타": f_df['기타'].sum()
            }
        
        # 2. 쿠팡
        elif "쿠팡" in fname:
            cols = ['신용카드(판매)','현금(판매)','기타(판매)','신용카드(환불)','현금(환불)','기타(환불)']
            for c in cols:
                if c in df.columns: df[c] = df[c].apply(to_num)
            df['신용'] = df['신용카드(판매)'] - df.get('신용카드(환불)', 0)
            df['현금'] = df['현금(판매)'] - df.get('현금(환불)', 0)
            df['기타'] = df['기타(판매)'] - df.get('기타(환불)', 0)
            t_df = df[df['과세유형'] == 'TAX']
            f_df = df[df['과세유형'] == 'FREE']
            return {
                "과세_신용": t_df['신용'].sum(), "과세_현금": t_df['현금'].sum(), "과세_기타": t_df['기타'].sum(),
                "면세_신용": f_df['신용'].sum(), "면세_현금": f_df['현금'].sum(), "면세_기타": f_df['기타'].sum()
            }

        # 3. 토스
        elif "토스" in fname:
            df['금액'] = df['결제수단 결제 금액'].apply(to_num)
            def classify(name):
                name_str = str(name)
                if any(x in name_str for x in ['커피', '오르조']): return 'TAX'
                if any(x in name_str for x in ['양배추', '당근', '감자']): return 'FREE'
                return 'TAX'
            df['유형'] = df['상품명'].apply(classify)
            t_df, f_df = df[df['유형']=='TAX'], df[df['유형']=='FREE']
            def get_sum(sub):
                card = sub[sub['결제수단'].str.contains('카드', na=False)]['금액'].sum()
                cash = sub[sub['결제수단'].str.contains('계좌|가상', na=False)]['금액'].sum()
                return card, cash, sub['금액'].sum() - (card + cash)
            tc, th, tg = get_sum(t_df); fc, fh, fg = get_sum(f_df)
            return {"과세_신용": tc, "과세_현금": th, "과세_기타": tg, "면세_신용": fc, "면세_현금": fh, "면세_기타": fg}

        # 4. 롯데ON & 11번가 (요약형)
        elif "롯데ON" in fname or "롯데온" in fname:
            for c in ['신용카드', '현금영수증', '기타', '휴대폰']:
                if c in df.columns: df[c] = df[c].apply(to_num)
            return {"과세_신용": df['신용카드'].sum(), "과세_현금": df['현금영수증'].sum(), "과세_기타": df['기타'].sum() + df.get('휴대폰', pd.Series([0])).sum(), "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
        
        elif "11번가" in fname:
            df = smart_read_csv(file) # 다시 읽기 (skiprows 적용 위해)
            # 11번가는 보통 6행부터 데이터
            df = pd.read_csv(file, skiprows=5, encoding='cp949')
            for c in ['신용카드결제', '현금영수증(소득공제용)', '현금영수증(지출증빙용)', '기타결제금액']:
                if c in df.columns: df[c] = df[c].apply(to_num)
            return {"과세_신용": df['신용카드결제'].sum(), "과세_현금": df['현금영수증(소득공제용)'].sum() + df['현금영수증(지출증빙용)'].sum(), "과세_기타": df['기타결제금액'].sum(), "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}

    except Exception as e:
        return f"분석 에러: {str(e)}"
    return "미지원 파일명"

# --- [메인 실행 화면] ---
uploaded_files = st.file_uploader("📂 정산 파일들을 올려주세요 (20개 이상 가능)", accept_multiple_files=True)

if uploaded_files:
    if st.button("🚀 부가세 통합 정산 및 분석 리포트 생성"):
        final_summary = {"과세": {"신용카드": 0, "현금영수증": 0, "기타": 0}, "면세": {"신용카드": 0, "현금영수증": 0, "기타": 0}}
        analysis_log = []
        
        for f in uploaded_files:
            res = analyze_file_v18(f)
            if isinstance(res, dict):
                row_total = sum(res.values())
                analysis_log.append({"파일명": f.name, "인식결과": "성공", "추출금액": f"{int(row_total):,}원"})
                # 합산 로직
                final_summary["과세"]["신용카드"] += res["과세_신용"]
                final_summary["과세"]["현금영수증"] += res["과세_현금"]
                final_summary["과세"]["기타"] += res["과세_기타"]
                final_summary["면세"]["신용카드"] += res["면세_신용"]
                final_summary["면세"]["현금영수증"] += res["면세_현금"]
                final_summary["면세"]["기타"] += res["면세_기타"]
            else:
                analysis_log.append({"파일명": f.name, "인식결과": f"실패 ({res})", "추출금액": "0원"})
        
        # 1. 분석 현황판 (디버깅용)
        st.subheader("📋 파일별 분석 상세 리포트")
        st.table(pd.DataFrame(analysis_log))
        
        # 2. 최종 결과 표
        df_report = pd.DataFrame(final_summary).T
        df_report['합계'] = df_report.sum(axis=1)
        st.subheader("📊 3분기 최종 통합 정산 결과")
        st.table(df_report.applymap(lambda x: f"{int(x):,}원"))

        # 3. 엑셀 다운로드 (xlsxwriter 설치 확인 필수)
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_report.to_excel(writer, sheet_name='최종보고서')
            st.download_button("📥 세무사 제출용 엑셀 다운로드", output.getvalue(), "부가세_통합정산_최종.xlsx")
        except:
            st.warning("⚠️ 엑셀 엔진(xlsxwriter)이 설치되지 않아 다운로드가 불가능합니다. requirements.txt를 확인해 주세요.")
