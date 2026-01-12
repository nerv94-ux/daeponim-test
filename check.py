import streamlit as st
import requests
import time
import hmac
import hashlib
import bcrypt
import base64
from datetime import datetime

# 페이지 설정
st.set_page_config(page_title="API 연결 마스터", layout="wide")

st.title("🛡️ 스마트스토어 & 쿠팡 API 통합 점검")

# --- [중요] IP 확인 섹션 ---
st.error("⚠️ 네이버/쿠팡 API 센터에 등록해야 할 주소")
try:
    # 현재 프로그램이 돌아가고 있는 서버의 진짜 IP를 가져옵니다.
    current_ip = requests.get("https://api.ipify.org").text
    st.code(current_ip)
    st.caption(f"위의 숫자 주소를 복사해서 각 쇼핑몰 API 설정의 '호출 IP' 또는 '허용 IP'에 추가하세요.")
except:
    st.write("IP 주소를 불러오는 중입니다...")

st.divider()

# 탭 구성
tab1, tab2 = st.tabs(["네이버 스마트스토어", "쿠팡 (Coupang)"])

# --- [1] 네이버 테스트 로직 ---
with tab1:
    st.subheader("네이버 커머스 API 설정")
    n_id = st.text_input("Application ID (Client ID)")
    n_secret = st.text_input("Application Secret (Client Secret)", type="password")

    if st.button("네이버 연결 확인"):
        if not n_id or not n_secret:
            st.warning("ID와 Secret을 입력해주세요.")
        else:
            timestamp = str(int(time.time() * 1000))
            # 네이버 보안 서명 생성 (bcrypt)
            password = (n_id + "_" + timestamp).encode('utf-8')
            hashed = bcrypt.hashpw(password, n_secret.encode('utf-8'))
            client_secret_sign = base64.b64encode(hashed).decode('utf-8')

            url = "https://api.commerce.naver.com/external/v1/oauth2/token"
            data = {
                "client_id": n_id,
                "timestamp": timestamp,
                "grant_type": "client_credentials",
                "client_secret_sign": client_secret_sign,
                "type": "SELF"
            }
            
            res = requests.post(url, data=data)
            if res.status_code == 200:
                st.success("✅ 네이버 연결 성공! 이제 매출 데이터를 가져올 수 있습니다.")
            else:
                st.error(f"❌ 실패 사유: {res.json().get('message', '알 수 없는 오류')}")
                st.info("방금 위에서 확인한 IP 주소가 네이버 API 센터에 등록되었는지 꼭 확인하세요.")

# --- [2] 쿠팡 테스트 로직 ---
with tab2:
    st.subheader("쿠팡 마켓플레이스 API 설정")
    c_vendor_id = st.text_input("업체코드 (Vendor ID - 예: A00123456)")
    c_access_key = st.text_input("Access Key")
    c_secret_key = st.text_input("Secret Key", type="password")

    if st.button("쿠팡 연결 확인"):
        if not all([c_vendor_id, c_access_key, c_secret_key]):
            st.warning("모든 정보를 입력해주세요.")
        else:
            # 쿠팡 HMAC 보안 서명 생성
            import os
            os.environ['TZ'] = 'GMT'
            dt = datetime.utcnow().strftime('%y%m%d' + 'T' + '%H%M%S' + 'Z')
            method = "GET"
            path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
            message = dt + method + path
            
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
                st.success("✅ 쿠팡 연결 성공! 토글과 대표님 프로그램이 모두 정상 작동합니다.")
            else:
                st.error(f"❌ 쿠팡 실패 (코드 {res.status_code})")
                st.info("쿠팡 윙에서 '자체개발' 모드로 선택하고, 위 IP 주소를 등록했는지 확인하세요.")
