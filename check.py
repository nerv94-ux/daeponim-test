import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import calendar

st.set_page_config(page_title="부가세 마스터 V7", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V7 - 자가 치유형)")

# --- [사이드바 설정] ---
with st.sidebar:
    st.header("📅 정산 기간 선택")
    target_year = st.selectbox("정산 연도", [2025, 2026], index=0)
    col_s, col_e = st.columns(2)
    with col_s: start_m = st.selectbox("시작 월", list(range(1, 13)), index=6)
    with col_e: end_m = st.selectbox("종료 월", list(range(1, 13)), index=8)
    
    last_day = calendar.monthrange(target_year, end_m)[1]
    start_dt, end_dt = datetime(target_year, start_m, 1), datetime(target_year, end_m, last_day)
    
    st.divider()
    st.subheader("🔑 스마트스토어 API")
    n_id = st.text_input("Client ID", key="n_id_v7")
    n_secret = st.text_input("Client Secret", type="password", key="n_secret_v7")
    st.caption("권한 체크 필수: API 센터 > API 리스트 > '정산관리' 체크")

# --- [네이버 API: 주소 자동 탐색 엔진] ---
def fetch_naver_tax_full_data(cid, secret, s_dt, e_dt):
    try:
        # 1. 인증 토큰 발급
        ts = str(int(time.time() * 1000))
        pwd = (cid + "_" + ts).encode('utf-8')
        sign = base64.b64encode(bcrypt.hashpw(pwd, secret.encode('utf-8'))).decode('utf-8')

        token_res = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", 
                                  data={"client_id": cid, "timestamp": ts, "grant_type": "client_credentials", "client_secret_sign": sign, "type": "SELF"})
        token = token_res.json().get('access_token')
        if not token: return "🔑 인증 실패: ID/Secret 및 IP를 확인하세요."

        # 2. 404를 피하기 위해 후보 주소들을 순례합니다.
        # 네이버 개편 시기에 따라 주소가 미세하게 다를 수 있습니다.
        endpoints = [
            "https://api.commerce.naver.com/external/v1/pay-settle/settle/tax-reports",
            "https://api.commerce.naver.com/external/v1/settle/tax-reports",
            "https://api.commerce.naver.com/external/v1/pay-settle/settle/tax-report"
        ]
        
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        params = {
            "searchStartDate": s_dt.strftime("%Y-%m-%d"), 
            "searchEndDate": e_dt.strftime("%Y-%m-%d"),
            "pageNumber": 1, "pageSize": 100 # 안전하게 100건씩 호출
        }

        final_sums = {"카드": 0, "현금": 0, "기타": 0, "면세": 0}
        success_flag = False

        for url in endpoints:
            data_res = requests.get(url, headers=headers, params=params)
            if data_res.status_code == 200:
                raw_data = data_res.json()
                items = raw_data.get('elements', []) if isinstance(raw_data, dict) else raw_data
                
                # 데이터가 있다면 합산 시작
                if items:
                    for i in items:
                        final_sums["카드"] += i.get('cardSalesAmount', 0)
                        final_sums["현금"] += i.get('cashReceiptSalesAmount', 0)
                        final_sums["기타"] += i.get('etcSalesAmount', 0)
                        final_sums["면세"] += i.get('taxFreeSalesAmount', 0)
                    success_flag = True
                    break # 성공했으므로 루프 종료
            elif data_res.status_code == 404:
                continue # 다음 주소 시도
            else:
                return f"📡 서버 응답 오류 ({data_res.status_code})"

        if success_flag: return final_sums
        return "📭 해당 기간에 정산 데이터가 없거나, API 리스트에서 '정산관리' 권한이 빠져있습니다."

    except Exception as e:
        return f"❌ 코드 실행 오류: {str(e)}"

# --- [메인 화면] ---
if st.button("🚀 부가세 정산 데이터 긁어오기 (V7)"):
    if not n_id:
        st.warning("Client ID를 입력해 주세요.")
    else:
        with st.spinner("네이버 서버의 금고를 열고 있습니다..."):
            res = fetch_naver_tax_full_data(n_id, n_secret, start_dt, end_dt)
            
            if isinstance(res, dict):
                st.success("✅ 네이버 데이터 수집 성공!")
                # 대시보드 출력
                df = pd.DataFrame([{"마켓": "스마트스토어(API)", **res}])
                st.table(df)
                
                st.divider()
                st.subheader("🧾 세무사 제출용 최종 합계")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("신용카드", f"{int(res['카드']):,}원")
                c2.metric("현금영수증", f"{int(res['현금']):,}원")
                c3.metric("기타(포인트 등)", f"{int(res['기타']):,}원")
                c4.metric("면세 합계", f"{int(res['면세']):,}원")
                
                total = sum(res.values())
                st.info(f"💡 이번 분기 총 매출 합계: {total:,}원")
            else:
                st.error(res)
