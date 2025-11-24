import pymysql
from openai import OpenAI
import os
import json
from dotenv import load_dotenv
from datetime import datetime
from pymongo import MongoClient as PyMongoClient
import streamlit as st
import httpx # <-- DITAMBAHKAN: Diperlukan untuk konfigurasi http client yang lebih aman

# --- KONFIGURASI AWAL ---

# Lingkungan: st.secrets digunakan di Streamlit Cloud, tidak perlu load_dotenv() di sini.
# load_dotenv() 

# Ambil API Key dari Streamlit Secrets
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
MODEL = 'gpt-4o'

# OpenAI API Pengaturan
# Perbaikan untuk mengatasi error "unexpected keyword argument 'proxies'"
# Menginisialisasi httpx.Client secara eksplisit untuk menghindari konflik proxy
try:
    # Membuat klien HTTPX dasar tanpa pengaturan proxy eksplisit 
    # (ini seringkali mengatasi konflik di lingkungan cloud)
    base_http_client = httpx.Client()
    client = OpenAI(api_key=OPENAI_API_KEY, http_client=base_http_client)
except Exception:
    # Jika klien HTTPX bermasalah, kembali ke inisialisasi standar
    client = OpenAI(api_key=OPENAI_API_KEY)


# MongoDB Pengaturan
mongo_client = PyMongoClient(st.secrets["MONGO_URI"])
db = mongo_client[st.secrets["MONGO_DB"]]
collection = db[st.secrets["MONGO_COLLECTION"]]
collection_feedback = db[st.secrets["MONGO_COLLECTION_FEEDBACK"]]

# Halaman Pengaturan Dasar
st.set_page_config(page_title="수학여행 도우미", page_icon="🧠", layout="wide")

# --- PROMPT SISTEM ---
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

# --- SESSION STATE INISIALISASI ---
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "chat_ended" not in st.session_state:
    st.session_state["chat_ended"] = False
if "user_said_finish" not in st.session_state:
    st.session_state["user_said_finish"] = False
if "step" not in st.session_state:
    st.session_state["step"] = 1 # <--- DITAMBAHKAN: Mengatur langkah awal

# --- FUNGSI PENDUKUNG ---

# MongoDB Simpan Fungsi
def save_to_mongo(all_data):
    number = st.session_state.get('user_number', '').strip()
    name = st.session_state.get('user_name', '').strip()

    if not number or not name:
        st.error("사용자 학번과 이름을 입력해야 합니다.")
        return False

    mongo_client_local = None 
    try:
        # Gunakan konfigurasi mongo_client global yang sudah didefinisikan di atas,
        # atau buat koneksi lokal baru jika ingin memastikan koneksi fresh
        from pymongo import MongoClient
        mongo_client_local = MongoClient(st.secrets["MONGO_URI"]) # <--- Menggunakan koneksi lokal baru untuk menyimpan
        db_local = mongo_client_local[st.secrets["MONGO_DB"]]
        collection_local = db_local[st.secrets["MONGO_COLLECTION"]]

        now = datetime.now()

        document = {
            "number": number,
            "name": name,
            "chat": all_data,
            "time": now
        }

        collection_local.insert_one(document)
        return True

    except Exception as e:
        st.error(f"MongoDB 저장 중 오류가 발생했습니다: {e}")
        return False

    finally:
        if mongo_client_local:
            mongo_client_local.close()


# GPT Respon Generate Fungsi
def get_chatgpt_response(prompt):
    # Gunakan client global yang sudah diinisialisasi di atas
    messages_for_api = [{"role": "system", "content": initial_prompt}] + st.session_state["messages"] + [{"role": "user", "content": prompt}]
    
    # Menambahkan penanganan error untuk API call
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages_for_api,
        )
        answer = response.choices[0].message.content

        # Simpan dialog ke session state
        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.session_state["messages"].append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        st.error(f"OpenAI API 호출 중 오류가 발생했습니다: {e}")
        return "죄송합니다. 현재 AI 서버에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."


# Session State Reset Fungsi
def reset_session_state():
    for key in list(st.session_state.keys()):
        if key not in ["user_number", "user_name"]: # 학번과 이름은 유지
            del st.session_state[key]
    st.session_state["messages"] = []
    st.session_state["chat_ended"] = False
    st.session_state["user_said_finish"] = False
    st.session_state["feedback_saved"] = False 


# --- HALAMAN APLIKASI ---

# Halaman 1: Input 학번 (Nomor Siswa) 및 이름 (Nama)
def page_1():
    st.title("수학여행 도우미 챗봇 M1")
    st.write("학번과 이름을 입력한 뒤 '다음' 버튼을 눌러주세요.")

    if "user_number" not in st.session_state:
        st.session_state["user_number"] = ""
    if "user_name" not in st.session_state:
        st.session_state["user_name"] = ""

    st.session_state["user_number"] = st.text_input("학번", value=st.session_state["user_number"])
    st.session_state["user_name"] = st.text_input("이름", value=st.session_state["user_name"])

    st.write(" ") 
    if st.button("다음", key="page1_next_button"):
        if st.session_state["user_number"].strip() == "" or st.session_state["user_name"].strip() == "":
            st.error("학번과 이름을 모두 입력해주세요.")
        else:
            st.session_state["step"] = 2
            st.rerun()

# Halaman 2: Panduan Penggunaan
def page_2():
    st.title("수학여행 도우미 활용 방법")
    st.write(
        """  
        ※주의! '자동 번역'을 활성화하면 대화가 이상하게 번역되므로 활성화하면 안 돼요. 혹시 이미 '자동 번역' 버튼을 눌렀다면 비활성화 하세요.  

학생은 다음과 같은 절차로 챗봇을 활용하도록 안내되었습니다:

① 인공지능에게 수학 문제를 알려주세요.

② LATex기반으로 문제 입력시 (1)문장 속 수식은 `$수식$`, (2)블록 수식은 `$$ 수식 $$` 형식으로 입력해주세요.

③ 인공지능은 문제 해결에 필요한 수학 개념, 공식, 해결 전략, 접근 방향을 단계적으로 안내할 거예요. 궁금한 점은 언제든지 질문하세요.

④ 궁금한 걸 다 물어봤다면 ‘궁금한 건 다 물어봤어’라고 말해주세요. 또는 [마침] 버튼을 눌러주세요.

⑤ 인공지능이 충분히 대화가 이루어졌다고 판단되면 [다음] 버튼을 눌러도 된다고 안내할 거예요. 그때 버튼을 눌러주세요.
        """)

    # Tombol
    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("이전"):
            st.session_state["step"] = 1
            st.rerun()

    with col2:
        if st.button("다음", key="page2_next_button"):
            st.session_state["step"] = 3
            st.rerun()

# Halaman 3: Chat dengan GPT
def page_3():
    st.title("수학여행 도우미 활용하기")
    st.write("수학여행 도우미와 대화를 나누며 수학을 설계하세요.")

    if not st.session_state.get("user_number") or not st.session_state.get("user_name"):
        st.error("학번과 이름이 누락되었습니다. 다시 입력해주세요.")
        st.session_state["step"] = 1
        st.rerun()

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    if "user_input_temp" not in st.session_state:
        st.session_state["user_input_temp"] = ""

    if "recent_message" not in st.session_state:
        st.session_state["recent_message"] = {"user": "", "assistant": ""}

    # Chat sudah berakhir, nonaktifkan input dan tombol Send/Finish
    if st.session_state.get("chat_ended", False):
        st.info("대화가 종료되었습니다. [다음] 버튼을 눌러 피드백을 확인해주세요.")
        user_input = st.text_area(
            "You: ",
            value="",
            key="user_input",
            disabled=True
        )
        col1, col2 = st.columns([1, 1])
        with col1:
            st.button("전송", disabled=True)
        with col2:
            st.button("마침", disabled=True)
    else:
        user_input = st.text_area(
            "You: ",
            value=st.session_state["user_input_temp"],
            key="user_input",
            on_change=lambda: st.session_state.update({"user_input_temp": st.session_state["user_input"]}),
        )

        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("전송"):
                if user_input.strip():
                    assistant_response = get_chatgpt_response(user_input)
                    st.session_state["recent_message"] = {"user": user_input, "assistant": assistant_response}
                    st.session_state["user_input_temp"] = ""
                    st.rerun()

        with col2:
            if st.button("마침"):
                final_input = "마침"
                assistant_response = get_chatgpt_response(final_input)
                st.session_state["recent_message"] = {"user": final_input, "assistant": assistant_response}
                st.session_state["user_input_temp"] = ""
                st.session_state["chat_ended"] = True
                st.session_state["user_said_finish"] = True 
                st.rerun()

    # Output
    st.subheader("📌 최근 대화")
    if st.session_state["recent_message"]["user"] or st.session_state["recent_message"]["assistant"]:
        st.write(f"**You:** {st.session_state['recent_message']['user']}")
        st.write(f"**수학여행 도우미:** {st.session_state['recent_message']['assistant']}")
    else:
        st.write("아직 최근 대화가 없습니다.")

    st.subheader("📜 누적 대화 목록")
    if st.session_state["messages"]:
        for message in st.session_state["messages"]:
            if message["role"] == "user":
                st.write(f"**You:** {message['content']}")
            elif message["role"] == "assistant":
                st.write(f"**수학여행 도우미:** {message['content']}")
    else:
        st.write("아직 대화 기록이 없습니다.")

    col3, col4 = st.columns([1, 1])
    with col3:
        if st.button("이전"):
            st.session_state["step"] = 2
            st.session_state["chat_ended"] = False 
            st.session_state["user_said_finish"] = False 
            st.rerun()
    with col4:
        if st.session_state.get("chat_ended", False):
            if st.button("다음", key="page3_next_button_enabled"):
                st.session_state["step"] = 4
                st.session_state["feedback_saved"] = False
                st.rerun()
        else:
            st.button("다음", key="page3_next_button_disabled", disabled=True)


# MySQL Simpan Feedback Fungsi (Perlu diperhatikan: save_to_mongo sudah ada. Fungsi ini tampaknya untuk Feedback terpisah)
def save_feedback_to_db(feedback):
    number = st.session_state.get('user_number', '').strip()
    name = st.session_state.get('user_name', '').strip()

    if not number or not name:
        st.error("사용자 학번과 이름을 입력해야 합니다.")
        return False

    try:
        # Perhatikan: Pastikan Anda telah menginstal pymysql
        db = pymysql.connect(
            host=st.secrets["DB_HOST"],
            user=st.secrets["DB_USER"],
            password=st.secrets["DB_PASSWORD"],
            database=st.secrets["DB_DATABASE"],
            charset="utf8mb4",
            autocommit=True
        )
        cursor = db.cursor()
        now = datetime.now()

        sql = """
        INSERT INTO feedback (number, name, feedback, time)
        VALUES (%s, %s, %s, %s)
        """
        val = (number, name, feedback, now)

        cursor.execute(sql, val)
        cursor.close()
        db.close()
        st.success("피드백이 성공적으로 저장되었습니다.")
        return True
    except pymysql.MySQLError as db_err:
        st.error(f"DB 처리 중 오류가 발생했습니다: {db_err}")
    except Exception as e:
        st.error(f"알 수 없는 오류가 발생했습니다: {e}")
    return False

# Halaman 4: Output Proses Penyelesaian Masalah
def page_4():
    st.title("수학여행 도우미의 제안")
    st.write("수학여행 도우미가 대화 내용을 정리 중입니다. 잠시만 기다려주세요.")

    # Cek apakah feedback sudah dibuat di session state
    if "experiment_plan" not in st.session_state or not st.session_state.get("feedback_saved", False):

        # Pastikan ada pesan, kalau tidak kembali ke halaman 3
        if not st.session_state["messages"]:
            st.warning("대화 기록이 없습니다. 이전 페이지로 돌아가 대화를 시작해주세요.")
            st.session_state["step"] = 3
            st.rerun()
            return
            
        chat_history = "\n".join(f"{msg['role']}: {msg['content']}" for msg in st.session_state["messages"])
        
        if st.session_state.get("user_said_finish", False):
            prompt = f"""
다음은 학생과 수학여행 도우미의 대화 기록입니다:

{chat_history}

---

학생이 "마침"이라고 말했습니다. 이제 다음 지침에 따라 대화 내용을 요약하고 피드백을 제공하세요:

📌 **1. 대화 내용 요약**
- 학생이 어떤 개념을 시도했고, 어떤 실수를 했으며 어떻게 수정했는지를 중심으로 요약하세요.
- 가독성을 위해 문단마다 줄바꿈을 사용하세요.

💬 **2. 문제해결 능력 피드백**
- 개념 적용, 전략적 사고, 자기주도성, 오개념 교정 등의 측면에서 평가하세요.

🧾 **3. 수학적 결과 또는 전략 정리 (조건 분기)**

- **학생이 대화 중 스스로 정확한 정답을 제시한 경우**:
  - 문제 풀이 과정을 간결히 요약하고, LaTeX 수식으로 최종 정답을 제시하세요.
  - 그리고 이어서 **난이도를 높인 새로운 수학 문제를 제시하세요.**

- **정답을 제시하지 못했거나 오답을 제시한 경우**:
- 정답을 언급하지 않고 문제 해결에 필요한 핵심 개념, 공식, 전략만 정리하세요. 설명은 생략하고 수식만 제시하세요.

- 마지막으로, **"이제 [다음] 버튼을 눌러 마무리해 줘!"** 라고 안내해주세요.

반드시 위 형식을 따르고, 항목 순서를 변경하지 마세요.
"""
        else: 
            st.session_state["experiment_plan"] = "현재 대화가 명확히 종료되지 않았습니다. 이전 페이지로 돌아가서 '마침' 버튼을 누르거나 대화를 계속 진행해주세요."
            st.warning(st.session_state["experiment_plan"])
            return # Keluar dari fungsi jika tidak ada input '마침'

        # OpenAI API 호출 (hanya jika ada prompt valid)
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": prompt}]
            )
            st.session_state["experiment_plan"] = response.choices[0].message.content
        except Exception as e:
            st.error(f"피드백 생성 중 OpenAI API 오류: {e}")
            st.session_state["experiment_plan"] = "피드백 생성 중 오류가 발생했습니다."


    # Output Feedback
    st.subheader("📋 생성된 피드백")
    st.write(st.session_state["experiment_plan"])

    # Data untuk disimpan ke MongoDB
    all_data_to_store = st.session_state["messages"] + [{"role": "assistant", "content": st.session_state["experiment_plan"]}]

    # Menyimpan ke MongoDB
    if "feedback_saved" not in st.session_state:
        st.session_state["feedback_saved"] = False

    if not st.session_state["feedback_saved"]:
        if save_to_mongo(all_data_to_store):
            st.session_state["feedback_saved"] = True
        else:
            st.error("저장에 실패했습니다. 다시 시도해주세요.")
    else:
        st.info("이미 피드백이 저장되었습니다.")


    # Tombol
    col_end1, col_end2 = st.columns([1, 1])

    with col_end1:
        if st.button("저장 후 종료", key="save_and_exit_button"):
            st.success("대화 기록이 성공적으로 저장되었습니다. 프로그램을 종료합니다.")
            st.stop() 
            
    with col_end2:
        if st.button("처음으로", key="start_over_button"):
            st.success("대화 기록이 성공적으로 저장되었습니다. 처음 페이지로 돌아갑니다.")
            reset_session_state()
            st.session_state["step"] = 1 
            st.rerun()


# --- LOGIKA UTAMA ---

if st.session_state["step"] == 1:
    page_1()
elif st.session_state["step"] == 2:
    page_2()
elif st.session_state["step"] == 3:
    page_3()
elif st.session_state["step"] == 4:
    page_4()
