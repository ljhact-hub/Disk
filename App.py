import streamlit as st
import json
import csv
import itertools
import re
from collections import Counter
import pandas as pd

# --- 1. Adepti 정밀 데이터 및 공식 설정 ---
AGENT_DB = {
    "루시아": {"atk": 758, "hp": 8477, "def": 594, "crit_r": 5.0, "crit_d": 50.0, "ap": 95, "err": 1.56},
    "반월": {"atk": 859, "hp": 8497, "def": 445, "crit_r": 19.4, "crit_d": 50.0, "ap": 89, "err": 1.0},
    "다이아린": {"atk": 758, "hp": 8250, "def": 612, "crit_r": 19.4, "crit_d": 50.0, "ap": 93, "err": 1.2},
    "자오": {"atk": 765, "hp": 9117, "def": 701, "crit_r": 5.0, "crit_d": 50.0, "ap": 96, "err": 1.2},
    "엽빛나": {"atk": 938, "hp": 7673, "def": 606, "crit_r": 19.4, "crit_d": 50.0, "ap": 93, "err": 1.2},
    "수나": {"atk": 750, "hp": 8477, "def": 600, "crit_r": 5.0, "crit_d": 50.0, "ap": 95, "err": 1.0},
    "앨리스": {"atk": 880, "hp": 7673, "def": 606, "crit_r": 5.0, "crit_d": 50.0, "ap": 118, "err": 1.2},
    "제인": {"atk": 880, "hp": 7788, "def": 606, "crit_r": 5.0, "crit_d": 50.0, "ap": 114, "err": 1.2},
    "청의": {"atk": 758, "hp": 8250, "def": 612, "crit_r": 5.0, "crit_d": 50.0, "ap": 93, "err": 1.2},
    "주연": {"atk": 919, "hp": 7482, "def": 600, "crit_r": 5.0, "crit_d": 78.8, "ap": 92, "err": 1.2},
    "엘렌": {"atk": 938, "hp": 7673, "def": 606, "crit_r": 19.4, "crit_d": 50.0, "ap": 93, "err": 1.2},
    "DEFAULT": {"atk": 800, "hp": 8000, "def": 600, "crit_r": 5.0, "crit_d": 50.0, "ap": 90, "err": 1.2}
} # 편의상 일부만 기재함 (원본의 전체 딕셔너리 그대로 복붙하면 됨)

MAIN_VALUES = {
    "체력": 2200, "공격력": 316, "방어력": 184,
    "체력%": 30.0, "공격력%": 30.0, "방어력%": 48.0, "치확": 24.0, "치피": 48.0, "이상마": 92,
    "관통률": 24.0, "물리 속성 피해%": 30.0, "불 속성 피해%": 30.0, "얼음 속성 피해%": 30.0, 
    "전기 속성 피해%": 30.0, "에테르 속성 피해%": 30.0, "이상 장악력": 18.0, "충격력": 18.0, "에너지 자동 회복": 60.0
}

SUB_ROLL_VALUES = {"치확": 2.4, "치피": 4.8, "공격력%": 3.0, "공격력": 19, "이상마": 9, "에너지 자동 회복": 0.1, "체력%": 3.0, "방어력%": 4.8, "관통 수치": 9}

DEFAULT_SETS = ["딱따구리 일렉트로", "복어 일렉트로", "쇼크스타 디스코", "자유의 블루스", "카오스 재즈", "원시 펑크"] # 원본 리스트 복붙

SET_ALIASES = {
    "딱따구리 일렉트로": ["딱따구리", "딱따"], "복어 일렉트로": ["복어"], "카오스 재즈": ["카오스메탈", "카메", "카재"]
} # 원본 딕셔너리 복붙

# --- 2. 세션 상태 (Session State) 초기화 ---
if 'inventory' not in st.session_state:
    st.session_state.inventory = []
if 'best_build' not in st.session_state:
    st.session_state.best_build = None

# --- 3. 핵심 로직 함수 ---
def map_set_name(raw_name):
    clean = re.sub(r'\s+', '', str(raw_name))
    for std, aliases in SET_ALIASES.items():
        if clean in [re.sub(r'\s+', '', a) for a in aliases] or clean == re.sub(r'\s+', '', std): return std
    return raw_name.strip()

def extract_effective_subs(raw_text):
    if not raw_text: return []
    text = str(raw_text).replace(' ', '').replace('이상마스터리', '이상마')
    tokens = re.split(r'[,/\n\r]', text)
    mapping = {"치확": "치확", "치피": "치피", "공격력": "공격력", "공격력%": "공격력%", "이상마": "이상마", "체력%": "체력%", "에너지자동회복": "에너지 자동 회복"}
    return list(set(mapping[t] for t in tokens if t in mapping))

def parse_target_stats_flat(note_str):
    targets = {}
    clean_str = note_str.replace(',', '') 
    for line in clean_str.split('\n'):
        if m := re.search(r"(공격력|공)\s*[:\-]?\s*([\d\.]+)", line): targets["공격력"] = float(m.group(2))
        if m := re.search(r"(이상\s*마스터리|이상마|이마)\s*[:\-]?\s*([\d\.]+)", line): targets["이상마"] = float(m.group(2))
        if m := re.search(r"(치명타\s*확률|치확)\s*[:\-]?\s*([\d\.]+)", line): targets["치확"] = float(m.group(2))
        if m := re.search(r"(치명타\s*피해|치피)\s*[:\-]?\s*([\d\.]+)", line): targets["치피"] = float(m.group(2))
        if m := re.search(r"(관통률|관통)\s*[:\-]?\s*([\d\.]+)", line): targets["관통률"] = float(m.group(2))
    return targets

def calculate_adepti_score(disk, eff_list):
    score = 0
    for sub in disk.get("subs", []):
        if sub["name"] in eff_list:
            score += (1 + sub.get("upgrade", 0))
    return score

# --- 4. 웹 UI 구성 ---
st.set_page_config(page_title="ZZZ | HYBRID ADEPTI-ENGINE", layout="wide")
st.title("ZZZ | HYBRID ADEPTI-ENGINE (Web Ver.)")

col_left, col_right = st.columns([1, 1.2])

# ========== 왼쪽: 인벤토리 관리 ==========
with col_left:
    st.header("🗃️ INVENTORY")
    
    exclude_equipped = st.checkbox("타 캐릭터 장착 디스크 제외 (Exclude equipped)", value=True)
    
    # 디스크 데이터 업로드/다운로드
    uploaded_file = st.file_uploader("디스크 데이터 업로드 (JSON)", type=['json'])
    if uploaded_file is not None:
        try:
            st.session_state.inventory = json.load(uploaded_file)
            st.success("데이터 로드 완료!")
        except:
            st.error("JSON 파일 형식이 잘못되었습니다.")
            
    if st.session_state.inventory:
        inv_json = json.dumps(st.session_state.inventory, ensure_ascii=False, indent=2)
        st.download_button("💾 현재 인벤토리 백업 (JSON 다운로드)", data=inv_json, file_name="disk_data.json", mime="application/json")
    
    st.subheader("새 디스크 추가")
    with st.expander("디스크 직접 입력 폼 열기"):
        with st.form("add_disk_form"):
            c1, c2, c3 = st.columns(3)
            slot = c1.selectbox("슬롯 번호", [1, 2, 3, 4, 5, 6])
            set_name = c2.selectbox("세트", DEFAULT_SETS)
            main_stat = c3.selectbox("주옵션", ["체력", "공격력", "방어력", "체력%", "공격력%", "방어력%", "치확", "치피", "이상마", "관통률", "물리 속성 피해%", "불 속성 피해%", "얼음 속성 피해%", "전기 속성 피해%", "에테르 속성 피해%", "이상 장악력", "충격력", "에너지 자동 회복"])
            
            st.markdown("**부옵션 입력 (옵션명 / 강화횟수 0~5)**")
            subs = []
            for i in range(4):
                sc1, sc2 = st.columns(2)
                sub_n = sc1.selectbox(f"부옵 {i+1}", ["(None)", "치확", "치피", "공격력", "공격력%", "방어력", "방어력%", "체력", "체력%", "이상마", "관통 수치"], key=f"sn_{i}")
                sub_u = sc2.number_input(f"강화 {i+1}", 0, 5, 0, key=f"su_{i}")
                if sub_n != "(None)":
                    subs.append({"name": sub_n, "upgrade": sub_u})
                    
            owner = st.text_input("장착자 (비워두면 미장착)")
            submitted = st.form_submit_button("추가하기")
            
            if submitted:
                new_disk = {"slot": slot, "set": set_name, "main": main_stat, "level": "15", "subs": subs, "owner": owner}
                st.session_state.inventory.append(new_disk)
                st.success("디스크가 추가되었습니다!")
                st.rerun()

    st.subheader(f"보유 디스크 목록 (총 {len(st.session_state.inventory)}개)")
    if st.session_state.inventory:
        df = pd.DataFrame(st.session_state.inventory)
        df['subs_str'] = df['subs'].apply(lambda x: ", ".join([f"{s['name']}+{s['upgrade']}" for s in x]))
        st.dataframe(df[['slot', 'set', 'main', 'subs_str', 'owner']])

# ========== 오른쪽: 시뮬레이터 ==========
with col_right:
    st.header("⚙️ ADEPTI SIMULATOR")
    
    char_list = list(AGENT_DB.keys())
    char_list.remove("DEFAULT")
    selected_char = st.selectbox("에이전트 선택", char_list)
    
    st.markdown("### 🎯 목표 스탯 및 유효 부옵 설정")
    c1, c2 = st.columns(2)
    target_input = c1.text_area("목표 스탯 (예: 공격력 3000\\n치확 50)", value="공격력 2500\n치확 50\n치피 100")
    eff_input = c2.text_area("유효 부옵 (쉼표 구분)", value="치확, 치피, 공격력%, 공격력")
    
    st.markdown("### 🔧 엔진 및 코어 세팅")
    ec1, ec2, ec3, ec4 = st.columns(4)
    engine_atk = ec1.number_input("엔진 기초공", value=600)
    add_atk_p = ec2.number_input("추가 공(%)", value=0)
    add_ap = ec3.number_input("추가 이상마", value=0)
    add_cr = ec4.number_input("추가 치확(%)", value=0)
    
    # 4세트 / 2세트 조건 입력
    st.markdown("### 🎲 세트 옵션 조건")
    sc1, sc2 = st.columns(2)
    s4_req = sc1.multiselect("요구 4세트", DEFAULT_SETS)
    s2_req = sc2.multiselect("요구 2세트", DEFAULT_SETS)
    
    if st.button("🚀 RUN HYBRID OPTIMIZATION", use_container_width=True, type="primary"):
        with st.spinner('가능한 모든 조합을 연산 중입니다...'):
            eff_list = extract_effective_subs(eff_input)
            target_stats = parse_target_stats_flat(target_input)
            base = AGENT_DB.get(selected_char, AGENT_DB["DEFAULT"])
            
            candidates = []
            for i in range(1, 7):
                pool = [d for d in st.session_state.inventory if d["slot"] == i]
                if exclude_equipped:
                    pool = [d for d in pool if not d.get('owner') or d.get('owner') == selected_char]
                
                # 각 파츠별 유효옵 점수(RV) 기준 상위 15개만 컷팅 (연산량 조절)
                def disk_rv_score(d):
                    sc = 0.0
                    for s in d['subs']:
                        if s['name'].replace('이상 마스터리', '이상마') in eff_list: 
                            sc += (1 + int(s['upgrade']))
                    return sc
                candidates.append(sorted(pool, key=disk_rv_score, reverse=True)[:15])
            
            if any(not c for c in candidates):
                st.error("특정 슬롯의 디스크가 부족하여 조합을 계산할 수 없습니다.")
            else:
                max_eval = -9999999.0
                best_build = None
                best_disk_stats = None
                best_final_stats = None
                
                # 완전 탐색 로직 (원본 코드와 동일)
                for combo in itertools.product(*candidates):
                    c = Counter([d.get('set', 'Unknown') for d in combo])
                    if not any(v >= 4 for v in c.values()): continue 
                    
                    m4, m2, m4_set = False, False, None
                    for s, sn in c.items():
                        if sn >= 4 and (not s4_req or any(rs in s for rs in s4_req)):
                            m4, m4_set = True, s
                            break
                    for s, sn in c.items():
                        if s != m4_set and sn >= 2 and (not s2_req or any(rs in s for rs in s2_req)):
                            m2 = True
                            break
                            
                    base_rv = sum(calculate_adepti_score(d, eff_list) for d in combo)
                    score = base_rv * 100.0
                    if m4 and m2: score += 100000.0
                    elif m4: score += 50000.0
                    
                    disk_stats = {k: 0.0 for k in MAIN_VALUES.keys()}
                    disk_stats.update({k: 0.0 for k in SUB_ROLL_VALUES.keys()})
                    for d in combo:
                        m_type = d['main'].replace('이상 마스터리', '이상마')
                        if m_type in disk_stats: disk_stats[m_type] += MAIN_VALUES.get(m_type, 0)
                        for s in d['subs']:
                            sn = s['name'].replace('이상 마스터리', '이상마')
                            if sn in disk_stats: disk_stats[sn] += (1 + int(s['upgrade'])) * SUB_ROLL_VALUES.get(sn, 0)
                    
                    final_stats = {}
                    final_stats["공격력"] = (base["atk"] + engine_atk) * ((100 + disk_stats["공격력%"] + add_atk_p) / 100) + disk_stats["공격력"]
                    final_stats["치확"] = base["crit_r"] + disk_stats["치확"] + add_cr
                    final_stats["치피"] = base["crit_d"] + disk_stats["치피"]
                    final_stats["이상마"] = base["ap"] + disk_stats["이상마"] + add_ap
                    
                    for t_name, t_val in target_stats.items():
                        c_val = final_stats.get(t_name, 0)
                        if c_val < t_val: score -= ((t_val - c_val) / t_val) ** 2 * 20000.0
                        else:
                            if t_name != "치확": score += ((c_val - t_val) / t_val) * 1000.0
                    if final_stats["치확"] > 100.0: score -= (final_stats["치확"] - 100.0) * 10.0
                    
                    if score > max_eval:
                        max_eval, best_build, best_disk_stats, best_final_stats = score, combo, disk_stats, final_stats
                
                if best_build:
                    st.session_state.best_build = {"char": selected_char, "build": best_build}
                    st.success(f"최적화 완료! (조합 평가 점수: {int(max_eval%100000)})")
                    
                    st.markdown(f"**[{selected_char}] 최종 예상 스탯**")
                    st.info(f"공격력: {int(best_final_stats['공격력'])} | 치확: {best_final_stats['치확']:.1f}% | 치피: {best_final_stats['치피']:.1f}% | 이상마: {int(best_final_stats['이상마'])}")
                    
                    st.markdown("**선택된 디스크 조합**")
                    cols = st.columns(3)
                    for idx, d in enumerate(best_build):
                        sub_str = "<br>".join([f"- {s['name']} +{s['upgrade']}" for s in d['subs']])
                        cols[idx%3].markdown(f"""
                        <div style="border:1px solid #444; padding:10px; border-radius:5px; margin-bottom:10px; background-color:#1E1E24;">
                            <b style="color:#F4C20D;">Slot {d['slot']}</b> [{d['set']}]<br>
                            <b>Main:</b> {d['main']}<br>
                            <span style="color:#AAA; font-size:14px;">{sub_str}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning("조건을 만족하는 디스크 조합을 찾을 수 없습니다.")

    # 장착 버튼 처리
    if st.session_state.best_build and st.session_state.best_build["char"] == selected_char:
        if st.button("✅ 이 조합 장착 (인벤토리 반영)", type="secondary"):
            char = st.session_state.best_build["char"]
            build = st.session_state.best_build["build"]
            
            # 기존 장착 해제
            for d in st.session_state.inventory:
                if d.get('owner') == char:
                    d['owner'] = ""
            
            # 새 디스크에 오너 등록
            for d in build:
                # 인벤토리 내 객체를 찾아서 직접 수정
                for inv_d in st.session_state.inventory:
                    if inv_d == d:  # 딕셔너리 비교
                        inv_d['owner'] = char
                        
            st.session_state.best_build = None # 초기화
            st.success(f"[{char}] 요원에게 디스크 장착이 완료되었습니다! 왼쪽 인벤토리에 적용되었습니다.")
            st.rerun()
