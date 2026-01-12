import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import calendar
import io

st.set_page_config(page_title="부가세 마스터 V3 (수정본)", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V3)")

# --- [사이드바: 날짜 및 API 설정] ---
with st.sidebar:
    st.header("📅 조회 기간 설정")
    curr_year = 2026 # 현재 연도 기준
    target_year = st.selectbox("연도 선택", [2025, 2026], index=0)
    
    col1, col2 = st.columns(2)
    with col1: start_m = st.selectbox("시작 월", list(range(1, 13)), index=6) # 7월
    with col2: end_m = st.selectbox("종료 월", list(range(1, 13)), index=8)   # 9월
    
    last_day = calendar.monthrange(target_year, end_m)[1]
    start_dt = datetime(target_year, start_m, 1)
    end_dt = datetime(target_year, end_m, last_day)
    
    st.divider()
    st.subheader("🔑 네이버 API 설정")
    n_id = st.text_input("Client ID", key="n_id")
    n_secret = st.text_input("Client Secret", type="password", key="n_secret")
    st.caption("허용 IP: 34.127.0.121")

# --- [엑셀/CSV 분석 엔진] ---
def analyze_files(files):
    results = []
    for f in files:
        fname = f.name
        try:
            # 파일 형식 및 헤더 스킵 처리
            if "11번가" in fname or "계산서" in fname:
                df = pd.read_csv(f, skiprows=5) if fname.endswith('.csv') else pd.read_excel(f, skiprows=5)
            else:
                df = pd.read_csv(f) if fname.endswith('.csv') else pd.read_excel(f)
            
            # 마켓별 로직
            if "쿠팡" in fname:
                # 과세/면세 구분 합산
                card = df['신용카드(판매)'].sum() - df['신용카드(환불)'].sum()
                cash = df['현금(판매)'].sum() - df['현금(환불)'].sum()
                etc = df['기타(판매)'].sum() - df['기타(환불)'].sum()
                # 과세유형이 TAX인 것과 FREE인 것을 분리할 수 있으나 통합 합계 우선
                results.append({"마켓": f"쿠팡({fname[:10]})", "카드": card, "현금": cash, "기타": etc, "면세": 0})
            
            elif "11번가" in fname:
                results.append({"마켓": "11번가", "카드": df['신용카드결제'].sum(), "현금": df['현금영수증(소득공제용)'].sum() + df['현금영수증(지출증빙용)'].sum(), "기타": df['기타결제금액'].sum(), "면세": df['면세매출금액'].sum()})
                
            elif "롯데ON" in fname:
                results.append({"마켓": "롯데온", "카드": df['신용카드'].sum(), "현금": df['현금영수증'].sum(), "기타": df['휴대폰'].sum() + df['기타'].sum(), "면세": 0})
                
            elif "토스" in fname:
                # 토스 건별 정산 자료 분석
                card = df[df['결제수단'].str.contains('카드', na=False, case=False)]['결제수단 결제 금액'].sum()
                cash = df[df['결제수단'].str.contains('토스머니|계좌|현금', na=False, case=False)]['결제수단 결제 금액'].sum()
                etc = df['결제수단 결제 금액'].sum() - (card + cash)
                results.append({"마켓": f"토스({fname[:7]})", "카드": card, "현금": cash, "기타": etc, "면세": 0})

            elif "매출전자세금계산서" in fname:
                results.append({"마켓": "세금계산서발행", "카드": 0, "현금": 0, "기타": 0, "면세": 0, "증빙": df['합계금액'].sum()})

            elif "매출전자계산서" in fname:
                results.append({"마켓": "면세계산서발행", "카드": 0, "현금": 0, "기타": 0, "면세": df['합계금액'].sum(), "증빙": 0})

        except Exception as e:
            st.error(f"{fname} 파일 해석 실패: {e}")
    return results

# --- [네이버 API 엔진] ---
def fetch_naver_data(cid, secret, s_dt, e_dt):
    try:
        ts = str(int(time.time() * 1000))
        pwd = (cid + "_" + ts).encode('utf-8')
        hashed = bcrypt.hashpw(pwd, secret.encode('utf-8'))
        sign = base64.b64encode(hashed).decode('utf-8')

        # 1. 토큰 요청
        res = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", 
                            data={"client_id": cid, "timestamp": ts, "grant_type": "client_credentials", "client_secret_sign": sign, "type": "SELF"})
        token = res.json().get('access_token')
        if not token: return f"인증 실패: {res.text}"

        # 2. 정산 데이터 요청
        headers = {"Authorization": f"Bearer {token}"}
        params = {"searchStartDate": s_dt.strftime("%Y-%m-%d"), "searchEndDate": e_dt.strftime("%Y-%m-%d")}
        data_res = requests.get("https://api.commerce.naver.com/external/v1/settle/tax-report", headers=headers, params=params)
        
        if data_res.status_code == 200:
            items = data_res.json()
            if not items: return "데이터 없음 (해당 기간 매출 0건)"
            # 합산 로직
            sums = {"카드": 0, "현금": 0, "기타": 0, "면세": 0}
            for i in items:
                sums["카드"] += i.get('cardSalesAmount', 0)
                sums["현금"] += i.get('cashReceiptSalesAmount', 0)
                sums["기타"] += i.get('etcSalesAmount', 0)
                sums["면세"] += i.get('taxFreeSalesAmount', 0)
            return sums
        return f"데이터 호출 실패: {data_res.status_code}"
    except Exception as e:
        return f"오류 발생: {e}"

# --- [메인 실행부] ---
c_left, c_right = st.columns([1, 1.2])

with c_left:
    st.subheader("📂 엑셀 파일 업로드")
    files = st.file_uploader("다운로드한 엑셀/CSV 파일들을 모두 선택하세요", accept_multiple_files=True)

with c_right:
    if st.button("🚀 부가세 통합 정산 시작"):
        final_list = []
        
        # 1. 네이버 처리
        if n_id and n_secret:
            with st.spinner("네이버 API 통신 중..."):
                n_data = fetch_naver_data(n_id, n_secret, start_dt, end_dt)
                if isinstance(n_data, dict):
                    final_list.append({"마켓": "스마트스토어(API)", **n_data})
                else:
                    st.warning(f"네이버 API 건너뜀: {n_data}")
        
        # 2. 파일 처리
        if files:
            with st.spinner("파일 분석 중..."):
                file_results = analyze_files(files)
                final_list.extend(file_results)
        
        if final_list:
            df = pd.DataFrame(final_list).fillna(0)
            st.subheader("📊 마켓별 상세 요약")
            st.table(df)
            
            st.divider()
            st.subheader("🧾 세무사 제출용 최종 합계")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("신용카드 매출", f"{int(df['카드'].sum()):,}원")
            k2.metric("현금영수증 매출", f"{int(df['현금'].sum()):,}원")
            k3.metric("기타(포인트 등)", f"{int(df['기타'].sum()):,}원")
            k4.metric("면세 매출 합계", f"{int(df['면세'].sum()):,}원")
            
            if '증빙' in df.columns:
                st.info(f"💡 전자(세금)계산서 별도 발행액 합계: {int(df['증빙'].sum()):,}원")
        else:
            st.error("분석할 데이터가 없습니다. API 정보를 입력하거나 파일을 업로드해 주세요.")
