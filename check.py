import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import calendar

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V6", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V6 - 완성형)")

# --- [사이드바: 기간 및 API 설정] ---
with st.sidebar:
    st.header("📅 정산 기간 선택")
    target_year = st.selectbox("정산 연도", [2025, 2026], index=0)
    
    col_s, col_e = st.columns(2)
    with col_s: start_m = st.selectbox("시작 월", list(range(1, 13)), index=6) # 7월
    with col_e: end_m = st.selectbox("종료 월", list(range(1, 13)), index=8)   # 9월
    
    last_day = calendar.monthrange(target_year, end_m)[1]
    start_dt = datetime(target_year, start_m, 1)
    end_dt = datetime(target_year, end_m, last_day)
    
    st.success(f"📍 대상 기간: {target_year}년 {start_m}월 ~ {end_m}월")
    
    st.divider()
    st.subheader("🔑 스마트스토어 API")
    n_id = st.text_input("Client ID", key="n_id_v6")
    n_secret = st.text_input("Client Secret", type="password", key="n_secret_v6")
    st.caption("허용 IP: 34.127.0.121")

# --- [네이버 API: 누락 없는 호출 엔진] ---
def fetch_naver_tax_reports(cid, secret, s_dt, e_dt):
    try:
        # 1. 인증 토큰 발급
        ts = str(int(time.time() * 1000))
        pwd = (cid + "_" + ts).encode('utf-8')
        hashed = bcrypt.hashpw(pwd, secret.encode('utf-8'))
        sign = base64.b64encode(hashed).decode('utf-8')

        token_res = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", 
                                  data={"client_id": cid, "timestamp": ts, "grant_type": "client_credentials", "client_secret_sign": sign, "type": "SELF"})
        token = token_res.json().get('access_token')
        if not token: return "🔑 인증 실패 (ID/Secret 확인)"

        # 2. 부가세 내역 호출 (plural URL: tax-reports)
        headers = {"Authorization": f"Bearer {token}"}
        # pageSize=1000 을 넣어 한 번에 모든 데이터를 가져옵니다.
        params = {
            "searchStartDate": s_dt.strftime("%Y-%m-%d"), 
            "searchEndDate": e_dt.strftime("%Y-%m-%d"),
            "pageNumber": 1,
            "pageSize": 1000 
        }
        
        # 공식 경로: /external/v1/pay-settle/settle/tax-reports
        report_url = "https://api.commerce.naver.com/external/v1/pay-settle/settle/tax-reports"
        data_res = requests.get(report_url, headers=headers, params=params)
        
        if data_res.status_code == 200:
            raw_data = data_res.json()
            # 네이버 응답은 주로 'elements' 키 안에 리스트가 들어있습니다.
            items = raw_data.get('elements', []) if isinstance(raw_data, dict) else raw_data
            
            if not items: return "📭 해당 기간에 정산 완료된 매출이 없습니다."
            
            sums = {"카드": 0, "현금": 0, "기타": 0, "면세": 0}
            for i in items:
                sums["카드"] += i.get('cardSalesAmount', 0)
                sums["현금"] += i.get('cashReceiptSalesAmount', 0)
                sums["기타"] += i.get('etcSalesAmount', 0)
                sums["면세"] += i.get('taxFreeSalesAmount', 0)
            return sums
        
        # 404 등이 날 경우 상세 메시지 표시
        return f"📡 네이버 서버 응답 에러: {data_res.status_code}\n(URL: {report_url})"
    except Exception as e:
        return f"❌ 코드 실행 오류: {str(e)}"

# --- [메인 실행 화면] ---
if st.button("🚀 네이버 API 실시간 매출 집계"):
    if not n_id or not n_secret:
        st.warning("Client ID와 Secret을 입력해 주세요.")
    else:
        with st.spinner("네이버 서버와 통신 중... (전수 조사 모드)"):
            res = fetch_naver_tax_reports(n_id, n_secret, start_dt, end_dt)
            if isinstance(res, dict):
                st.success("✅ 네이버 데이터 수집 성공!")
                
                # 결과 테이블
                df = pd.DataFrame([{"마켓": "스마트스토어(API)", **res}])
                st.table(df)
                
                # 요약 대시보드
                st.divider()
                st.subheader("🧾 세무사 제출용 요약")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("신용카드", f"{int(res['카드']):,}원")
                c2.metric("현금영수증", f"{int(res['현금']):,}원")
                c3.metric("기타(포인트 등)", f"{int(res['기타']):,}원")
                c4.metric("면세 합계", f"{int(res['면세']):,}원")
                
                st.info(f"💡 총 합계(과세+면세): {int(res['카드'] + res['현금'] + res['기타'] + res['면세']):,}원")
            else:
                st.error(res)
