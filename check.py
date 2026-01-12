import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import calendar
import io

# 페이지 설정 및 제목
st.set_page_config(page_title="부가세 마스터 V4", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V4 - 실전 완성형)")

# --- [사이드바: 숫자 기반 날짜 선택] ---
with st.sidebar:
    st.header("📅 정산 기간 선택")
    target_year = st.selectbox("정산 연도", [2025, 2026], index=0)
    
    col_s, col_e = st.columns(2)
    with col_s: start_m = st.selectbox("시작 월", list(range(1, 13)), index=6) # 7월
    with col_e: end_m = st.selectbox("종료 월", list(range(1, 13)), index=8)   # 9월
    
    # 실제 날짜 계산
    last_day = calendar.monthrange(target_year, end_m)[1]
    start_dt = datetime(target_year, start_m, 1)
    end_dt = datetime(target_year, end_m, last_day)
    
    st.info(f"📍 대상 기간: {target_year}년 {start_m}월 ~ {end_m}월")
    
    st.divider()
    st.subheader("🔑 스마트스토어 API")
    n_id = st.text_input("Client ID", key="n_id_v4")
    n_secret = st.text_input("Client Secret", type="password", key="n_secret_v4")
    st.caption("허용 IP: 34.127.0.121")

# --- [유틸리티: 한글 CSV/엑셀 읽기] ---
def smart_read(file):
    if file.name.endswith('.csv'):
        # 한국어 엑셀은 대부분 CP949 또는 EUC-KR입니다.
        for enc in ['utf-8-sig', 'cp949', 'utf-8', 'euc-kr']:
            try:
                file.seek(0)
                return pd.read_csv(file, encoding=enc)
            except: continue
    else:
        return pd.read_excel(file)
    return None

# --- [네이버 API: 최신 경로 적용] ---
def get_naver_tax_report(cid, secret, s_dt, e_dt):
    try:
        # 1. 인증 토큰 발급
        ts = str(int(time.time() * 1000))
        pwd = (cid + "_" + ts).encode('utf-8')
        hashed = bcrypt.hashpw(pwd, secret.encode('utf-8'))
        sign = base64.b64encode(hashed).decode('utf-8')

        token_res = requests.post("https://api.commerce.naver.com/external/v1/oauth2/token", 
                                  data={"client_id": cid, "timestamp": ts, "grant_type": "client_credentials", "client_secret_sign": sign, "type": "SELF"})
        token = token_res.json().get('access_token')
        if not token: return "인증 실패"

        # 2. 부가세 내역 호출 (최신 pay-settle 경로 적용)
        headers = {"Authorization": f"Bearer {token}"}
        params = {"searchStartDate": s_dt.strftime("%Y-%m-%d"), "searchEndDate": e_dt.strftime("%Y-%m-%d")}
        # 404 방지를 위해 가장 표준적인 정산 경로 사용
        report_url = "https://api.commerce.naver.com/external/v1/pay-settle/settle/tax-report"
        data_res = requests.get(report_url, headers=headers, params=params)
        
        if data_res.status_code == 200:
            items = data_res.json()
            if not items: return "데이터 없음"
            sums = {"카드": 0, "현금": 0, "기타": 0, "면세": 0}
            for i in items:
                sums["카드"] += i.get('cardSalesAmount', 0)
                sums["현금"] += i.get('cashReceiptSalesAmount', 0)
                sums["기타"] += i.get('etcSalesAmount', 0)
                sums["면세"] += i.get('taxFreeSalesAmount', 0)
            return sums
        return f"통신 오류 ({data_res.status_code})"
    except Exception as e:
        return f"에러: {str(e)}"

# --- [메인 화면] ---
c_left, c_right = st.columns([1, 1.2])

with c_left:
    st.subheader("📂 엑셀 파일 업로드 (나머지 마켓)")
    st.write("쿠팡, 11번가, 롯데온, 토스, 계산서 파일들을 한꺼번에 올리세요.")
    files = st.file_uploader("파일 드래그 & 드롭", accept_multiple_files=True)

with c_right:
    if st.button("🚀 전체 데이터 분석 시작"):
        final_results = []
        
        # 1. 네이버 처리
        if n_id and n_secret:
            with st.spinner("네이버 API 연결 중..."):
                naver_data = get_naver_tax_report(n_id, n_secret, start_dt, end_dt)
                if isinstance(naver_data, dict):
                    final_results.append({"마켓": "스마트스토어(API)", **naver_data})
                else:
                    st.warning(f"네이버 API 결과: {naver_data}")
        
        # 2. 업로드 파일 처리
        if files:
            with st.spinner("파일 10개 분석 중..."):
                for f in files:
                    fname = f.name
                    df = smart_read(f)
                    if df is None: continue
                    
                    # 마켓 판별 로직 (보내주신 파일명 기준)
                    if "쿠팡" in fname:
                        # 쿠팡 파일은 판매-환불 합산
                        results = {"마켓": f"쿠팡({fname[:10]})", "카드": df['신용카드(판매)'].sum() - df['신용카드(환불)'].sum(), 
                                   "현금": df['현금(판매)'].sum() - df['현금(환불)'].sum(), "기타": df['기타(판매)'].sum() - df['기타(환불)'].sum(), "면세": 0}
                        final_results.append(results)
                    elif "11번가" in fname:
                        df_11 = smart_read(f) # 11번가는 헤더가 아래에 있으므로 다시 읽기
                        df_11 = df_11.iloc[4:] # 5번째 줄부터 데이터
                        final_results.append({"마켓": "11번가", "카드": pd.to_numeric(df_11.iloc[:,15], errors='coerce').sum(), 
                                              "현금": pd.to_numeric(df_11.iloc[:,16], errors='coerce').sum() + pd.to_numeric(df_11.iloc[:,17], errors='coerce').sum(),
                                              "기타": pd.to_numeric(df_11.iloc[:,19], errors='coerce').sum(), "면세": pd.to_numeric(df_11.iloc[:,13], errors='coerce').sum()})
                    elif "롯데ON" in fname:
                        final_results.append({"마켓": "롯데온", "카드": df['신용카드'].sum(), "현금": df['현금영수증'].sum(), "기타": df['휴대폰'].sum() + df['기타'].sum(), "면세": 0})
                    elif "토스" in fname:
                        card = df[df['결제수단'].str.contains('카드', na=False)]['결제수단 결제 금액'].sum()
                        cash = df[df['결제수단'].str.contains('토스머니|계좌|현금', na=False)]['결제수단 결제 금액'].sum()
                        final_results.append({"마켓": f"토스({fname[:7]})", "카드": card, "현금": cash, "기타": df['결제수단 결제 금액'].sum() - (card+cash), "면세": 0})
                    elif "세금계산서" in fname: # 과세 증빙
                        df_s = df.iloc[4:]
                        final_results.append({"마켓": "세금계산서발행분", "카드": 0, "현금": 0, "기타": 0, "면세": 0, "증빙": pd.to_numeric(df_s.iloc[:,14], errors='coerce').sum()})
                    elif "계산서" in fname: # 면세 증빙
                        df_g = df.iloc[4:]
                        final_results.append({"마켓": "계산서발행분(면세)", "카드": 0, "현금": 0, "기타": 0, "면세": pd.to_numeric(df_g.iloc[:,14], errors='coerce').sum()})

        if final_results:
            df_final = pd.DataFrame(final_results).fillna(0)
            st.subheader("📊 마켓별 상세 리포트")
            st.table(df_final)
            
            st.divider()
            st.subheader("🧾 세무사 제출용 최종 합계")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("신용카드 매출", f"{int(df_final['카드'].sum()):,}원")
            k2.metric("현금영수증 매출", f"{int(df_final['현금'].sum()):,}원")
            k3.metric("기타(포인트 등)", f"{int(df_final['기타'].sum()):,}원")
            k4.metric("면세 매출 합계", f"{int(df_final['면세'].sum()):,}원")
            
            if '증빙' in df_final.columns:
                st.info(f"💡 전자(세금)계산서 별도 발행액 합계: {int(df_final['증빙'].sum()):,}원")
        else:
            st.error("분석할 수 있는 데이터가 없습니다. 파일을 먼저 업로드해 주세요.")
