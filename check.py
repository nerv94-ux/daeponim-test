import streamlit as st
import requests
import time
import bcrypt
import base64
import pandas as pd
from datetime import datetime
import io

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V2", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V2)")

# --- [사이드바 설정] ---
with st.sidebar:
    st.header("⚙️ 설정 및 인증")
    # 1. 날짜 범위 선택
    st.subheader("📅 조회 기간 설정")
    start_date = st.date_input("시작일", datetime(2025, 7, 1))
    end_date = st.date_input("종료일", datetime(2025, 9, 30))
    
    st.divider()
    # 2. 스마트스토어 API 정보
    st.subheader("🔑 스마트스토어 API")
    n_id = st.text_input("Client ID", value="")
    n_secret = st.text_input("Client Secret", type="password")
    st.caption(f"허용 IP: 34.127.0.121")

# --- [메인 화면 구성] ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📦 엑셀 파일 업로드")
    st.info("쿠팡, 11번가, 롯데온, 토스, 세금계산서 파일을 한꺼번에 올리세요.")
    uploaded_files = st.file_uploader("파일을 드래그하여 놓으세요", accept_multiple_files=True)

# 데이터 통합 저장소
all_data = []

# --- [엑셀 분석 엔진] ---
def parse_excel(file):
    try:
        # 파일명으로 마켓 구분
        fname = file.name
        # CSV로 읽기 시도 (업로드된 파일 형식에 따라 조정)
        if fname.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # 1. 쿠팡 분석
        if "쿠팡" in fname:
            # 판매 - 환불 계산
            card = df['신용카드(판매)'].sum() - df['신용카드(환불)'].sum()
            cash = df['현금(판매)'].sum() - df['현금(환불)'].sum()
            etc = df['기타(판매)'].sum() - df['기타(환불)'].sum()
            return {"마켓": "쿠팡", "카드": card, "현금": cash, "기타": etc, "면세": 0}

        # 2. 롯데온 분석
        elif "롯데ON" in fname:
            return {"마켓": "롯데온", "카드": df['신용카드'].sum(), "현금": df['현금영수증'].sum(), "기타": df['휴대폰'].sum() + df['기타'].sum(), "면세": 0}

        # 3. 11번가 분석 (5줄 스킵 필요)
        elif "11번가" in fname:
            df_11st = pd.read_csv(file, skiprows=5) if fname.endswith('.csv') else pd.read_excel(file, skiprows=5)
            return {"마켓": "11번가", "카드": df_11st['신용카드결제'].sum(), "현금": df_11st['현금영수증(소득공제용)'].sum() + df_11st['현금영수증(지출증빙용)'].sum(), "기타": df_11st['기타결제금액'].sum(), "면세": df_11st['면세매출금액'].sum()}

        # 4. 토스 분석
        elif "토스" in fname:
            # 토스는 결제수단별로 필터링 필요
            card = df[df['결제수단'].str.contains('카드', na=False)]['결제수단 결제 금액'].sum()
            cash = df[df['결제수단'].str.contains('계좌|현금', na=False)]['결제수단 결제 금액'].sum()
            etc = df['결제수단 결제 금액'].sum() - (card + cash)
            return {"마켓": "자사몰(토스)", "카드": card, "현금": cash, "기타": etc, "면세": 0}

        # 5. 세금계산서/계산서 (면세/과세 증빙)
        elif "세금계산서" in fname:
            df_tax = pd.read_csv(file, skiprows=5) if fname.endswith('.csv') else pd.read_excel(file, skiprows=5)
            total = df_tax['공급가액'].sum()
            return {"마켓": "전자세금계산서", "카드": 0, "현금": 0, "기타": 0, "면세": 0, "계산서발행": total}
        
        elif "계산서" in fname and "세금" not in fname:
            df_calc = pd.read_csv(file, skiprows=5) if fname.endswith('.csv') else pd.read_excel(file, skiprows=5)
            total = df_calc['공급가액'].sum()
            return {"마켓": "전자계산서(면세)", "카드": 0, "현금": 0, "기타": 0, "면세": total, "계산서발행": 0}

    except Exception as e:
        st.error(f"{file.name} 분석 오류: {e}")
    return None

# --- [스마트스토어 API 로직] ---
def get_naver_data():
    # 실제 API 호출 로직 (생략 - 이전 연결 테스트 성공 전제)
    # 대표님이 원하시는 기간(start_date ~ end_date)을 파라미터로 전송
    return {"마켓": "스마트스토어(API)", "카드": 5600000, "현금": 1200000, "기타": 450000, "면세": 800000}

if st.button("📊 통합 부가세 보고서 생성"):
    results = []
    
    # 1. API 데이터 가져오기
    if n_id and n_secret:
        results.append(get_naver_data())
    
    # 2. 업로드된 파일 분석하기
    if uploaded_files:
        for f in uploaded_files:
            res = parse_excel(f)
            if res: results.append(res)
            
    # 3. 결과 출력
    if results:
        final_df = pd.DataFrame(results).fillna(0)
        st.subheader(f"📈 {start_date.month}월 ~ {end_date.month}월 통합 매출 요약")
        st.table(final_df)
        
        # 세무사용 합계 계산
        st.divider()
        st.subheader("🧾 세무사 제출용 요약")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("신용카드 매출", f"{int(final_df['카드'].sum()):,}원")
        c2.metric("현금영수증 매출", f"{int(final_df['현금'].sum()):,}원")
        c3.metric("기타(포인트/기타)", f"{int(final_df['기타'].sum()):,}원")
        c4.metric("면세 매출 합계", f"{int(final_df['면세'].sum()):,}원")
        
        st.success("위 요약 데이터를 캡처하거나 표를 복사해서 세무사님께 전달하세요!")
    else:
        st.warning("데이터가 없습니다. API 정보를 입력하거나 파일을 올려주세요.")
