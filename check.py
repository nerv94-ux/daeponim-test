import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="부가세 마스터 V21", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V21 - 최종 완성형)")

def universal_loader(file):
    try:
        file.seek(0)
        return pd.read_excel(file)
    except: pass
    for enc in ['cp949', 'utf-8-sig', 'utf-8', 'euc-kr']:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding=enc)
            if df.shape[1] > 1: return df
        except: continue
    return None

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

def analyze_market_universal(file):
    fname = file.name
    df = universal_loader(file)
    if df is None: return "파일 해독 불가"
    try:
        if find_col(df, "과세매출") and find_col(df, "면세매출"): # 스마트스토어형
            c_tax, c_free = find_col(df, "과세매출"), find_col(df, "면세매출")
            c_card, c_cash_s, c_cash_j, c_etc = find_col(df, "신용카드"), find_col(df, "현금(소득"), find_col(df, "현금(지출"), find_col(df, "기타")
            res = {"과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
            for _, r in df.iterrows():
                card, cash, etc = to_n(r[c_card]), to_n(r.get(c_cash_s,0))+to_n(r.get(c_cash_j,0)), to_n(r.get(c_etc,0))
                if to_n(r[c_tax]) > 0: res["과세_신용"]+=card; res["과세_현금"]+=cash; res["과세_기타"]+=etc
                if to_n(r[c_free]) > 0: res["면세_신용"]+=card; res["면세_현금"]+=cash; res["면세_기타"]+=etc
            return res
        elif find_col(df, "과세유형"): # 쿠팡형
            c_type = find_col(df, "과세유형")
            res = {"과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
            for _, r in df.iterrows():
                card = to_n(r[find_col(df,"신용카드(판매)")]) - to_n(r.get(find_col(df,"신용카드(환불)"),0))
                cash = to_n(r[find_col(df,"현금(판매)")]) - to_n(r.get(find_col(df,"현금(환불)"),0))
                etc = to_n(r[find_col(df,"기타(판매)")]) - to_n(r.get(find_col(df,"기타(환불)"),0))
                p = "과세" if "TAX" in str(r[c_type]).upper() else "면세"
                res[f"{p}_신용"]+=card; res[f"{p}_현금"]+=cash; res[f"{p}_기타"]+=etc
            return res
        elif "토스" in fname: # 토스형
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

uploaded_files = st.file_uploader("📂 정산 파일을 모두 올려주세요", accept_multiple_files=True)
if uploaded_files and st.button("🚀 정산 시작"):
    final_data = {"과세": {"신용카드": 0, "현금영수증": 0, "기타": 0}, "면세": {"신용카드": 0, "현금영수증": 0, "기타": 0}}
    logs = []
    for f in uploaded_files:
        res = analyze_market_universal(f)
        if isinstance(res, dict):
            logs.append({"파일명": f.name, "상태": "✅ 성공", "금액": f"{int(sum(res.values())):,}원"})
            for k, v in res.items():
                cat, typ = k.split('_')
                final_data[cat][{"신용":"신용카드","현금":"현금영수증","기타":"기타"}[typ]] += v
        else: logs.append({"파일명": f.name, "상태": f"❌ {res}", "금액": "0원"})
    st.table(pd.DataFrame(logs))
    st.divider()
    df_f = pd.DataFrame(final_data).T
    df_f['합계'] = df_f.sum(axis=1)
    st.table(df_f.applymap(lambda x: f"{int(x):,}원"))
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_f.to_excel(writer, sheet_name='부가세정산')
    st.download_button("📥 세무사 제출용 통합 엑셀 다운로드", output.getvalue(), "통합_정산결과.xlsx")
