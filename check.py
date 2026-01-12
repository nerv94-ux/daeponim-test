import streamlit as st
import requests
import time
import hmac
import hashlib
import bcrypt
import base64
from datetime import datetime

st.set_page_config(page_title="API 연결 테스트", layout="centered")
st.title("🛡️ API 연결 상태 긴급 점검")

# 탭으로 네이버/쿠팡 분리
tab1, tab2 = st.tabs(["네이버 스마트스토어", "쿠팡 (Coupang)"])

# --- [네이버 테스트 로직] ---
with tab1:
    st.subheader("네이버 커머스 API 테스트")
    n_client_id = st.text_input("애플리케이션 ID (Client ID)")
    n_client_secret = st.text_input("애플리케이션 시크릿 (Client Secret)", type="password")

    if st.button("네이버 연결 시도"):
        timestamp = str(int(time.time() * 1000))
        # 네이버 특유의 보안 방식 (bcrypt 해싱)
        password = (n_client_id + "_" + timestamp).encode('utf-8')
        hashed = bcrypt.hashpw(password, n_client_secret.encode('utf-8'))
        client_secret_sign = base64.b64encode(hashed).decode('utf-8')

        url = "https://api.commerce.naver.com/external/v1/oauth2/token"
        data = {
            "client_id": n_client_id,
            "timestamp": timestamp,
            "grant_type": "client_credentials",
            "client_secret_sign": client_secret_sign,
            "type": "SELF"
        }
        
        res = requests.post(url, data=data)
        if res.status_code == 200:
            st.success("✅ 네이버 연결 성공! (토글과 상관없이 단독 작동 가능)")
        else:
            st.error(f"❌ 실패: {res.json().get('message', '정보를 확인하세요')}")

# --- [쿠팡 테스트 로직] ---
with tab2:
    st.subheader("쿠팡 마켓플레이스 API 테스트")
    c_vendor_id = st.text_input("업체코드 (Vendor ID - 예: A00123456)")
    c_access_key = st.text_input("Access Key")
    c_secret_key = st.text_input("Secret Key", type="password")

    if st.button("쿠팡 연결 시도"):
        # 쿠팡 API 호출을 위한 서명(Signature) 생성
        import os
        os.environ['TZ'] = 'GMT'
        dt = datetime.utcnow().strftime('%y%m%d' + 'T' + '%H%M%S' + 'Z')
        path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
        message = dt + "GET" + path
        
        signature = hmac.new(c_secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
        authorization = f"CEA algorithm=HmacSHA256, access-key={c_access_key}, signed-date={dt}, signature={signature}"
        
        url = f"https://api-gateway.coupang.com{path}"
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": authorization,
            "X-Requested-By": c_vendor_id
        }
        
        res = requests.get(url, headers=headers, params={"maxPerPage": 1})
        if res.status_code == 200:
            st.success("✅ 쿠팡 연결 성공! (자체개발/IP 등록이 올바르게 되었습니다)")
        else:
            st.error(f"❌ 실패 (코드 {res.status_code}): 토글 IP와 대표님 IP가 모두 등록되었는지 확인하세요.")