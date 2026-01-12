import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import calendar

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V9", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V9 - 최종 수정형)")

# --- [사이드바 설정] ---
with st.sidebar:
    st.header("📅 정산 기간 선택")
    target_year = st.selectbox("정산 연도", [2025, 2026], index=0)
    col_s, col_e = st.columns(2)
    with col_s: start_m = st.selectbox("시작 월", list(range(1, 13)), index=6) # 7월
    with col_e: end_m = st.selectbox("종료 월", list(range(1, 13)), index=8)   # 9월
    
    st.divider()
    st.subheader("🔑 스마트스토어 API")
    n_id = st.text_input("Client ID", key="n_id_v9")
    n_secret = st.text_input("Client Secret", type="password", key="n_secret_v9")
    st.caption("허용 IP: 34.127.0.121")

# --- [네이버 API: 실전 부가세 데이터 엔진] ---
def fetch_naver_vat_v9(cid, secret, start_m, end_m, year):
    try:
        # 1. 인증 토큰 발급
        ts = str(int(time.time() * 1000))
        pwd = (cid + "_" + ts).encode('utf-8')
        sign = base64.b64encode(bcrypt.hashpw(pwd, secret.encode('utf-8'))).decode('utf-8')

        token_res = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", 
                                  data={"client_id": cid, "timestamp": ts, "grant_type": "client_credentials", "client_secret_sign": sign, "type": "SELF"})
        token = token_res.json().get('access_token')
        if not token: return "🔑 인증 실패: ID/Secret을 확인하세요."

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        all_sums = {"카드": 0, "현금": 0, "기타": 0, "면세": 0}
        
        # 2. 월별로 순회하며 데이터 수집
        for month in range(start_m, end_m + 1):
            last_day = calendar.monthrange(year, month)[1]
            s_str = f"{year}-{month:02d}-01"
            e_str = f"{year}-{month:02d}-{last_day:02d}"
            
            # [필독] 대표님이 찾으신 경로와 파라미터 적용
            url = "https://api.commerce.naver.com/external/v1/pay-settle/vat/daily"
            params = {
                "startDate": s_str,    # searchStartDate가 아님
                "endDate": e_str,      # searchEndDate가 아님
                "pageNumber": 1,       # 필수
                "pageSize": 1000       # 필수
            }
            
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code == 200:
                data = res.json()
                items = data.get('elements', [])
                
                for i in items:
                    # 필드명 매칭 (카드, 현금-소득, 현금-지출, 기타, 면세)
                    all_sums["카드"] += i.get('creditCardAmount', 0)
                    all_sums["현금"] += i.get('cashInComeDeductionAmount', 0) + i.get('cashOutGoingEvidenceAmount', 0)
                    all_sums["기타"] += i.get('otherAmount', 0)
                    all_sums["면세"] += i.get('taxExemptionSalesAmount', 0)
            else:
                return f"📡 {month}월 호출 실패 ({res.status_code}): {res.text}"

        return all_sums

    except Exception as e:
        return f"❌ 오류 발생: {str(e)}"

# --- [메인 실행 화면] ---
if st.button("🚀 네이버 API 실시간 매출 집계 시작"):
    if not n_id or not n_secret:
        st.warning("Client ID와 Secret을 입력해 주세요.")
    else:
        with st.spinner(f"{start_m}월~{end_m}월 정산 데이터를 긁어오는 중..."):
            res = fetch_naver_vat_v9(n_id, n_secret, start_m, end_m, target_year)
            
            if isinstance(res, dict):
                st.success("✅ 네이버 정산 데이터 로드 완료!")
                
                # 결과 테이블
                df = pd.DataFrame([{"구분": f"스마트스토어 ({start_m}~{end_m}월)", **res}])
                st.table(df)
                
                # 요약 대시보드
                st.divider()
                st.subheader("🧾 세무사 제출용 요약")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("신용카드", f"{int(res['카드']):,}원")
                c2.metric("현금영수증", f"{int(res['현금']):,}원")
                c3.metric("기타(포인트 등)", f"{int(res['기타']):,}원")
                c4.metric("면세 합계", f"{int(res['면세']):,}원")
                
                total_sum = sum(res.values())
                st.info(f"💡 총 매출 합계: {total_sum:,}원")
                st.caption("※ 네이버 서버에서 실시간으로 가져온 데이터입니다.")
            else:
                st.error(res)
