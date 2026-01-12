import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="부가세 마스터 V22", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V22 - 마켓별 개별 리포트형)")

# --- [유틸리티 함수] ---
def universal_loader(file):
    fname = file.name
    # 1. 엑셀/CSV 자동 감지 및 인코딩 처리
    for enc in ['cp949', 'utf-8-sig', 'utf-8', 'euc-kr']:
        try:
            file.seek(0)
            # 11번가 파일은 상단 5줄을 건너뛰어야 할 수 있음
            if "11번가" in fname:
                df = pd.read_csv(file, encoding=enc, skiprows=5)
            else:
                df = pd.read_csv(file, encoding=enc)
            
            if df.shape[1] > 2: return df
        except: continue
    
    try:
        file.seek(0)
        return pd.read_excel(file)
    except: return None

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

# --- [마켓 분석 엔진] ---
def analyze_market_v22(file):
    fname = file.name
    df = universal_loader(file)
    if df is None: return "해독 불가"
    
    try:
        # 스마트스토어
        if find_col(df, "과세매출") and find_col(df, "면세매출"):
            c_tax, c_free = find_col(df, "과세매출"), find_col(df, "면세매출")
            c_card, c_cash_s, c_cash_j, c_etc = find_col(df, "신용카드"), find_col(df, "현금(소득"), find_col(df, "현금(지출"), find_col(df, "기타")
            res = {"과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
            for _, r in df.iterrows():
                card, cash, etc = to_n(r[c_card]), to_n(r.get(c_cash_s,0))+to_n(r.get(c_cash_j,0)), to_n(r.get(c_etc,0))
                if to_n(r[c_tax]) > 0: res["과세_신용"]+=card; res["과세_현금"]+=cash; res["과세_기타"]+=etc
                if to_n(r[c_free]) > 0: res["면세_신용"]+=card; res["면세_현금"]+=cash; res["면세_기타"]+=etc
            return res
        
        # 쿠팡
        elif find_col(df, "과세유형"):
            c_type = find_col(df, "과세유형")
            res = {"과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
            for _, r in df.iterrows():
                card = to_n(r[find_col(df,"신용카드(판매)")]) - to_n(r.get(find_col(df,"신용카드(환불)"),0))
                cash = to_n(r[find_col(df,"현금(판매)")]) - to_n(r.get(find_col(df,"현금(환불)"),0))
                etc = to_n(r[find_col(df,"기타(판매)")]) - to_n(r.get(find_col(df,"기타(환불)"),0))
                p = "과세" if "TAX" in str(r[c_type]).upper() else "면세"
                res[f"{p}_신용"]+=card; res[f"{p}_현금"]+=cash; res[f"{p}_기타"]+=etc
            return res

        # 11번가 & 롯데ON
        elif "11번가" in fname or "롯데ON" in fname or "롯데온" in fname:
            c_card = find_col(df, "신용카드") or find_col(df, "신용카드결제")
            c_cash = find_col(df, "현금영수증") or find_col(df, "현금영수증(소득")
            c_etc = find_col(df, "기타") or find_col(df, "기타결제")
            c_phone = find_col(df, "휴대폰")
            
            # 롯데온 가공품 파일은 보통 전액 과세
            is_tax = "가공품" in fname or "과세" in fname
            prefix = "과세" if is_tax else "면세"
            
            res = {"과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
            res[f"{prefix}_신용"] = df[c_card].apply(to_n).sum() if c_card else 0
            res[f"{prefix}_현금"] = df[c_cash].apply(to_n).sum() if c_cash else 0
            res[f"{prefix}_기타"] = df[c_etc].apply(to_n).sum() if c_etc else 0
            if c_phone: res[f"{prefix}_기타"] += df[c_phone].apply(to_n).sum()
            return res

        # 토스
        elif "토스" in fname:
            res = {"과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
            for _, r in df.iterrows():
                p = "면세" if any(x in str(r[find_col(df,"상품명")]) for x in ['양배추','당근','감자','무농약']) else "과세"
                amt, m = to_n(r[find_col(df,"결제수단결제금액")]), str(r[find_col(df,"결제수단")])
                if "카드" in m: res[f"{p}_신용"]+=amt
                elif any(x in m for x in ["계좌","현금","페이"]): res[f"{p}_현금"]+=amt
                else: res[f"{p}_기타"]+=amt
            return res
    except Exception as e: return f"오류: {e}"
    return "형식 미지원"

# --- [메인 실행 화면] ---
uploaded_files = st.file_uploader("📂 모든 마켓 정산 파일을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    if st.button("🚀 전체 정산 분석 시작"):
        total_data = {"과세": {"신용카드": 0, "현금영수증": 0, "기타": 0}, "면세": {"신용카드": 0, "현금영수증": 0, "기타": 0}}
        individual_reports = []

        for f in uploaded_files:
            res = analyze_market_v22(f)
            if isinstance(res, dict):
                individual_reports.append({"파일명": f.name, "데이터": res})
                for k, v in res.items():
                    cat, typ = k.split('_')
                    total_data[cat][{"신용":"신용카드","현금":"현금영수증","기타":"기타"}[typ]] += v
            else:
                st.error(f"❌ {f.name}: {res}")

        # 1. 마켓별 개별 리포트 출력
        st.subheader("📋 마켓별 개별 분석 내역")
        for report in individual_reports:
            with st.expander(f"📄 {report['파일명']}"):
                df_ind = pd.DataFrame([
                    {"구분": "과세", "신용카드": report['데이터']['과세_신용'], "현금영수증": report['데이터']['과세_현금'], "기타": report['데이터']['과세_기타']},
                    {"구분": "면세", "신용카드": report['데이터']['면세_신용'], "현금영수증": report['데이터']['면세_현금'], "기타": report['데이터']['면세_기타']}
                ]).set_index("구분")
                st.table(df_ind.applymap(lambda x: f"{int(x):,}원"))

        # 2. 최종 합계 리포트 출력
        st.divider()
        st.subheader("📊 3분기 통합 최종 정산표")
        df_total = pd.DataFrame(total_data).T
        df_total['합계'] = df_total.sum(axis=1)
        st.table(df_total.applymap(lambda x: f"{int(x):,}원"))
        
        # 엑셀 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_total.to_excel(writer, sheet_name='최종합계')
        st.download_button("📥 세무사 제출용 통합 엑셀 다운로드", output.getvalue(), "통합_정산결과.xlsx")
