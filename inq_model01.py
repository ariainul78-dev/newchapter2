import os
import json
import streamlit as st
from datetime import datetime
from sqlalchemy import create_engine, text
import openai  # pakai ini saja

# =========================================
# Streamlit Secrets
# =========================================
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
DATABASE_URL = st.secrets["DATABASE_URL"]
MODEL = "gpt-4o-mini"  # bisa diganti sesuai akses

# set API key
openai.api_key = OPENAI_API_KEY

# =========================================
# PostgreSQL Connection
# =========================================
engine = create_engine(DATABASE_URL)

# =========================================
# Streamlit Page Config
# =========================================
st.set_page_config(
    page_title="수학여행 도우미",
    page_icon="🧠",
    layout="wide"
)

# =========================================
# Initial Prompt
# =========================================
initial_prompt = """
너는 '수학여행 도우미' 이름의 챗봇으로, 고등학생의 수학 문제 해결을 돕는다.
설명은 친절하지만 학생 스스로 생각하게 유도한다.
"""

# =========================================
# Session State Init
# =========================================
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "chat_ended" not in st.session_state:
    st.session_state["chat_ended"] = False
if "user_said_finish" not in st.session_state:
    st.session_state["user_said_finish"] = False

# =========================================
# Save to PostgreSQL
# =========================================
def save_to_postgres(all_data):
    number = st.session_state.get("user_number", "").strip()
    name = st.session_state.get("user_name", "").strip()

    if not number or not name:
        st.error("학번과 이름을 입력해야 저장할 수 있습니다.")
        return False

    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO qna (number, name, chat, time)
                    VALUES (:number, :name, :chat, NOW())
                """),
                {
                    "number": number,
                    "name": name,
                    "chat": json.dumps(all_data),
                }
            )
        return True
    except Exception as e:
        st.error(f"데이터베이스 저장 오류: {e}")
        return False

# =========================================
# OpenAI API
# =========================================
def get_openai_response(prompt):
    messages_for_api = (
        [{"role": "system", "content": initial_prompt}]
        + st.session_state["messages"]
        + [{"role": "user", "content": prompt}]
    )

    try:
        response = openai.chat.completions.create(
            model=MODEL,
            messages=messages_for_api
        )

        answer = response.choices[0].message.content

        # simpan ke session state
        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.session_state["messages"].append({"role": "assistant", "content": answer})

        return answer

    except Exception as e:
        st.error(f"OpenAI Error: {e}")
        return "[Error: gagal memproses permintaan]"

# =========================================
# Reset Session
# =========================================
def reset_session_state():
    for key in list(st.session_state.keys()):
        if key not in ["user_number", "user_name"]:
            del st.session_state[key]
    st.session_state["messages"] = []
    st.session_state["chat_ended"] = False
    st.session_state["user_said_finish"] = False
    st.session_state["feedback_saved"] = False

# =========================================
# Page 1 – User Info
# =========================================
def page_1():
    st.title("수학여행 도우미 M1")
    st.write("학번과 이름을 입력하세요.")

    st.session_state["user_number"] = st.text_input(
        "학번",
        value=st.session_state.get("user_number", "")
    )
    st.session_state["user_name"] = st.text_input(
        "이름",
        value=st.session_state.get("user_name", "")
    )

    if st.button("다음"):
        if not st.session_state["user_number"].strip() or not st.session_state["user_name"].strip():
            st.error("학번과 이름을 모두 입력하세요.")
        else:
            st.session_state["step"] = 2
            st.rerun()

# =========================================
# Page 2 – Instructions
# =========================================
def page_2():
    st.title("수학여행 도우미 사용방법")
    st.write("챗봇을 사용하여 문제 해결을 연습하세요.")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("이전"):
            st.session_state["step"] = 1
            st.rerun()
    with col2:
        if st.button("다음"):
            st.session_state["step"] = 3
            st.rerun()

# =========================================
# Page 3 – Chat Interface
# =========================================
def page_3():
    st.title("수학여행 도우미와 대화하기")

    if not st.session_state.get("user_number") or not st.session_state.get("user_name"):
        st.error("학번과 이름이 누락되었습니다.")
        st.session_state["step"] = 1
        st.rerun()

    user_input = st.text_area("You:", "")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("전송"):
            if user_input.strip():
                get_openai_response(user_input)
                st.rerun()
    with col2:
        if st.button("마침"):
            get_openai_response("마침")
            st.session_state["chat_ended"] = True
            st.session_state["user_said_finish"] = True
            st.rerun()

    st.subheader("📜 대화 기록")
    for msg in st.session_state["messages"]:
        if msg["role"] == "user":
            st.write(f"**You:** {msg['content']}")
        else:
            st.write(f"**수학여행 도우미:** {msg['content']}")

# =========================================
# Page 4 – Summary & Save
# =========================================
def page_4():
    st.title("수학여행 도우미의 제안")

    if not st.session_state.get("user_said_finish"):
        st.write("대화를 먼저 종료하세요.")
        return

    chat_history = "\n".join(
        f"{m['role']}: {m['content']}" for m in st.session_state["messages"]
    )

    prompt = f"다음 대화를 요약하고 학생에게 필요한 피드백을 작성하세요:\n\n{chat_history}"

    response = openai.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": prompt}]
    )

    result = response.choices[0].message.content
    st.session_state["experiment_plan"] = result

    st.subheader("📋 피드백 결과")
    st.write(result)

    if not st.session_state.get("feedback_saved", False):
        all_data_to_store = (
            st.session_state["messages"]
            + [{"role": "assistant", "content": result}]
        )

        if save_to_postgres(all_data_to_store):
            st.success("저장되었습니다!")
            st.session_state["feedback_saved"] = True
        else:
            st.error("저장 실패.")

# =========================================
# Main Routing
# =========================================
if "step" not in st.session_state:
    st.session_state["step"] = 1

if st.session_state["step"] == 1:
    page_1()
elif st.session_state["step"] == 2:
    page_2()
elif st.session_state["step"] == 3:
    page_3()
elif st.session_state["step"] == 4:
    page_4()
