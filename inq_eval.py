import streamlit as st
import json
from sqlalchemy import create_engine, text

# -----------------------------
# PostgreSQL 연결 (Supabase / Railway secrets)
# -----------------------------
DATABASE_URL = st.secrets["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

# -----------------------------
# Streamlit 앱 설정
# -----------------------------
st.set_page_config(page_title="학생 인공지능 사용 내역 (교사용)", layout="wide")
st.title("학생의 인공지능 사용 내역 (교사용)")

# -----------------------------
# 비밀번호 입력
# -----------------------------
password = st.text_input("비밀번호를 입력하세요", type="password")

# -----------------------------
# PostgreSQL에서 모든 레코드 가져오기
# -----------------------------
def fetch_records():
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT id, number, name, time FROM qna ORDER BY time DESC")
            )
            records = [{"id": row.id, "number": row.number, "name": row.name, "time": row.time} for row in result]
        return records
    except Exception as e:
        st.error(f"PostgreSQL 오류: {e}")
        return []

# -----------------------------
# 특정 ID의 레코드 가져오기
# -----------------------------
def fetch_record_by_id(record_id):
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT chat FROM qna WHERE id = :id"), {"id": record_id}
            )
            row = result.fetchone()
            if row and row.chat:
                chat_data = row.chat
                # chat가 문자열이면 json으로 변환
                if isinstance(chat_data, str):
                    chat_data = json.loads(chat_data)
                return chat_data
            return None
    except Exception as e:
        st.error(f"PostgreSQL 오류: {e}")
        return None

# -----------------------------
# 비밀번호 검증 및 레코드 표시
# -----------------------------
if password == st.secrets["PASSWORD"]:
    records = fetch_records()

    if records:
        record_options = [
            f"{rec['number']} ({rec['name']}) - {rec['time']}" for rec in records
        ]
        selected_record = st.selectbox("내역을 선택하세요:", record_options)
        selected_record_id = records[record_options.index(selected_record)]["id"]

        chat = fetch_record_by_id(selected_record_id)
        if chat:
            st.write("### 학생의 대화 기록")
            for message in chat:
                if message.get("role") == "user":
                    st.markdown(f"**학생:** {message.get('content','')}")
                elif message.get("role") == "assistant":
                    st.markdown(f"**AI Tutor:** {message.get('content','')}")
        else:
            st.warning("선택된 레코드에 대화 기록이 없습니다.")
    else:
        st.warning("데이터베이스에 저장된 내역이 없습니다.")
else:
    if password:  # 비어있을 때는 에러 안뜨게
        st.error("비밀번호가 틀렸습니다.")
