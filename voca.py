import streamlit as st
from openai import OpenAI
import json, os
from datetime import datetime

# ================= 설정 =================
DATA_FILE = "voca.json"
MODEL_NAME = "gpt-4.1-mini"

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ================= 유틸 =================
def now_ymd():
    return datetime.now().strftime("%Y-%m-%d")

def normalize_token(s: str) -> str:
    # 정답 판정용: 공백 제거 + 소문자
    return (s or "").strip().lower()

def normalize_mean_string(mean: str) -> str:
    # 뜻 저장용: / 기준 분리 -> 공백 제거 -> 빈칸 제거 -> 중복 제거
    parts = [p.strip() for p in (mean or "").split("/") if p.strip()]
    seen = set()
    out = []
    for p in parts:
        key = p  # 뜻은 한글일 수 있으니 lower() 안 함
        if key not in seen:
            seen.add(key)
            out.append(p)
    return "/".join(out)

def safe_json_load(path: str):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        # 파일이 깨졌으면 백업하고 새로 시작
        try:
            os.rename(path, path + ".broken")
        except Exception:
            pass
        return {}

def safe_json_save(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# ================= DB =================
def load_db():
    return safe_json_load(DATA_FILE)

def save_db(db):
    safe_json_save(DATA_FILE, db)

# ================= 상태 =================
if "page" not in st.session_state:
    st.session_state.page = "home"

if "current_session" not in st.session_state:
    st.session_state.current_session = None

if "quiz" not in st.session_state:
    st.session_state.quiz = {}

# 퀴즈 방향 상태를 session_state로 고정 (rerun에도 유지)
if "quiz_dir" not in st.session_state:
    st.session_state.quiz_dir = "EN_KO"  # 기본: 영->한

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
                seen[normalize_token(item.get("word",""))] = item
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

            # 기본 뜻 정규화
            mean_clean = normalize_mean_string(mean)

            ai_mean_clean = ""
            if use_ai:
                try:
                    r = client.responses.create(
                        model=MODEL_NAME,
                        input=f"영어 단어 '{word}'의 가장 많이 쓰이는 한국어 뜻을 핵심 단어만 / 로 구분해서 알려줘. 불필요한 설명은 빼고 뜻만."
                    )
                    ai_mean_clean = normalize_mean_string(r.output_text.strip())
                except Exception as e:
                    st.warning("AI 뜻 생성에 실패했어. (사용자 입력 뜻으로만 저장할게)")
                    ai_mean_clean = ""

            # 뜻 합치기
            merged = normalize_mean_string("/".join([mean_clean, ai_mean_clean]))

            # 뜻이 완전 비었으면 저장은 하되 경고
            if not merged:
                st.warning("뜻이 비어있어. 나중에 수정할 수 있어!")

            # 중복 단어 처리: 같은 단어가 있으면 '업데이트'
            key = normalize_token(word)
            existing = None
            for item in voca_db[session]:
                if normalize_token(item.get("word","")) == key:
                    existing = item
                    break

            if existing:
                # 뜻은 합치고, wrong는 유지
                existing["mean"] = normalize_mean_string("/".join([existing.get("mean",""), merged]))
                existing.setdefault("wrong", 0)
                existing.setdefault("correct", 0)
                existing["updated_at"] = now_ymd()
                st.success("이미 있는 단어라서 뜻을 합쳐 업데이트했어!")
            else:
                voca_db[session].append({
                    "word": word,
                    "mean": merged,
                    "wrong": 0,
                    "correct": 0,
                    "created_at": now_ymd(),
                    "updated_at": now_ymd(),
                })
                st.success("추가 완료!")

            save_db(voca_db)
            st.rerun()

    st.divider()
    st.subheader("📋 단어 목록")

    if not voca_db[session]:
        st.info("아직 단어가 없어. 위에서 추가해줘!")
        st.divider()

    # 단어 목록: 수정/삭제
    for i, item in enumerate(list(voca_db[session])):  # 안전하게 복사
        word = item.get("word", "")
        mean_val = item.get("mean", "")

        c1, c2, c3 = st.columns([3, 6, 1])

        with c1:
            st.markdown(f"**{word}**")

        with c2:
            new_mean = st.text_input(
                "뜻",
                value=mean_val,
                key=f"mean_{session}_{i}"
            )
            new_mean_norm = normalize_mean_string(new_mean)
            if new_mean_norm != normalize_mean_string(mean_val):
                item["mean"] = new_mean_norm
                item["updated_at"] = now_ymd()
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
            "state": "CHECK",  # CHECK -> NEXT
            "last_result": None,  # {"ok": bool, "answers": [...]}
        }
        st.session_state.page = "quiz"
        st.rerun()

# ================= 퀴즈 =================
def quiz_page():
    qz = st.session_state.quiz
    lst = qz.get("list", [])

    st.title("📝 퀴즈")

    # 뒤로가기
    if st.button("⬅ 단어장으로", use_container_width=True):
        st.session_state.page = "vocab"
        st.rerun()

    st.divider()

    if not lst:
        st.info("퀴즈를 낼 단어가 없어. 단어장에 단어를 추가해줘!")
        return

    # 방향 토글 (session_state로 유지)
    is_ko_en = st.checkbox("한 → 영", value=(st.session_state.quiz_dir == "KO_EN"))
    st.session_state.quiz_dir = "KO_EN" if is_ko_en else "EN_KO"

    # 종료
    if qz["idx"] >= len(lst):
        st.subheader("🏁 퀴즈 종료")
        st.write(f"{len(lst)}문제 중 **{qz['correct']}개 정답**")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("❌ 오답만 다시 풀기", use_container_width=True):
                qz["list"] = qz["wrong"]
                qz["wrong"] = []
                qz["idx"] = 0
                qz["correct"] = 0
                qz["state"] = "CHECK"
                qz["last_result"] = None
                st.rerun()
        with col2:
            if st.button("🔁 처음부터 다시", use_container_width=True):
                # wrong 기준 정렬로 다시 시작
                qz["list"] = sorted(qz["list"], key=lambda x: -(x.get("wrong", 0)))
                qz["wrong"] = []
                qz["idx"] = 0
                qz["correct"] = 0
                qz["state"] = "CHECK"
                qz["last_result"] = None
                st.rerun()
        return

    q = lst[qz["idx"]]

    # 문제 표시
    st.write(f"**{qz['idx'] + 1} / {len(lst)}**")

    prompt_text = q.get("word", "") if st.session_state.quiz_dir == "EN_KO" else q.get("mean", "")
    st.subheader(prompt_text)

    # 마지막 결과 표시
    last = qz.get("last_result")
    if last and qz["state"] == "NEXT":
        if last["ok"]:
            st.success("정답 ✅")
        else:
            st.error("오답 ❌")
            st.caption(f"정답: {', '.join(last['answers'])}")

    # 입력 & 버튼 (CHECK와 NEXT를 버튼으로 분리)
    ans = st.text_input("정답 입력", key=f"ans_{qz['idx']}")

    c1, c2 = st.columns(2)

    with c1:
        if st.button("정답 확인", use_container_width=True, disabled=(qz["state"] != "CHECK")):
            # 정답 후보 만들기
            if st.session_state.quiz_dir == "EN_KO":
                answers = [a.strip() for a in (q.get("mean", "")).split("/") if a.strip()]
                # 뜻은 소문자 정규화 안 함 (한글/혼합 대비), 대신 공백만 제거한 비교 추가
                user = (ans or "").strip()
                ok = user in answers
            else:
                answers = [q.get("word", "").strip()]
                user = normalize_token(ans)
                ok = user == normalize_token(answers[0])

            if ok:
                qz["correct"] += 1
                q["correct"] = int(q.get("correct", 0)) + 1
            else:
                q["wrong"] = int(q.get("wrong", 0)) + 1
                # 오답 리스트 중복 방지: 객체 id 기반
                if q not in qz["wrong"]:
                    qz["wrong"].append(q)

            qz["last_result"] = {"ok": ok, "answers": answers}
            qz["state"] = "NEXT"
            save_db(voca_db)
            st.rerun()

    with c2:
        if st.button("다음 ▶", use_container_width=True, disabled=(qz["state"] != "NEXT")):
            qz["idx"] += 1
            qz["state"] = "CHECK"
            qz["last_result"] = None
            st.rerun()

# ================= 실행 =================
if st.session_state.page == "home":
    home()
elif st.session_state.page == "vocab":
    vocab_page()
else:
    quiz_page()
