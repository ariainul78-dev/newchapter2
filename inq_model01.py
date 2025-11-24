import os
import json
from datetime import datetime
import streamlit as st
import pymysql
from pymongo import MongoClient
import openai
from dotenv import load_dotenv

# =========================================
# 환경 변수 로드
# =========================================
load_dotenv()
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
MODEL = 'gpt-4o'

openai.api_key = OPENAI_API_KEY

# MongoDB 설정 (전역)
mongo_client = MongoClient(st.secrets["MONGO_URI"])
db = mongo_client[st.secrets["MONGO_DB"]]
collection = db[st.secrets["MONGO_COLLECTION"]]
collection_feedback = db[st.secrets["MONGO_COLLECTION_FEEDBACK"]]

# 페이지 기본 설정
st.set_page_config(page_title="수학여행 도우미", page_icon="🧠", layout="wide")

# 초기 프롬프트
initial_prompt = '''
너는 '수학여행 도우미'라는 이름의 챗봇으로, 고등학생의 수학 문제 해결을 돕는 역할을 수행한다.

너의 목표는 학생이 스스로 탐구하고 문제를 해결할 수 있도록 유도하는 것이다. 어떤 경우에도 정답이나 풀이 과정을 직접 제공하지 말고, 수학 개념, 사고 전략, 접근 방법, 개념 유도 질문 등을 제공해야 한다.

대화는 다음 절차를 따른다:
1. 학생이 수학 문제를 제시한다.
2. 너는 문제 해결에 필요한 수학 개념, 사고 방향, 접근 전략을 안내한다.
3. 너는 어떤 대화 경우에도 학생이 제시한 수학문제의 정답이나 풀이 과정을 직접 제공하지 않는다.
4. 학생이 "궁금한 건 다 물어봤어"라고 말하면, 종료 조건을 만족하는지 판단하고 대화를 요약한 후 피드백을 제공한다.
5. 종료 후 학생이 다음 단계로 넘어갈 수 있도록 [다음] 버튼 클릭을 안내한다.

**대화 방식 지침**
- 질문은 한 번에 한 가지, 한 문장 이내로 간결하게 한다.
- 개념 설명은 학생 수준에서 명확하고 간결하게 한다.
- 어떤 경우에도 정답이나 풀이 과정은 절대 제공하지 않는다.
- 학생이 정답이나 풀이를 요구해도 개념과 접근 방법으로만 안내한다.
- 정답을 정확히 제시한 경우에는 난이도를 높인 문제를 제시한다.
- 사고를 유도하는 질문을 사용한다. 예:
  - "이 문제를 해결하려면 어떤 공식을 써야 할까?"
  - "이 상황에서 어떤 수학 개념이 떠오르니?"

**힌트 제공 원칙**
- 정답 대신 더 쉬운 유사 문제 또는 핵심 개념을 제시한다.
- 학생이 제시한 개념이나 공식을 평가하고, 필요시 보충 설명을 제공한다.

**풀이 평가 및 피드백 규칙**
- 정확한 풀이를 제시한 경우 더 어려운 문제로 이어간다.
- 오류가 있으면 더 쉬운 문제를 제시하고 개념을 재정리한다.

**금지 사항**
- 어떤 대화 경우에도 학생이 제시한 수학문제의 정답이나 풀이 과정을 직접 제공하지 않는다.
- "모르겠어요"라고 해도 답을 알려주지 말고 질문과 유도를 통해 사고를 유도한다.

**LaTeX 수식 처리 규칙**
- 모든 수학 개념과 공식은 반드시 LaTeX 수식으로 표현하여 출력한다.
- 인라인 수식은 `$수식$`, 블록 수식은 `$$ 수식 $$` 형태로 출력한다.
- 학생이 LaTeX 형식으로 `$` 또는 `$$` 없이 수식을 입력하여도 자동으로 `$수식$`, 블록 수식은 `$$ 수식 $$` 형태로 변환하여 출력한다.
- 수식 문법 오류가 있어도 에러 메시지를 출력하지 않고 자연스럽게 올바른 표현으로 안내한다.

**종료 조건**:
- 학생이 “마침”이라고 말하면, 지금까지의 대화 내용을 요약해줘.
  - 학생이 스스로 정답을 말한 경우: 가이드 답안을 제공하고 추가 문제를 제시해 줘
  - 정답을 말하지 않은 경우: 정답을 언급하지 않고 사용한 접근 방식이나 전략만 정리해 줘.
  - 마지막엔 “이제 [다음] 버튼을 눌러 마무리해 줘!”라고 안내해.
'''

# =========================================
# 세션 상태 초기화
# =========================================
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "chat_ended" not in st.session_state:
    st.session_state["chat_ended"] = False
if "user_said_finish" not in st.session_state:
    st.session_state["user_said_finish"] = False

# =========================================
# MongoDB 저장 함수
# =========================================
def save_to_mongo(all_data):
    number = st.session_state.get('user_number', '').strip()
    name = st.session_state.get('user_name', '').strip()
    if not number or not name:
        st.error("사용자 학번과 이름을 입력해야 합니다.")
        return False

    try:
        document = {
            "number": number,
            "name": name,
            "chat": all_data,
            "time": datetime.now()
        }
        collection.insert_one(document)
        return True
    except Exception as e:
        st.error(f"MongoDB 저장 중 오류가 발생했습니다: {e}")
        return False

# =========================================
# GPT 응답 생성 함수
# =========================================
def get_chatgpt_response(prompt):
    messages_for_api = [{"role": "system", "content": initial_prompt}] + st.session_state["messages"] + [{"role": "user", "content": prompt}]
    try:
        response = openai.chat.completions.create(
            model=MODEL,
            messages=messages_for_api,
        )
        answer = response.choices[0].message.content

        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.session_state["messages"].append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        st.error(f"OpenAI 오류: {e}")
        return "[Error: GPT 응답 실패]"

# =========================================
# 세션 상태 초기화
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
# 페이지 1: 학번 및 이름 입력
# =========================================
def page_1():
    st.title("수학여행 도우미 챗봇 M1")
    st.write("학번과 이름을 입력한 뒤 '다음' 버튼을 눌러주세요.")
    st.session_state["user_number"] = st.text_input("학번", value=st.session_state.get("user_number",""))
    st.session_state["user_name"] = st.text_input("이름", value=st.session_state.get("user_name",""))

    if st.button("다음"):
        if not st.session_state["user_number"].strip() or not st.session_state["user_name"].strip():
            st.error("학번과 이름을 모두 입력해주세요.")
        else:
            st.session_state["step"] = 2
            st.rerun()

# =========================================
# 페이지 2: 사용법 안내
# =========================================
def page_2():
    st.title("수학여행 도우미 활용 방법")
    st.write("학생은 문제를 입력하고, 인공지능이 개념과 전략을 안내합니다. '마침'을 누르면 피드백 페이지로 이동합니다.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("이전"):
            st.session_state["step"] = 1
            st.rerun()
    with col2:
        if st.button("다음"):
            st.session_state["step"] = 3
            st.rerun()

# =========================================
# 페이지 3: GPT와 대화
# =========================================
def page_3():
    st.title("수학여행 도우미와 대화하기")
    if not st.session_state.get("user_number") or not st.session_state.get("user_name"):
        st.error("학번과 이름이 누락되었습니다.")
        st.session_state["step"] = 1
        st.rerun()

    if st.session_state.get("chat_ended", False):
        st.info("대화가 종료되었습니다. [다음] 버튼을 눌러 피드백을 확인하세요.")
        st.text_area("You:", value="", disabled=True)
        col1, col2 = st.columns(2)
        with col1: st.button("전송", disabled=True)
        with col2: st.button("마침", disabled=True)
    else:
        user_input = st.text_area("You:", value="", key="user_input_temp")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("전송"):
                if user_input.strip():
                    get_chatgpt_response(user_input)
                    st.rerun()
        with col2:
            if st.button("마침"):
                get_chatgpt_response("마침")
                st.session_state["chat_ended"] = True
                st.session_state["user_said_finish"] = True
                st.rerun()

    st.subheader("📜 누적 대화")
    for msg in st.session_state["messages"]:
        role = "You" if msg["role"]=="user" else "수학여행 도우미"
        st.write(f"**{role}:** {msg['content']}")

    col3, col4 = st.columns(2)
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

# =========================================
# 페이지 4: 피드백
# =========================================
def page_4():
    st.title("수학여행 도우미의 제안")

    if st.session_state.get("user_said_finish", False) and not st.session_state.get("feedback_saved", False):
        chat_history = "\n".join(f"{msg['role']}: {msg['content']}" for msg in st.session_state["messages"])
        prompt = f"학생이 '마침'을 눌렀습니다. 대화 요약과 피드백 생성:\n\n{chat_history}"
        response = openai.chat.completions.create(
            model=MODEL,
            messages=[{"role":"system","content":prompt}]
        )
        st.session_state["experiment_plan"] = response.choices[0].message.content

    st.subheader("📋 생성된 피드백")
    st.write(st.session_state.get("experiment_plan",""))

    # 저장
    all_data_to_store = st.session_state["messages"] + [{"role":"assistant","content":st.session_state.get("experiment_plan","")}]
    if not st.session_state.get("feedback_saved", False):
        if save_to_mongo(all_data_to_store):
            st.session_state["feedback_saved"] = True
            st.success("대화 기록이 저장되었습니다.")
        else:
            st.error("저장 실패!")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("처음으로"):
            reset_session_state()
            st.session_state["step"] = 1
            st.rerun()
    with col2:
        if st.button("종료"):
            st.stop()

# =========================================
# Main
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
