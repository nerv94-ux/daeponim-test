import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import calendar

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V3", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V3)")

# --- [사이드바: 날짜를 숫자로 선택] ---
with st.sidebar:
    st.header("📅 조회 기간 설정")
    # 달력 대신 숫자로 선택하게 변경
    curr_year = datetime.now().year
    target_year = st.selectbox("연도 선택", [curr_year, curr_year-1], index=0)
    
    col_start, col_end = st.columns(2)
    with col_start:
        start_m = st.selectbox("시작 월", list(range(1, 13)), index=6) # 기본 7월
    with col_end:
        end_m = st.selectbox("종료 월", list(range(1, 13)), index=8)   # 기본 9월
    
    # 내부적으로 사용할 datetime 변환
    last_day = calendar.monthrange(target_year, end_m)[1]
    start_date = datetime(target_year, start_m, 1)
    end_date = datetime(target_year, end_m, last_day)
    
    st.success(f"선택 기간: {target_year}년 {start_m}월 ~ {end_m}월")
    
    st.divider()
    st.subheader("🔑 네이버 API 설정")
    n_id = st.text_input("Client ID")
    n_secret = st.text_input("Client Secret", type="password")
    st.caption("허용 IP: 34.127.0.121")

# --- [1. 네이버 API 실전 호출 함수] ---
def get_naver_api_data(c_id, c_secret, s_date, e_date):
    try:
        # 토큰 발급 (보안 인증)
        timestamp = str(int(time.time() * 1000))
        password = (c_id + "_" + timestamp).encode('utf-8')
        hashed = bcrypt.hashpw(password, c_secret.encode('utf-8'))
        client_secret_sign = base64.b64encode(hashed).decode('utf-8')

        token_url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        token_res = requests.post(token_url, data={
            "client_id": c_id, "timestamp": timestamp,
            "grant_type": "client_credentials", "client_secret_sign": client_secret_sign, "type": "SELF"
        })
        token = token_res.json().get('access_token')
        if not token: return None

        # 정산 내역 API 호출
        report_url = "https://api.commerce.naver.com/external/v1/settle/tax-report"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"searchStartDate": s_date.strftime("%Y-%m-%d"), "searchEndDate": e_date.strftime("%Y-%m-%d")}
        
        res = requests.get(report_url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            # 네이버 실제 응답에서 각 항목별 합산
            results = {"카드": 0, "현금": 0, "기타": 0, "면세": 0}
            for item in data:
                results["카드"] += item.get('cardSalesAmount', 0)
                results["현금"] += item.get('cashReceiptSalesAmount', 0)
                results["기타"] += item.get('etcSalesAmount', 0)
                results["면세"] += item.get('taxFreeSalesAmount', 0)
            return results
    except:
        return None
    return None

# --- [2. 엑셀 분석 엔진 (대표님 파일 맞춤형)] ---
def parse_excel_file(file):
    fname = file.name
    try:
        # 11번가 & (세금)계산서: 5줄 스킵 필요
        if "11번가" in fname or "계산서" in fname:
            df = pd.read_csv(file, skiprows=5) if fname.endswith('.csv') else pd.read_excel(file, skiprows=5)
        else:
            df = pd.read_csv(file) if fname.endswith('.csv') else pd.read_excel(file)

        if "쿠팡" in fname:
            # 판매액 - 환불액 합산
            card = df['신용카드(판매)'].sum() - df['신용카드(환불)'].sum()
            cash = df['현금(판매)'].sum() - df['현금(환불)'].sum()
            etc = df['기타(판매)'].sum() - df['기타(환불)'].sum()
            return {"마켓": "쿠팡", "카드": card, "현금": cash, "기타": etc, "면세": 0}
        
        elif "11번가" in fname:
            return {"마켓": "11번가", "카드": df['신용카드결제'].sum(), "현금": df['현금영수증(소득공제용)'].sum() + df['현금영수증(지출증빙용)'].sum(), "기타": df['기타결제금액'].sum(), "면세": df['면세매출금액'].sum()}
            
        elif "롯데ON" in fname:
            return {"마켓": "롯데온", "카드": df['신용카드'].sum(), "현금": df['현금영수증'].sum(), "기타": df['휴대폰'].sum() + df['기타'].sum(), "면세": 0}
            
        elif "토스" in fname:
            card = df[df['결제수단'].str.contains('카드', na=False)]['결제수단 결제 금액'].sum()
            cash = df[df['결제수단'].str.contains('계좌|현금', na=False)]['결제수단 결제 금액'].sum()
            etc = df['결제수단 결제 금액'].sum() - (card + cash)
            return {"마켓": "자사몰(토스)", "카드": card, "현금": cash, "기타": etc, "면세": 0}

        elif "매출전자세금계산서" in fname:
            return {"마켓": "세금계산서발행", "카드": 0, "현금": 0, "기타": 0, "면세": 0, "증빙": df['합계금액'].sum()}

        elif "매출전자계산서" in fname:
            return {"마켓": "면세계산서발행", "카드": 0, "현금": 0, "기타": 0, "면세": df['합계금액'].sum(), "증빙": 0}

    except Exception as e:
        st.error(f"{fname} 분석 중 오류: {e}")
    return None

# --- [메인 레이아웃] ---
col_file, col_report = st.columns([1, 1.2])

with col_file:
    st.subheader("📁 엑셀 파일 업로드")
    uploaded_files = st.file_uploader("쿠팡, 11번가 등 파일을 모두 선택하세요", accept_multiple_files=True)

with col_report:
    if st.button("🚀 부가세 통합 정산 시작"):
        all_results = []
        
        # 1. 네이버 API 호출
        if n_id and n_secret:
            with st.spinner("네이버 데이터를 실시간으로 가져오는 중..."):
                naver_res = get_naver_api_data(n_id, n_secret, start_date, end_date)
                if naver_res:
                    all_results.append({"마켓": "스마트스토어(API)", **naver_res})
                else:
                    st.error("네이버 API 연결 실패! 정보를 확인하세요.")
        
        # 2. 엑셀 파일 분석
        if uploaded_files:
            for f in uploaded_files:
                res = parse_excel_file(f)
                if res: all_results.append(res)
        
        if all_results:
            df_final = pd.DataFrame(all_results).fillna(0)
            st.subheader("📊 마켓별 매출 요약")
            st.table(df_final)
            
            st.divider()
            st.subheader("🧾 세무사 제출용 최종 합계")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("신용카드", f"{int(df_final['카드'].sum()):,}원")
            c2.metric("현금영수증", f"{int(df_final['현금'].sum()):,}원")
            c3.metric("기타 매출", f"{int(df_final['기타'].sum()):,}원")
            c4.metric("면세 합계", f"{int(df_final['면세'].sum()):,}원")
            
            if '증빙' in df_final.columns:
                st.info(f"💡 세금계산서 발행액(별도): {int(df_final['증빙'].sum()):,}원")
        else:
            st.warning("분석할 데이터가 없습니다.")
