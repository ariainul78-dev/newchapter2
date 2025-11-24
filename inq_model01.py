import os
import json
import streamlit as st
from datetime import datetime
from sqlalchemy import create_engine, text
import openai

# -----------------------------
# 환경 변수 (Streamlit secrets)
# -----------------------------
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
DATABASE_URL = st.secrets["DATABASE_URL"]
MODEL = "gpt-3.5-turbo"  # Bisa diganti "gpt-4" jika punya akses

openai.api_key = OPENAI_API_KEY

# -----------------------------
# PostgreSQL 연결
# -----------------------------
engine = create_engine(DATABASE_URL)

# -----------------------------
# Streamlit 페이지 설정
# -----------------------------
st.set_page_config(page_title="수학여행 도우미", page_icon="🧠", layout="wide")

# -----------------------------
# 초기 프롬프트
# -----------------------------
initial_prompt = '''
너는 '수학여행 도우미'라는 이름의 챗봇으로, 고등학생의 수학 문제 해결을 돕는 역할을 수행한다.

너의 목표는 학생이 스스로 탐구하고 문제를 해결할 수 있도록 유도하는 것이다. 어떤 경우에도 정답이나 풀이 과정을 직접 제공하지 말고, 수학 개념, 사고 전략, 접근 방법, 개념 유도 질문 등을 제공해야 한다.
'''

# -----------------------------
# 세션 상태 초기화
# -----------------------------
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "chat_ended" not in st.session_state:
    st.session_state["chat_ended"] = False
if "user_said_finish" not in st.session_state:
    st.session_state["user_said_finish"] = False

# -----------------------------
# PostgreSQL 저장 함수
# -----------------------------
def save_to_postgres(all_data):
    number = st.session_state.get('user_number', '').strip()
    name = st.session_state.get('user_name', '').strip()

    if not number or not name:
        st.error("사용자 학번과 이름을 입력해야 합니다.")
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
                    "chat": json.dumps(all_data)
                }
            )
        return True
    except Exception as e:
        st.error(f"PostgreSQL 저장 중 오류가 발생했습니다: {e}")
        return False

# -----------------------------
# OpenAI 응답 생성 함수 (API v1 usage)
# -----------------------------
def get_openai_response(prompt):
    # construct messages: system + prior messages + new user message
    messages_for_api = [{"role": "system", "content": initial_prompt}] + st.session_state["messages"] + [{"role": "user", "content": prompt}]
    try:
        # gunakan API terbaru: openai.chat.completions.create
        response = openai.chat.completions.create(
            model=MODEL,
            messages=messages_for_api,
            temperature=0.7,
            max_tokens=1024
        )
        # ambil teks jawaban
        # new SDK returns choices with message object
        answer = response.choices[0].message.get("content", "")
        # simpan di session
        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.session_state["messages"].append({"role": "assistant", "content": answer})
        return answer
    except openai.error.RateLimitError:
        st.error("OpenAI rate limit tercapai. Silakan tunggu dan coba lagi.")
        return "[Error: rate limit]"
    except openai.error.AuthenticationError:
        st.error("OpenAI API key tidak valid. Periksa OPENAI_API_KEY di secrets.")
        return "[Error: auth]"
    except Exception as e:
        st.error(f"OpenAI 호출 중 오류가 발생했습니다: {e}")
        return f"[Error: {e}]"

# -----------------------------
# 세션 상태 초기화 함수
# -----------------------------
def reset_session_state():
    for key in list(st.session_state.keys()):
        if key not in ["user_number", "user_name"]:
            del st.session_state[key]
    st.session_state["messages"] = []
    st.session_state["chat_ended"] = False
    st.session_state["user_said_finish"] = False
    st.session_state["feedback_saved"] = False

# -----------------------------
# 페이지 1 ~ 3
# -----------------------------
def page_1():
    st.title("수학여행 도우미 챗봇 M1")
    st.write("학번과 이름을 입력한 뒤 '다음' 버튼을 눌러주세요.")
    st.session_state["user_number"] = st.text_input("학번", value=st.session_state.get("user_number", ""))
    st.session_state["user_name"] = st.text_input("이름", value=st.session_state.get("user_name", ""))
    if st.button("다음", key="page1_next_button"):
        if not st.session_state["user_number"].strip() or not st.session_state["user_name"].strip():
            st.error("학번과 이름을 모두 입력해주세요.")
        else:
            st.session_state["step"] = 2
            st.rerun()

def page_2():
    st.title("수학여행 도우미 활용 방법")
    st.write("학생은 안내를 따라 챗봇을 활용할 수 있습니다.")
    st.markdown("""
    **사용법 요약**
    1. 문제를 입력하세요. (수식은 LaTeX: `$...$` 또는 `$$...$$`)
    2. AI가 개념과 접근방법을 안내합니다(정답 직접 제공 금지).
    3. 대화가 끝나면 '마침'을 눌러 요약/피드백을 받으세요.
    """)
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("이전"):
            st.session_state["step"] = 1
            st.rerun()
    with col2:
        if st.button("다음", key="page2_next_button"):
            st.session_state["step"] = 3
            st.rerun()

def page_3():
    st.title("수학여행 도우미 활용하기")
    if not st.session_state.get("user_number") or not st.session_state.get("user_name"):
        st.error("학번과 이름이 누락되었습니다.")
        st.session_state["step"] = 1
        st.rerun()
    # 입력 영역
    user_input = st.text_area("You: ", value="", key="user_input", height=150)
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("전송"):
            if user_input.strip():
                # panggil OpenAI
                assistant_response = get_openai_response(user_input)
                st.session_state["recent_message"] = {"user": user_input, "assistant": assistant_response}
                st.session_state["user_input_temp"] = ""
                st.rerun()
    with col2:
        if st.button("마침"):
            final_input = "마침"
            assistant_response = get_openai_response(final_input)
            st.session_state["recent_message"] = {"user": final_input, "assistant": assistant_response}
            st.session_state["chat_ended"] = True
            st.session_state["user_said_finish"] = True
            st.rerun()

    # 최근 대화 출력
    st.subheader("📌 최근 대화")
    if st.session_state.get("recent_message"):
        st.write(f"**You:** {st.session_state['recent_message']['user']}")
        st.write(f"**수학여행 도우미:** {st.session_state['recent_message']['assistant']}")

    # 누적 대화 출력
    st.subheader("📜 누적 대화 목록")
    if st.session_state["messages"]:
        for message in st.session_state["messages"]:
            if message["role"] == "user":
                st.markdown(f"**You:** {message['content']}")
            elif message["role"] == "assistant":
                st.markdown(f"**수학여행 도우미:** {message['content']}")
    else:
        st.write("아직 대화 기록이 없습니다.")

    # navigasi
    col3, col4 = st.columns([1,1])
    with col3:
        if st.button("이전"):
            st.session_state["step"] = 2
            st.rerun()
    with col4:
        if st.session_state.get("chat_ended", False):
            if st.button("다음"):
                st.session_state["step"] = 4
                st.session_state["feedback_saved"] = False
                st.rerun()
        else:
            st.button("다음", disabled=True)

# -----------------------------
# 페이지 4
# -----------------------------
def page_4():
    st.title("수학여행 도우미의 제안")
    st.write("수학여행 도우미가 대화 내용을 정리 중입니다.")
    chat_history = "\n".join(f"{msg['role']}: {msg['content']}" for msg in st.session_state["messages"])
    if st.session_state.get("user_said_finish", False):
        prompt = f"학생과 수학여행 도우미의 대화 기록:\n{chat_history}\n---\n대화 요약 및 피드백 생성"
        try:
            response = openai.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.5,
                max_tokens=800
            )
            plan = response.choices[0].message.get("content", "")
            st.session_state["experiment_plan"] = plan
            st.subheader("📋 생성된 피드백")
            st.write(st.session_state["experiment_plan"])
            # 저장
            if not st.session_state.get("feedback_saved", False):
                all_data_to_store = st.session_state["messages"] + [{"role": "assistant", "content": st.session_state["experiment_plan"]}]
                if save_to_postgres(all_data_to_store):
                    st.session_state["feedback_saved"] = True
                else:
                    st.error("저장 실패")
        except openai.error.RateLimitError:
            st.error("OpenAI rate limit tercapai. Silakan tunggu dan coba lagi.")
        except Exception as e:
            st.error(f"OpenAI 호출 중 오류가 발생했습니다: {e}")
    else:
        st.write("대화가 종료되지 않았습니다.")

# -----------------------------
# 메인 로직
# -----------------------------
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
