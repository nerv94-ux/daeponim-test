import streamlit as st
import pandas as pd
import io
import re

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V24", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V24 - 상세 보고서형)")

# --- [1. 유틸리티 함수: 지능형 로더] ---
def to_n(val):
    if pd.isna(val): return 0
    clean = re.sub(r'[^\d.-]', '', str(val))
    try: return float(clean) if clean else 0
    except: return 0

def find_col(df, keyword):
    keyword = keyword.replace(" ", "").lower()
    for col in df.columns:
        if keyword in str(col).replace(" ", "").lower(): return col
    return None

def smart_loader(file):
    fname = file.name
    # 11번가는 무조건 5줄 스킵 시도
    if "11번가" in fname:
        for enc in ['utf-8-sig', 'cp949', 'utf-8']:
            try:
                file.seek(0)
                df = pd.read_csv(file, encoding=enc, skiprows=5)
                if '정산확정처리일' in df.columns or find_col(df, "신용카드"): return df
            except: continue
    
    # 일반 CSV/엑셀 시도
    for enc in ['utf-8-sig', 'cp949', 'utf-8', 'euc-kr']:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding=enc)
            if df.shape[1] > 2: return df
        except: continue
    try:
        file.seek(0)
        return pd.read_excel(file)
    except: return None

# --- [2. 데이터 가공 엔진] ---
def extract_month(df, date_col):
    if not date_col: return "불명"
    first_val = str(df[date_col].iloc[0])
    if len(first_val) == 6 and first_val.isdigit(): # 202507 형태
        return str(int(first_val[4:6])) + "월"
    try:
        return str(pd.to_datetime(first_val).month) + "월"
    except:
        return "불명"

def process_file_detailed(file):
    fname = file.name
    df = smart_loader(file)
    if df is None: return None
    
    rows = []
    # 마켓 이름 결정
    m_name = "스마트스토어" if "스마트스토어" in fname else \
             "쿠팡" if "쿠팡" in fname else \
             "토스" if "토스" in fname else \
             "롯데ON" if "롯데" in fname else \
             "11번가" if "11번가" in fname else \
             "세금계산서" if "세금계산서" in fname else "기타"

    try:
        # 공통 컬럼 찾기
        c_tax_amt = find_col(df, "과세매출")
        c_free_amt = find_col(df, "면세매출")
        c_date = find_col(df, "기준일") or find_col(df, "매출인식일") or find_col(df, "정산확정") or find_col(df, "매출월") or find_col(df, "결제일시")

        # 월별 그룹화 (단순화: 파일당 하나의 월로 가정하거나 날짜별 처리)
        df['temp_month'] = df[c_date].apply(lambda x: str(int(str(x)[4:6]))+"월" if (len(str(x))==6 and str(x).isdigit()) else str(pd.to_datetime(x).month)+"월" if pd.notna(x) else "불명")
        
        for m, m_df in df.groupby('temp_month'):
            res = {"마켓": m_name, "월": m, "과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
            
            # 마켓별 로직 분기
            if m_name == "스마트스토어":
                c_card, c_cash_s, c_cash_j, c_etc = find_col(df, "신용카드"), find_col(df, "현금(소득"), find_col(df, "현금(지출"), find_col(df, "기타")
                for _, r in m_df.iterrows():
                    is_tax = to_n(r[c_tax_amt]) > 0
                    is_free = to_n(r[c_free_amt]) > 0
                    card, cash, etc = to_n(r[c_card]), to_n(r.get(c_cash_s,0))+to_n(r.get(c_cash_j,0)), to_n(r.get(c_etc,0))
                    if is_tax: res["과세_신용"]+=card; res["과세_현금"]+=cash; res["과세_기타"]+=etc
                    if is_free: res["면세_신용"]+=card; res["면세_현금"]+=cash; res["면세_기타"]+=etc

            elif m_name == "쿠팡":
                c_type = find_col(df, "과세유형")
                for _, r in m_df.iterrows():
                    card = to_n(r[find_col(df,"신용카드(판매)")]) - to_n(r.get(find_col(df,"신용카드(환불)"),0))
                    cash = to_n(r[find_col(df,"현금(판매)")]) - to_n(r.get(find_col(df,"현금(환불)"),0))
                    etc = to_n(r[find_col(df,"기타(판매)")]) - to_n(r.get(find_col(df,"기타(환불)"),0))
                    p = "과세" if "TAX" in str(r[c_type]).upper() else "면세"
                    res[f"{p}_신용"]+=card; res[f"{p}_현금"]+=cash; res[f"{p}_기타"]+=etc

            elif m_name == "토스":
                for _, r in m_df.iterrows():
                    p = "면세" if any(x in str(r[find_col(df,"상품명")]) for x in ['양배추','당근','감자','무농약']) else "과세"
                    amt, meth = to_n(r[find_col(df,"결제수단결제금액")]), str(r[find_col(df,"결제수단")])
                    if "카드" in meth: res[f"{p}_신용"]+=amt
                    elif any(x in meth for x in ["계좌","현금","페이"]): res[f"{p}_현금"]+=amt
                    else: res[f"{p}_기타"]+=amt

            elif m_name in ["11번가", "롯데ON"]:
                c_card = find_col(df, "신용카드") or find_col(df, "신용카드결제")
                c_cash = find_col(df, "현금영수증") or find_col(df, "현금영수증(소득")
                c_etc = find_col(df, "기타") or find_col(df, "기타결제")
                c_phone = find_col(df, "휴대폰")
                p = "과세" if ("가공품" in fname or to_n(m_df[c_tax_amt].sum() if c_tax_amt else 1) > 0) else "면세"
                res[f"{p}_신용"] = m_df[c_card].apply(to_n).sum() if c_card else 0
                res[f"{p}_현금"] = m_df[c_cash].apply(to_n).sum() if c_cash else 0
                res[f"{p}_기타"] = m_df[c_etc].apply(to_n).sum() if c_etc else 0
                if c_phone: res[f"{p}_기타"] += m_df[c_phone].apply(to_n).sum()
            rows.append(res)
    except Exception as e:
        st.error(f"⚠️ {fname} 처리 실패: {e}")
    return rows

# --- [3. 메인 실행 부] ---
uploaded = st.file_uploader("📂 정산 파일들을 모두 드래그하세요", accept_multiple_files=True)
if uploaded:
    if st.button("🚀 상세 정산표 생성 (엑셀 복제 모드)"):
        all_res = []
        for f in uploaded:
            data = process_file_detailed(f)
            if data: all_res.extend(data)
        
        if all_res:
            df = pd.DataFrame(all_res)
            # 수치형 데이터 정리
            num_cols = ["과세_신용", "과세_현금", "과세_기타", "면세_신용", "면세_현금", "면세_기타"]
            df[num_cols] = df[num_cols].fillna(0).astype(int)
            df['총계'] = df[num_cols].sum(axis=1)
            
            # 정렬
            df['월_순서'] = df['월'].str.extract('(\d+)').astype(int)
            df = df.sort_values(['월_순서', '마켓']).drop('월_순서', axis=1)
            
            st.subheader("📊 마켓별/월별 상세 정산 내역")
            st.table(df.style.format({c: "{:,}원" for c in num_cols + ['총계']}))
            
            # 최종 합계 행
            st.divider()
            total_sum = df[num_cols + ['총계']].sum().to_frame().T
            total_sum.insert(0, "마켓", "★ 전체 합계")
            total_sum.insert(1, "월", "-")
            st.subheader("🧾 세무사 제출용 최종 합계")
            st.table(total_sum.style.format({c: "{:,}원" for c in num_cols + ['총계']}))
            
            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='정산상세')
                total_sum.to_excel(writer, index=False, startrow=len(df)+2, sheet_name='정산상세')
            st.download_button("📥 통합 정산 엑셀 다운로드", output.getvalue(), "유기농부_통합정산리포트.xlsx")
