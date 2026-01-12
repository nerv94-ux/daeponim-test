import streamlit as st
import pandas as pd
import io
import re

# 페이지 설정
st.set_page_config(page_title="부가세 마스터 V20", layout="wide")
st.title("🚜 유기농부 부가세 통합 정산 시스템 (V20 - 최종형)")

# --- [1. 유틸리티 함수: 지능형 숫자 변환 및 인코딩] ---
def smart_read(file):
    """여러 인코딩을 시도하여 파일을 읽어옵니다."""
    for enc in ['cp949', 'utf-8-sig', 'utf-8', 'euc-kr']:
        try:
            file.seek(0)
            # 11번가나 일부 엑셀 변환 CSV는 상단에 쓰레기 데이터가 있을 수 있어 체크
            df = pd.read_csv(file, encoding=enc)
            if df.shape[1] < 2: continue # 제대로 안 읽혔으면 다음 인코딩
            return df
        except: continue
    return None

def to_n(val):
    """문자열 숫자를 깨끗한 실수로 변환"""
    if pd.isna(val): return 0
    if isinstance(val, (int, float)): return float(val)
    # 쉼표, 원, 공백 제거
    clean = re.sub(r'[^\d.]', '', str(val))
    try: return float(clean) if clean else 0
    except: return 0

def find_col(df, keyword):
    """컬럼명 중 키워드가 포함된 첫 번째 컬럼을 반환"""
    for col in df.columns:
        if keyword in str(col).replace(" ", ""):
            return col
    return None

# --- [2. 마켓별 지능형 분석 엔진] ---
def analyze_market_intelligence(file):
    fname = file.name
    df = smart_read(file)
    if df is None: return "파일 해독 불가"

    try:
        # A. 스마트스토어 상세내역
        if "스마트스토어" in fname or find_col(df, "과세매출"):
            c_tax = find_col(df, "과세매출")
            c_free = find_col(df, "면세매출")
            c_card = find_col(df, "신용카드")
            c_cash_s = find_col(df, "현금(소득")
            c_cash_j = find_col(df, "현금(지출")
            c_etc = find_col(df, "기타")
            
            # 행별 분류 로직
            df['is_tax'] = df[c_tax].apply(to_n) > 0
            df['is_free'] = df[c_free].apply(to_n) > 0
            
            res = {"과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
            
            # 과세 합산
            tax_df = df[df['is_tax']]
            res["과세_신용"] = tax_df[c_card].apply(to_n).sum()
            res["과세_현금"] = tax_df[c_cash_s].apply(to_n).sum() + tax_df[c_cash_j].apply(to_n).sum()
            res["과세_기타"] = tax_df[c_etc].apply(to_n).sum()
            
            # 면세 합산
            free_df = df[df['is_free']]
            res["면세_신용"] = free_df[c_card].apply(to_n).sum()
            res["면세_현금"] = free_df[c_cash_s].apply(to_n).sum() + free_df[c_cash_j].apply(to_n).sum()
            res["면세_기타"] = free_df[c_etc].apply(to_n).sum()
            return res

        # B. 쿠팡 (과세유형 TAX/FREE 기반)
        elif "쿠팡" in fname or find_col(df, "과세유형"):
            c_type = find_col(df, "과세유형")
            c_card_p = find_col(df, "신용카드(판매)")
            c_card_r = find_col(df, "신용카드(환불)")
            c_cash_p = find_col(df, "현금(판매)")
            c_cash_r = find_col(df, "현금(환불)")
            c_etc_p = find_col(df, "기타(판매)")
            c_etc_r = find_col(df, "기타(환불)")

            df['net_card'] = df[c_card_p].apply(to_n) - df[c_card_r].apply(to_n)
            df['net_cash'] = df[c_cash_p].apply(to_n) - df[c_cash_r].apply(to_n)
            df['net_etc'] = df[c_etc_p].apply(to_n) - df[c_etc_r].apply(to_n)

            t_df = df[df[c_type].str.contains("TAX", na=False)]
            f_df = df[df[c_type].str.contains("FREE", na=False)]

            return {
                "과세_신용": t_df['net_card'].sum(), "과세_현금": t_df['net_cash'].sum(), "과세_기타": t_df['net_etc'].sum(),
                "면세_신용": f_df['net_card'].sum(), "면세_현금": f_df['net_cash'].sum(), "면세_기타": f_df['net_etc'].sum()
            }

        # C. 토스 (상품명 키워드 분류)
        elif "토스" in fname:
            c_name = find_col(df, "상품명")
            c_pay = find_col(df, "결제수단")
            c_amt = find_col(df, "결제수단결제금액")
            
            def toss_tax(name):
                n = str(name)
                if any(x in n for x in ['양배추','당근','감자','브로콜리','농산물']): return 'FREE'
                return 'TAX'
            
            df['type'] = df[c_name].apply(toss_tax)
            res = {"과세_신용": 0, "과세_현금": 0, "과세_기타": 0, "면세_신용": 0, "면세_현금": 0, "면세_기타": 0}
            
            for _, row in df.iterrows():
                amt = to_n(row[c_amt])
                p_method = str(row[c_pay])
                prefix = "과세" if row['type'] == 'TAX' else "면세"
                
                if "카드" in p_method: res[f"{prefix}_신용"] += amt
                elif any(x in p_method for x in ["계좌", "가상", "현금"]): res[f"{prefix}_현금"] += amt
                else: res[f"{prefix}_기타"] += amt
            return res

        # D. 11번가 (5행 스킵 로직 포함)
        elif "11번가" in fname:
            # 11번가는 데이터가 6행부터 시작하는 경우가 많음
            file.seek(0)
            df = pd.read_csv(file, skiprows=5, encoding='cp949')
            c_card = find_col(df, "신용카드결제")
            c_cash = find_col(df, "현금영수증")
            c_etc = find_col(df, "기타결제")
            return {
                "과세_신용": df[c_card].apply(to_n).sum(),
                "과세_현금": df[c_cash].apply(to_n).sum() if c_cash else 0,
                "과세_기타": df[c_etc].apply(to_n).sum() if c_etc else 0,
                "면세_신용": 0, "면세_현금": 0, "면세_기타": 0
            }

    except Exception as e:
        return f"분석 중 오류 발생: {str(e)}"
    return "지원하지 않는 파일 형식"

# --- [3. 메인 UI] ---
with st.sidebar:
    st.header("⚙️ 설정")
    period = st.text_input("리포트 제목", "2025년 3분기 부가세 정산")

files = st.file_uploader("📂 정산 파일들을 모두 선택하세요 (20개 이상 무제한)", accept_multiple_files=True)

if files:
    st.subheader("📋 업로드 파일 분석 현황")
    logs = []
    final_summary = {"과세": {"신용카드": 0, "현금영수증": 0, "기타": 0}, "면세": {"신용카드": 0, "현금영수증": 0, "기타": 0}}

    if st.button("🚀 정산 시작 (분류기 가동)"):
        for f in files:
            res = analyze_market_intelligence(f)
            if isinstance(res, dict):
                logs.append({"파일명": f.name, "상태": "✅ 성공", "금액": f"{int(sum(res.values())):,}원"})
                # 마스터 합산
                for k, v in res.items():
                    cat, typ = k.split('_')
                    t_map = {"신용": "신용카드", "현금": "현금영수증", "기타": "기타"}
                    final_summary[cat][t_map[typ]] += v
            else:
                logs.append({"파일명": f.name, "상태": f"❌ {res}", "금액": "0원"})
        
        st.table(pd.DataFrame(logs))
        
        # 결과 표
        st.divider()
        st.subheader(f"📊 {period} 통합 결과")
        df_res = pd.DataFrame(final_summary).T
        df_res['합계'] = df_res.sum(axis=1)
        st.table(df_res.applymap(lambda x: f"{int(x):,}원"))

        # 엑셀 내보내기
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_res.to_excel(writer, sheet_name='부가세정산')
            st.download_button("📥 세무사 제출용 엑셀 다운로드", output.getvalue(), f"{period}.xlsx")
        except:
            st.info("💡 엑셀 엔진이 설치되지 않았습니다. 수치를 복사해서 사용하세요.")
            
        st.code(f"""
[세무사 제출용 요약]
과세 합계: {int(df_res.loc['과세', '합계']):,}원
면세 합계: {int(df_res.loc['면세', '합계']):,}원
총 매출: {int(df_res['합계'].sum()):,}원
        """)
