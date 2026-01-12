import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import calendar

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V5", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V5 - 최종형)")

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
    n_id = st.text_input("Client ID", key="n_id_v5")
    n_secret = st.text_input("Client Secret", type="password", key="n_secret_v5")
    st.caption("허용 IP: 34.127.0.121")

# --- [네이버 API: 누락 없는 호출 엔진] ---
def get_naver_real_total(cid, secret, s_dt, e_dt):
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

        # 2. 부가세 내역 호출 (V3에서 작동했던 경로로 복구 + 전수조사 옵션 추가)
        headers = {"Authorization": f"Bearer {token}"}
        # pageSize=1000 을 넣어 한 번에 모든 데이터를 긁어옵니다.
        params = {
            "searchStartDate": s_dt.strftime("%Y-%m-%d"), 
            "searchEndDate": e_dt.strftime("%Y-%m-%d"),
            "pageSize": 1000 
        }
        
        # 정산 부가세 신고 내역 표준 경로
        report_url = "https://api.commerce.naver.com/external/v1/settle/tax-report"
        data_res = requests.get(report_url, headers=headers, params=params)
        
        if data_res.status_code == 200:
            raw_data = data_res.json()
            # 데이터가 'elements' 리스트 안에 있는지, 아니면 통째로 리스트인지 판별
            items = raw_data.get('elements', []) if isinstance(raw_data, dict) else raw_data
            
            if not items: return "📭 해당 기간에 정산 완료된 매출이 없습니다."
            
            sums = {"카드": 0, "현금": 0, "기타": 0, "면세": 0}
            for i in items:
                # 결제 수단별 금액 합산 (네이버 API 표준 필드)
                sums["카드"] += i.get('cardSalesAmount', 0)
                sums["현금"] += i.get('cashReceiptSalesAmount', 0)
                sums["기타"] += i.get('etcSalesAmount', 0)
                sums["면세"] += i.get('taxFreeSalesAmount', 0)
            return sums
        
        return f"📡 네이버 서버 응답 에러: {data_res.status_code}\n({data_res.text[:100]})"
    except Exception as e:
        return f"❌ 코드 실행 오류: {str(e)}"

# --- [메인 실행 화면] ---
c_files, c_report = st.columns([1, 1.2])

with c_files:
    st.subheader("📂 타 마켓 엑셀 업로드")
    uploaded_files = st.file_uploader("쿠팡, 11번가 등 파일을 선택하세요 (선택 사항)", accept_multiple_files=True)
    if not uploaded_files:
        st.info("현재 네이버 API 단독 테스트 모드입니다.")

with c_report:
    if st.button("🚀 부가세 통합 정산 시작"):
        final_list = []
        
        # 1. 네이버 API 데이터 가져오기
        if n_id and n_secret:
            with st.spinner("네이버 서버와 통신 중..."):
                naver_res = get_naver_real_total(n_id, n_secret, start_dt, end_dt)
                if isinstance(naver_res, dict):
                    final_list.append({"마켓": "스마트스토어(API)", **naver_res})
                    st.success("✅ 네이버 데이터 수집 성공!")
                else:
                    st.error(naver_res)
        
        # 2. 업로드된 파일이 있다면 처리 (이전 로직 동일)
        # ... (파일 분석 로직 생략 - 필요시 V4의 analyze_files 추가 가능)

        if final_list:
            df = pd.DataFrame(final_list).fillna(0)
            st.subheader("📊 정산 결과 요약")
            st.table(df)
            
            st.divider()
            st.subheader("🧾 세무사 제출용 최종 합계")
            k1, k2, k3, k4 = st.columns(4)
            # 합계 금액 표시
            card_total = int(df['카드'].sum())
            cash_total = int(df['현금'].sum())
            etc_total = int(df['기타'].sum())
            tax_free_total = int(df['면세'].sum())
            
            k1.metric("신용카드", f"{card_total:,}원")
            k2.metric("현금영수증", f"{cash_total:,}원")
            k3.metric("기타(포인트 등)", f"{etc_total:,}원")
            k4.metric("면세 합계", f"{tax_free_total:,}원")
            
            st.info(f"💡 총 합계(과세+면세): {card_total + cash_total + etc_total + tax_free_total:,}원")
        else:
            if not n_id:
                st.warning("Client ID를 입력하거나 파일을 업로드해 주세요.")
