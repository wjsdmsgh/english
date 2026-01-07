import streamlit as st
from openai import OpenAI
import json, os
from datetime import datetime

# ================= 설정 =================
DATA_FILE = "voca.json"
MODEL_NAME = "gpt-4.1-mini"

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ================= 유틸 =================
def today():
    return datetime.now().strftime("%Y-%m-%d")

def norm_word(s: str) -> str:
    return (s or "").strip().lower()

def normalize_mean(mean: str) -> str:
    parts = [p.strip() for p in (mean or "").split("/") if p.strip()]
    seen = set()
    out = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return "/".join(out)

def load_db():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        # 깨진 파일이면 백업 후 새로 시작
        try:
            os.rename(DATA_FILE, DATA_FILE + ".broken")
        except Exception:
            pass
        return {}

def save_db(db: dict):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

# ================= 상태 =================
if "page" not in st.session_state:
    st.session_state.page = "home"

if "current_session" not in st.session_state:
    st.session_state.current_session = None

if "quiz" not in st.session_state:
    st.session_state.quiz = {}

voca_db = load_db()

# ================= 홈 =================
def home():
    st.title("📚 단어장 선택")

    with st.form("create_session", clear_on_submit=True):
        name = st.text_input("회차(예: 1회차, Unit1)")
        submitted = st.form_submit_button("생성")
        if submitted:
            name = (name or "").strip()
            if not name:
                st.warning("회차 이름을 입력해줘.")
                st.stop()

            voca_db.setdefault(name, [])
            save_db(voca_db)

            st.session_state.current_session = name
            st.session_state.page = "vocab"
            st.rerun()

    st.divider()

    if not voca_db:
        st.info("아직 만든 단어장이 없어. 위에서 회차를 먼저 생성해줘!")
        return

    for s in voca_db.keys():
        if st.button(s, use_container_width=True):
            st.session_state.current_session = s
            st.session_state.page = "vocab"
            st.rerun()

# ================= 단어장 =================
def vocab_page():
    session = st.session_state.current_session
    if not session:
        st.session_state.page = "home"
        st.rerun()

    voca_db.setdefault(session, [])

    st.title(f"📘 {session}")

    colA, colB = st.columns([1, 1])
    with colA:
        if st.button("⬅ 회차 선택", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()

    with colB:
        if st.button("🧹 중복 단어 정리", use_container_width=True):
            # 같은 단어가 여러 개면 마지막 것만 남김
            seen = {}
            for item in voca_db[session]:
                seen[norm_word(item.get("word", ""))] = item
            voca_db[session] = [v for k, v in seen.items() if k]
            save_db(voca_db)
            st.success("중복 단어를 정리했어!")
            st.rerun()

    st.divider()

    # -------- 단어 추가 --------
    st.subheader("➕ 단어 추가")
    with st.form("add_word", clear_on_submit=True):
        word = st.text_input("영어 단어")
        mean = st.text_input("뜻 (/로 구분)")
        use_ai = st.checkbox("AI로 뜻 보강하기", value=True)
        submitted = st.form_submit_button("추가")

        if submitted:
            word = (word or "").strip()
            mean = (mean or "").strip()

            if not word:
                st.warning("영어 단어를 입력해줘.")
                st.stop()

            mean_clean = normalize_mean(mean)

            ai_mean_clean = ""
            if use_ai:
                try:
                    r = client.responses.create(
                        model=MODEL_NAME,
                        input=f"영어 단어 '{word}'의 가장 많이 쓰이는 한국어 뜻을 핵심 단어만 / 로 구분해서 알려줘. 불필요한 설명은 빼고 뜻만."
                    )
                    ai_mean_clean = normalize_mean(r.output_text.strip())
                except Exception:
                    st.warning("AI 뜻 생성에 실패했어. (사용자 입력 뜻으로만 저장할게)")
                    ai_mean_clean = ""

            merged = normalize_mean("/".join([mean_clean, ai_mean_clean]))

            if not merged:
                st.warning("뜻이 비어있어. 나중에 수정할 수 있어!")

            # 중복 단어면 업데이트
            key = norm_word(word)
            existing = None
            for item in voca_db[session]:
                if norm_word(item.get("word", "")) == key:
                    existing = item
                    break

            if existing:
                existing["mean"] = normalize_mean("/".join([existing.get("mean", ""), merged]))
                existing.setdefault("wrong", 0)
                existing.setdefault("correct", 0)
                existing["updated_at"] = today()
                st.success("이미 있는 단어라서 뜻을 합쳐 업데이트했어!")
            else:
                voca_db[session].append({
                    "word": word,
                    "mean": merged,
                    "wrong": 0,
                    "correct": 0,
                    "created_at": today(),
                    "updated_at": today(),
                })
                st.success("추가 완료!")

            save_db(voca_db)
            st.rerun()

    st.divider()
    st.subheader("📋 단어 목록")

    if not voca_db[session]:
        st.info("아직 단어가 없어. 위에서 추가해줘!")

    # 단어 목록: 수정/삭제
    for i, item in enumerate(list(voca_db[session])):  # 안전하게 복사
        word = item.get("word", "")
        mean_val = item.get("mean", "")

        c1, c2, c3 = st.columns([3, 6, 1])

        with c1:
            st.markdown(f"**{word}**")
            st.caption(f"오답: {item.get('wrong', 0)}")

        with c2:
            new_mean = st.text_input(
                "뜻",
                value=mean_val,
                key=f"mean_{session}_{i}"
            )
            new_mean_norm = normalize_mean(new_mean)
            if new_mean_norm != normalize_mean(mean_val):
                item["mean"] = new_mean_norm
                item["updated_at"] = today()
                save_db(voca_db)

        with c3:
            if st.button("🗑", key=f"del_{session}_{i}"):
                voca_db[session].remove(item)
                save_db(voca_db)
                st.rerun()

    st.divider()

    if st.button("▶ 퀴즈 시작", use_container_width=True):
        quiz_list = sorted(voca_db[session], key=lambda x: -(x.get("wrong", 0)))
        st.session_state.quiz = {
            "list": quiz_list,
            "wrong": [],
            "idx": 0,
            "correct": 0,
            "state": "CHECK",      # CHECK -> NEXT
            "dir": None,           # 아직 선택 안 함
            "phase": "SETUP",      # SETUP -> RUN -> END
            "last_result": None,   # {"ok": bool, "answers": [...]}
            "last_answer": ""      # 직전 입력값
        }
        st.session_state.page = "quiz"
        st.rerun()

# ================= 퀴즈 =================
def quiz_page():
    qz = st.session_state.quiz
    lst = qz.get("list", [])

    st.title("📝 퀴즈")

    if st.button("⬅ 단어장으로", use_container_width=True):
        st.session_state.page = "vocab"
        st.rerun()

    st.divider()

    if not lst:
        st.info("퀴즈를 낼 단어가 없어. 단어장에 단어를 추가해줘!")
        return

    # (1) 시작 전: 방향 선택
    if qz.get("phase") == "SETUP":
        st.subheader("퀴즈 설정")
        mode = st.radio(
            "어떤 방식으로 풀래?",
            ["영어 → 한국어", "한국어 → 영어"],
            index=0,
            horizontal=True
        )
        if st.button("시작하기 ▶", use_container_width=True):
            qz["dir"] = "EN_KO" if mode == "영어 → 한국어" else "KO_EN"
            qz["phase"] = "RUN"
            qz["state"] = "CHECK"
            qz["idx"] = 0
            qz["correct"] = 0
            qz["wrong"] = []
            qz["last_result"] = None
            qz["last_answer"] = ""
            st.rerun()
        return

    # (2) 결과 화면
    if qz.get("phase") == "END":
        total = len(qz.get("list", []))
        correct = qz.get("correct", 0)
        acc = (correct / total * 100) if total else 0

        st.subheader("🏁 퀴즈 종료")
        st.write(f"총 **{total}문제** 중 **{correct}문제 정답**")
        st.write(f"정답률: **{acc:.1f}%**")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("❌ 오답만 다시 풀기", use_container_width=True):
                qz["list"] = qz["wrong"]
                qz["wrong"] = []
                qz["idx"] = 0
                qz["correct"] = 0
                qz["state"] = "CHECK"
                qz["phase"] = "RUN"
                qz["last_result"] = None
                qz["last_answer"] = ""
                st.rerun()
        with col2:
            if st.button("🔁 다시 설정하고 시작", use_container_width=True):
                qz["phase"] = "SETUP"
                qz["dir"] = None
                st.rerun()
        return

    # (3) 문제 풀이 RUN
    idx = qz.get("idx", 0)
    if idx >= len(lst):
        qz["phase"] = "END"
        st.rerun()

    q = lst[idx]
    direction = qz.get("dir", "EN_KO")

    st.write(f"**{idx + 1} / {len(lst)}**")

    question_text = q.get("word", "") if direction == "EN_KO" else q.get("mean", "")
    st.subheader(question_text)

    # 직전 결과 표시
    last = qz.get("last_result")
    if last and qz.get("state") == "NEXT":
        if last["ok"]:
            st.success("정답 ✅")
        else:
            st.error("오답 ❌")
            st.caption(f"정답: {', '.join(last['answers'])}")

        if idx == len(lst) - 1:
            st.info("엔터(제출)를 한 번 더 누르면 결과가 나와!")

    # Enter 제출을 위해 form 사용
    form_key = f"answer_form_{idx}_{qz.get('state')}"
    with st.form(form_key, clear_on_submit=False):
        ans = st.text_input("정답 입력 (엔터로 제출)", value="", key=f"ans_{idx}")
        submitted = st.form_submit_button("제출 (Enter)")

        if submitted:
            # CHECK: 정답 확인
            if qz["state"] == "CHECK":
                user = (ans or "").strip()

                if direction == "EN_KO":
                    answers = [a.strip() for a in (q.get("mean", "")).split("/") if a.strip()]
                    ok = user in answers
                else:
                    answers = [(q.get("word", "") or "").strip()]
                    ok = user.lower() == answers[0].lower()

                if ok:
                    qz["correct"] += 1
                else:
                    q["wrong"] = int(q.get("wrong", 0)) + 1
                    if q not in qz["wrong"]:
                        qz["wrong"].append(q)

                qz["last_result"] = {"ok": ok, "answers": answers}
                qz["last_answer"] = user
                qz["state"] = "NEXT"

                save_db(voca_db)
                st.rerun()

            # NEXT: 다음(또는 결과)
            else:
                if idx == len(lst) - 1:
                    qz["phase"] = "END"
                    st.rerun()

                qz["idx"] += 1
                qz["state"] = "CHECK"
                qz["last_result"] = None
                qz["last_answer"] = ""
                st.rerun()

# ================= 실행 =================
if st.session_state.page == "home":
    home()
elif st.session_state.page == "vocab":
    vocab_page()
else:
    quiz_page()
