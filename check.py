import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V23", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V23 - 상세 리포트 복제형)")

# --- [1. 유틸리티 함수] ---
def to_n(val):
    if pd.isna(val): return 0
    if isinstance(val, (int, float)): return float(val)
    clean = re.sub(r'[^\d.-]', '', str(val))
    try: return float(clean) if clean else 0
    except: return 0

def find_col(df, keyword):
    keyword = keyword.replace(" ", "").lower()
    for col in df.columns:
        if keyword in str(col).replace(" ", "").lower(): return col
    return None

def universal_loader(file):
    fname = file.name
    # 엑셀 시도
    try:
        file.seek(0)
        return pd.read_excel(file)
    except: pass
    
    # CSV 시도 (인코딩 및 스킵 로직)
    for enc in ['utf-8-sig', 'cp949', 'utf-8', 'euc-kr']:
        try:
            file.seek(0)
            if "11번가" in fname:
                df = pd.read_csv(file, encoding=enc, skiprows=5)
            else:
                df = pd.read_csv(file, encoding=enc)
            if df.shape[1] > 2: return df
        except: continue
    return None

# --- [2. 마켓별 상세 분석 엔진] ---
def analyze_detailed(file):
    fname = file.name
    df = universal_loader(file)
    if df is None: return None
    
    results = []
    try:
        # A. 스마트스토어
        if find_col(df, "과세매출") and find_col(df, "기준일"):
            c_date, c_tax, c_free = find_col(df, "기준일"), find_col(df, "과세매출"), find_col(df, "면세매출")
            c_card, c_cash_s, c_cash_j, c_etc = find_col(df, "신용카드"), find_col(df, "현금(소득"), find_col(df, "현금(지출"), find_col(df, "기타")
            
            df['month'] = pd.to_datetime(df[c_date]).dt.month.astype(str) + "월"
            for m, m_df in df.groupby('month'):
                res = {"마켓": "스마트스토어", "월": m, "과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
                for _, r in m_df.iterrows():
                    card, cash, etc = to_n(r[c_card]), to_n(r.get(c_cash_s,0))+to_n(r.get(c_cash_j,0)), to_n(r.get(c_etc,0))
                    if to_n(r[c_tax]) > 0: res["과세_신용"]+=card; res["과세_현금"]+=cash; res["과세_기타"]+=etc
                    if to_n(r[c_free]) > 0: res["면세_신용"]+=card; res["면세_현금"]+=cash; res["면세_기타"]+=etc
                results.append(res)

        # B. 쿠팡
        elif find_col(df, "과세유형"):
            c_date, c_type = find_col(df, "매출인식일"), find_col(df, "과세유형")
            df['month'] = pd.to_datetime(df[c_date]).dt.month.astype(str) + "월"
            for m, m_df in df.groupby('month'):
                res = {"마켓": "쿠팡", "월": m, "과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
                for _, r in m_df.iterrows():
                    card = to_n(r[find_col(df,"신용카드(판매)")]) - to_n(r.get(find_col(df,"신용카드(환불)"),0))
                    cash = to_n(r[find_col(df,"현금(판매)")]) - to_n(r.get(find_col(df,"현금(환불)"),0))
                    etc = to_n(r[find_col(df,"기타(판매)")]) - to_n(r.get(find_col(df,"기타(환불)"),0))
                    p = "과세" if "TAX" in str(r[c_type]).upper() else "면세"
                    res[f"{p}_신용"]+=card; res[f"{p}_현금"]+=cash; res[f"{p}_기타"]+=etc
                results.append(res)

        # C. 롯데ON & 11번가
        elif "롯데ON" in fname or "롯데온" in fname or "11번가" in fname:
            m_name = "롯데ON" if "롯데" in fname else "11번가"
            c_date = find_col(df, "매출월") or find_col(df, "정산확정처리일")
            c_card = find_col(df, "신용카드") or find_col(df, "신용카드결제")
            c_cash = find_col(df, "현금영수증") or find_col(df, "현금영수증(소득")
            c_etc = find_col(df, "기타") or find_col(df, "기타결제")
            c_phone = find_col(df, "휴대폰")
            
            df['month'] = df[c_date].apply(lambda x: str(int(str(x)[4:6]))+"월" if len(str(x))==6 else str(pd.to_datetime(x).month)+"월")
            for m, m_df in df.groupby('month'):
                is_tax = "가공품" in fname or to_n(m_df[find_col(df,"과세매출")].sum()) > 0 if find_col(df,"과세매출") else True
                p = "과세" if is_tax else "면세"
                res = {"마켓": m_name, "월": m, "과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
                res[f"{p}_신용"] = m_df[c_card].apply(to_n).sum() if c_card else 0
                res[f"{p}_현금"] = m_df[c_cash].apply(to_n).sum() if c_cash else 0
                res[f"{p}_기타"] = m_df[c_etc].apply(to_n).sum() if c_etc else 0
                if c_phone: res[f"{p}_기타"] += m_df[c_phone].apply(to_n).sum()
                results.append(res)

        # D. 토스
        elif "토스" in fname:
            c_date = find_col(df, "결제일시")
            df['month'] = pd.to_datetime(df[c_date]).dt.month.astype(str) + "월"
            for m, m_df in df.groupby('month'):
                res = {"마켓": "토스", "월": m, "과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
                for _, r in m_df.iterrows():
                    p = "면세" if any(x in str(r[find_col(df,"상품명")]) for x in ['양배추','당근','감자','무농약']) else "과세"
                    amt, method = to_n(r[find_col(df,"결제수단결제금액")]), str(r[find_col(df,"결제수단")])
                    if "카드" in method: res[f"{p}_신용"]+=amt
                    elif any(x in method for x in ["계좌","현금","페이"]): res[f"{p}_현금"]+=amt
                    else: res[f"{p}_기타"]+=amt
                results.append(res)
    except Exception as e:
        st.error(f"⚠️ {fname} 분석 중 오류: {e}")
    return results

# --- [3. 메인 화면] ---
files = st.file_uploader("📂 정산 파일들을 모두 올려주세요 (한꺼번에 드래그)", accept_multiple_files=True)

if files:
    if st.button("🚀 상세 정산 리포트 생성"):
        all_rows = []
        for f in files:
            details = analyze_detailed(f)
            if details: all_rows.extend(details)
        
        if all_rows:
            # 대표님 엑셀 양식으로 변환
            df_final = pd.DataFrame(all_rows)
            df_final['총계'] = df_final.iloc[:, 2:].sum(axis=1)
            
            # 정렬 (월별, 마켓별)
            df_final['월_num'] = df_final['월'].str.extract('(\d+)').astype(int)
            df_final = df_final.sort_values(['월_num', '마켓']).drop('월_num', axis=1)
            
            st.subheader("📊 3분기 마켓별/월별 상세 정산 내역")
            st.table(df_final.style.format(lambda x: f"{int(x):,}" if isinstance(x, (int, float)) else x))
            
            # 합계 행 추가
            sum_row = df_final.sum(numeric_only=True).to_frame().T
            sum_row['마켓'], sum_row['월'] = "전체", "합계"
            st.divider()
            st.subheader("🧾 세무사 제출용 최종 합계")
            st.table(sum_row.style.format(lambda x: f"{int(x):,}" if isinstance(x, (int, float)) else x))

            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False, sheet_name='상세내역')
                sum_row.to_excel(writer, index=False, startrow=len(df_final)+2, sheet_name='상세내역')
            st.download_button("📥 통합 정산 상세 엑셀 다운로드", output.getvalue(), "유기농부_상세정산리포트.xlsx")
        else:
            st.warning("분석된 데이터가 없습니다. 파일명과 형식을 확인해 주세요.")
