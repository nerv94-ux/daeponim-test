import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import calendar

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V11", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V11 - 에러 수정본)")

# --- [사이드바 설정] ---
with st.sidebar:
    st.header("📅 정산 기간 선택")
    target_year = st.selectbox("정산 연도", [2025, 2026], index=0)
    col_s, col_e = st.columns(2)
    with col_s: start_m = st.selectbox("시작 월", list(range(1, 13)), index=6)
    with col_e: end_m = st.selectbox("종료 월", list(range(1, 13)), index=8)
    
    st.divider()
    st.subheader("🔑 스마트스토어 API")
    n_id = st.text_input("Client ID", key="n_id_v11")
    n_secret = st.text_input("Client Secret", type="password", key="n_secret_v11")
    st.caption("허용 IP: 34.127.0.121")

# --- [네이버 API: 과세/면세 6종 분류 호출] ---
def fetch_naver_vat_v11(cid, secret, start_m, end_m, year):
    try:
        ts = str(int(time.time() * 1000))
        pwd = (cid + "_" + ts).encode('utf-8')
        sign = base64.b64encode(bcrypt.hashpw(pwd, secret.encode('utf-8'))).decode('utf-8')

        token_res = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", 
                                  data={"client_id": cid, "timestamp": ts, "grant_type": "client_credentials", "client_secret_sign": sign, "type": "SELF"})
        token = token_res.json().get('access_token')
        if not token: return "인증 실패"

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        # API 결과 바구니
        total = {
            "과세_카드": 0, "과세_현금": 0, "과세_기타": 0,
            "면세_카드": 0, "면세_현금": 0, "면세_기타": 0
        }
        
        for month in range(start_m, end_m + 1):
            last_day = calendar.monthrange(year, month)[1]
            params = {
                "startDate": f"{year}-{month:02d}-01",
                "endDate": f"{year}-{month:02d}-{last_day:02d}",
                "pageNumber": 1, "pageSize": 1000
            }
            url = "https://api.commerce.naver.com/external/v1/pay-settle/vat/daily"
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code == 200:
                items = res.json().get('elements', [])
                for i in items:
                    # 과세 합산
                    total["과세_카드"] += i.get('creditCardAmount', 0)
                    total["과세_현금"] += i.get('cashInComeDeductionAmount', 0) + i.get('cashOutGoingEvidenceAmount', 0)
                    total["과세_기타"] += i.get('otherAmount', 0)
                    # 면세 합산
                    total["면세_카드"] += i.get('taxExemptionCreditCardAmount', 0)
                    total["면세_현금"] += i.get('taxExemptionCashAmount', 0)
                    total["면세_기타"] += i.get('taxExemptionOtherAmount', 0)
        return total
    except: return None

# --- [엑셀 분석: 과세/면세 6종 분류] ---
def parse_excel_v11(file):
    try:
        # 한국어 인코딩 처리
        df = pd.read_csv(file, header=None, encoding='utf-8-sig') if file.name.endswith('.csv') else pd.read_excel(file, header=None)
        df = df.iloc[3:] # 4행부터 데이터 시작
        return {
            "과세_카드": pd.to_numeric(df.iloc[:,2], errors='coerce').sum(),
            "과세_현금": pd.to_numeric(df.iloc[:,3], errors='coerce').sum(),
            "과세_기타": pd.to_numeric(df.iloc[:,4], errors='coerce').sum(),
            "면세_카드": pd.to_numeric(df.iloc[:,5], errors='coerce').sum(),
            "면세_현금": pd.to_numeric(df.iloc[:,6], errors='coerce').sum(),
            "면세_기타": pd.to_numeric(df.iloc[:,7], errors='coerce').sum(),
        }
    except: return None

# --- [메인 실행부] ---
col_in, col_out = st.columns([1, 1.5])

with col_in:
    st.subheader("📂 엑셀 데이터 업로드")
    files = st.file_uploader("정산 엑셀 파일들을 올려주세요", accept_multiple_files=True)

with col_out:
    if st.button("🚀 세무사 제출용 통합 정산 시작"):
        # 최종 결과 바구니 (이름표 고정)
        final_data = {
            "과세": {"신용카드": 0, "현금영수증": 0, "기타": 0},
            "면세": {"신용카드": 0, "현금영수증": 0, "기타": 0}
        }
        
        # 1. 네이버 API 데이터 합산 (이름표 매칭 로직 추가)
        if n_id and n_secret:
            n_res = fetch_naver_vat_v11(n_id, n_secret, start_m, end_m, target_year)
            if isinstance(n_res, dict):
                # 이름표를 서로 연결해주는 지도 (카드 -> 신용카드)
                typ_map = {"카드": "신용카드", "현금": "현금영수증", "기타": "기타"}
                for k, v in n_res.items():
                    cat, typ = k.split('_') # '과세', '카드' 분리
                    final_data[cat][typ_map[typ]] += v
        
        # 2. 엑셀 데이터 합산
        if files:
            for f in files:
                f_res = parse_excel_v11(f)
                if f_res:
                    final_data["과세"]["신용카드"] += f_res["과세_카드"]
                    final_data["과세"]["현금영수증"] += f_res["과세_현금"]
                    final_data["과세"]["기타"] += f_res["과세_기타"]
                    final_data["면세"]["신용카드"] += f_res["면세_카드"]
                    final_data["면세"]["현금영수증"] += f_res["면세_현금"]
                    final_data["면세"]["기타"] += f_res["면세_기타"]

        # --- [결과 표시] ---
        st.subheader(f"📊 {start_m}월~{end_m}월 통합 매출 현황")
        
        report_df = pd.DataFrame(final_data).T
        report_df['합계'] = report_df.sum(axis=1)
        st.table(report_df.applymap(lambda x: f"{int(x):,}원"))
        
        # --- [세무사 전달용 텍스트] ---
        st.divider()
        st.subheader("📄 세무사 전달용 요약 (복사하세요)")
        summary_text = f"""
[유기농부 {target_year}년 {start_m}~{end_m}월 부가세 자료]

1. 과세 매출 (가공품 등)
- 신용카드: {int(final_data['과세']['신용카드']):,}원
- 현금영수증: {int(final_data['과세']['현금영수증']):,}원
- 기타(포인트/기타): {int(final_data['과세']['기타']):,}원

2. 면세 매출 (농산물 등)
- 신용카드: {int(final_data['면세']['신용카드']):,}원
- 현금영수증: {int(final_data['면세']['현금영수증']):,}원
- 기타(포인트/기타): {int(final_data['면세']['기타']):,}원

총 합계: {int(report_df['합계'].sum()):,}원
        """
        st.code(summary_text, language="text")
