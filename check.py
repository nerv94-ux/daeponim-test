import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import calendar

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V12", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V12 - 면세 정밀 집계)")

# --- [사이드바 설정] ---
with st.sidebar:
    st.header("📅 정산 기간 선택")
    target_year = st.selectbox("정산 연도", [2025, 2026], index=0)
    col_s, col_e = st.columns(2)
    with col_s: start_m = st.selectbox("시작 월", list(range(1, 13)), index=6)
    with col_e: end_m = st.selectbox("종료 월", list(range(1, 13)), index=8)
    
    st.divider()
    st.subheader("🔑 스마트스토어 API")
    n_id = st.text_input("Client ID", key="n_id_v12")
    n_secret = st.text_input("Client Secret", type="password", key="n_secret_v12")
    st.caption("허용 IP: 34.127.0.121")

# --- [유틸리티: 쉼표 섞인 문자열을 숫자로 변환] ---
def clean_num(val):
    if pd.isna(val): return 0
    if isinstance(val, str):
        val = val.replace(',', '').strip()
    try:
        return float(val)
    except:
        return 0

# --- [네이버 API: 면세 통합 처리 로직] ---
def fetch_naver_vat_v12(cid, secret, start_m, end_m, year):
    try:
        ts = str(int(time.time() * 1000))
        pwd = (cid + "_" + ts).encode('utf-8')
        sign = base64.b64encode(bcrypt.hashpw(pwd, secret.encode('utf-8'))).decode('utf-8')

        token_res = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", 
                                  data={"client_id": cid, "timestamp": ts, "grant_type": "client_credentials", "client_secret_sign": sign, "type": "SELF"})
        token = token_res.json().get('access_token')
        if not token: return None

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        total = {
            "과세_신용카드": 0, "과세_현금영수증": 0, "과세_기타": 0,
            "면세_신용카드": 0, "면세_현금영수증": 0, "면세_기타": 0, "면세_합계": 0
        }
        
        for month in range(start_m, end_m + 1):
            last_day = calendar.monthrange(year, month)[1]
            params = {"startDate": f"{year}-{month:02d}-01", "endDate": f"{year}-{month:02d}-{last_day:02d}", "pageNumber": 1, "pageSize": 1000}
            url = "https://api.commerce.naver.com/external/v1/pay-settle/vat/daily"
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code == 200:
                items = res.json().get('elements', [])
                for i in items:
                    # 과세는 상세 분류
                    total["과세_신용카드"] += i.get('creditCardAmount', 0)
                    total["과세_현금영수증"] += i.get('cashInComeDeductionAmount', 0) + i.get('cashOutGoingEvidenceAmount', 0)
                    total["과세_기타"] += i.get('otherAmount', 0)
                    # 면세는 API 특성상 합계로 들어오는 경우가 많음
                    total["면세_합계"] += i.get('taxExemptionSalesAmount', 0)
        return total
    except: return None

# --- [엑셀 분석: 쉼표 제거 및 6종 분류] ---
def parse_excel_v12(file):
    try:
        df = pd.read_csv(file, header=None, encoding='utf-8-sig') if file.name.endswith('.csv') else pd.read_excel(file, header=None)
        df = df.iloc[3:] # 데이터 시작점
        
        # 각 칸의 데이터를 숫자로 깨끗하게 변환
        res = {
            "과세_신용카드": df.iloc[:,2].apply(clean_num).sum(),
            "과세_현금영수증": df.iloc[:,3].apply(clean_num).sum(),
            "과세_기타": df.iloc[:,4].apply(clean_num).sum(),
            "면세_신용카드": df.iloc[:,5].apply(clean_num).sum(),
            "면세_현금영수증": df.iloc[:,6].apply(clean_num).sum(),
            "면세_기타": df.iloc[:,7].apply(clean_num).sum(),
        }
        return res
    except: return None

# --- [메인 실행부] ---
col_in, col_out = st.columns([1, 1.5])

with col_in:
    st.subheader("📂 데이터 업로드")
    files = st.file_uploader("정산 엑셀(CSV) 파일을 올려주세요", accept_multiple_files=True)

with col_out:
    if st.button("🚀 세무사 제출용 통합 정산 시작"):
        final_data = {
            "과세": {"신용카드": 0, "현금영수증": 0, "기타": 0},
            "면세": {"신용카드": 0, "현금영수증": 0, "기타": 0}
        }
        
        # 1. 네이버 API 데이터 합산
        if n_id and n_secret:
            n_res = fetch_naver_vat_v12(n_id, n_secret, start_m, end_m, target_year)
            if isinstance(n_res, dict):
                final_data["과세"]["신용카드"] += n_res["과세_신용카드"]
                final_data["과세"]["현금영수증"] += n_res["과세_현금영수증"]
                final_data["과세"]["기타"] += n_res["과세_기타"]
                # API가 면세 상세를 안 주면 '기타'에 몰아서 합산 (데이터 유실 방지)
                if n_res["면세_합계"] > 0 and (n_res["면세_신용카드"] + n_res["면세_현금영수증"]) == 0:
                    final_data["면세"]["기타"] += n_res["면세_합계"]
                else:
                    final_data["면세"]["신용카드"] += n_res["면세_신용카드"]
                    final_data["면세"]["현금영수증"] += n_res["면세_현금영수증"]
                    final_data["면세"]["기타"] += n_res["면세_기타"]
        
        # 2. 엑셀 데이터 합산
        if files:
            for f in files:
                f_res = parse_excel_v12(f)
                if f_res:
                    final_data["과세"]["신용카드"] += f_res["과세_신용카드"]
                    final_data["과세"]["현금영수증"] += f_res["과세_현금영수증"]
                    final_data["과세"]["기타"] += f_res["과세_기타"]
                    final_data["면세"]["신용카드"] += f_res["면세_신용카드"]
                    final_data["면세"]["현금영수증"] += f_res["면세_현금영수증"]
                    final_data["면세"]["기타"] += f_res["면세_기타"]

        # --- [결과 표시] ---
        st.subheader(f"📊 {start_m}월~{end_m}월 통합 매출 현황")
        
        report_df = pd.DataFrame(final_data).T
        report_df['합계'] = report_df.sum(axis=1)
        st.table(report_df.applymap(lambda x: f"{int(x):,}원"))
        
        st.info("💡 네이버 API는 면세 매출의 카드/현금 상세 분류를 제공하지 않아 면세 합계액을 '기타' 항목에 합산하였습니다. 정확한 분류를 원하시면 스마트스토어에서 내려받은 엑셀 파일을 함께 업로드해 주세요.")
