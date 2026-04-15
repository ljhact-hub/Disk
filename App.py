import streamlit as st
import json
import csv
import itertools
import re
import os
import base64
from collections import Counter
import pandas as pd

# --- 1. 기본 설정 ---
THEME = {"accent": "#F4C20D", "bg": "#0F1115"}

MAIN_VALUES = {
    "체력": 2200, "공격력": 316, "방어력": 184,
    "체력%": 30.0, "공격력%": 30.0, "방어력%": 48.0, "치확": 24.0, "치피": 48.0, "이상마": 92,
    "관통률": 24.0, "물리 속성 피해%": 30.0, "불 속성 피해%": 30.0, "얼음 속성 피해%": 30.0, 
    "전기 속성 피해%": 30.0, "에테르 속성 피해%": 30.0, "이상 장악력": 18.0, "충격력": 18.0, "에너지 자동 회복": 60.0
}

SUB_ROLL_VALUES = {"치확": 2.4, "치피": 4.8, "공격력%": 3.0, "공격력": 19, "이상마": 9, "에너지 자동 회복": 0.1, "체력%": 3.0, "방어력%": 4.8, "관통 수치": 9}

DEFAULT_SETS = ["딱따구리 일렉트로", "복어 일렉트로", "쇼크스타 디스코", "자유의 블루스", "호르몬 펑크", "소울 록", "스윙 재즈", "불지옥 메탈", "카오스 재즈", "썬더 메탈", "극지 메탈", "송곳니 메탈", "빛의 아리아", "물빛 노랫소리", "달빛 기사의 칭송", "여명의 꽃", "산림의 왕", "운규 이야기", "파에톤의 노래", "그림자처럼 함께", "나뭇가지 검의 노래", "고요 속의 별", "원시 펑크"]

SET_ALIASES = {
    "딱따구리 일렉트로": ["딱따구리", "딱따"], "복어 일렉트로": ["복어"], "쇼크스타 디스코": ["쇼크스타", "쇼크"], "자유의 블루스": ["자유", "블루스"], "호르몬 펑크": ["호르몬", "호르몬재즈"], "소울 록": ["소울록"], "스윙 재즈": ["스윙"], "불지옥 메탈": ["불지옥"], "카오스 재즈": ["카오스메탈", "카메", "카재", "카오스재즈"], "썬더 메탈": ["썬더", "천둥"], "극지 메탈": ["극지"], "송곳니 메탈": ["송곳니"], "빛의 아리아": ["아리아"], "물빛 노랫소리": ["물빛"], "달빛 기사의 칭송": ["달빛기사"], "여명의 꽃": ["여명"], "산림의 왕": ["산림"], "운규 이야기": ["운규"], "파에톤의 노래": ["파에톤"], "그림자처럼 함께": ["그림자"], "나뭇가지 검의 노래": ["나뭇가지"], "고요 속의 별": ["고요별"], "원시 펑크": ["프로토펑크", "원시펑크"]
}

DEFAULT_BASE = {"atk": 800, "hp": 8000, "def": 600, "crit_r": 5.0, "crit_d": 50.0, "ap": 90, "err": 1.2}

# --- 2. 세션 상태 초기화 ---
if 'inventory' not in st.session_state: st.session_state.inventory = []
if 'char_db' not in st.session_state: st.session_state.char_db = {}
if 'dynamic_sets' not in st.session_state: st.session_state.dynamic_sets = list(DEFAULT_SETS)
if 'best_build' not in st.session_state: st.session_state.best_build = None

# --- 3. 로직 및 파싱 함수 (원본 그대로 이식) ---
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

def parse_agent_data(rows, name_idx, h_idx):
    data_row = rows[name_idx]
    for j in range(name_idx - 1, h_idx, -1):
        if len(rows[j]) > 2 and rows[j][2].strip() != '': data_row = rows[j]; break
    eff_list = extract_effective_subs(data_row[10] if len(data_row) > 10 else "")
    raw_s4 = re.sub(r'\(.*?\)', '', data_row[5]) if len(data_row) > 5 else ""
    s4_o = [map_set_name(s) for s in re.split(r'[/,\n\r]', raw_s4) if s.strip()]
    raw_s2 = re.sub(r'\(.*?\)', '', data_row[6]) if len(data_row) > 6 else ""
    s2_o = [map_set_name(s) for s in re.split(r'[/,\n\r]', raw_s2) if s.strip()]
    return {"eff_list": eff_list, "set4_opts": s4_o, "set2_opts": s2_o, "display_sets": s4_o + s2_o, "target_str": data_row[12] if len(data_row) > 12 else "", "note": data_row[14] if len(data_row) > 14 else "-", "hint": f"4번:{data_row[7]}, 5번:{data_row[8]}, 6번:{data_row[9]}"}

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
        if sub["name"] in eff_list: score += (1 + sub.get("upgrade", 0))
    return score

# 이미지 Base64 변환 (웹 HTML에서 로컬 이미지 띄우기 위함)
def get_img_base64(set_name):
    path = os.path.join("assets", f"{set_name}.png")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

# 디스크 카드 렌더링 함수
def render_disk_card(d, is_result=False, eff_list=None):
    b64 = get_img_base64(d['set'])
    bg_style = f"background-image: url('data:image/png;base64,{b64}'); background-size: cover; background-position: center;" if b64 else "background-color: #2C2F36;"
    sub_str = "<br>".join([f"<span style='color:{'#00FF00' if eff_list and s['name'] in eff_list else '#FFF'};'>- {s['name']} +{s['upgrade']}</span>" for s in d['subs']])
    owner_tag = f"<div style='background:rgba(0,0,0,0.7); color:#F4C20D; font-size:10px; display:inline-block; padding:2px 5px; border-radius:3px;'>[{d['owner']}]</div>" if d.get('owner') and not is_result else ""
    rv_tag = f"<div style='color:#00FFFF; font-size:12px; font-weight:bold; margin-top:5px;'>RV: {calculate_adepti_score(d, eff_list)}</div>" if is_result and eff_list else ""
    
    return f"""
    <div style="border: 2px solid #2C2F36; border-radius: 10px; width: 140px; height: 180px; position: relative; overflow: hidden; margin-bottom: 10px;">
        <div style="position: absolute; top:0; left:0; right:0; bottom:0; {bg_style} opacity: 0.5;"></div>
        <div style="position: relative; z-index: 1; padding: 8px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <b style="background:#2A2D35; border:1px solid #C0C0C0; padding:2px 6px; border-radius:4px; color:white;">{d['slot']}</b>
                <span style="background:rgba(0,0,0,0.6); color:white; font-size:11px; padding:2px 4px;">+{d['level']}</span>
            </div>
            <div style="background:rgba(0,0,0,0.6); color:white; font-size:11px; font-weight:bold; margin-top:5px; padding:2px;">{d['main'][:4]}</div>
            {owner_tag}
            <div style="margin-top: 10px; font-size: 12px; font-weight:bold; text-shadow: 1px 1px 2px black;">{sub_str}</div>
            {rv_tag}
        </div>
    </div>
    """

# --- 4. CSV 데이터 로드 처리 ---
def process_csv_data(raw_data):
    try:
        raw = list(csv.reader(raw_data))
        h_idx = next(i for i, r in enumerate(raw) if '캐릭명' in "".join(r))
        new_db = {}; ex_s = set(DEFAULT_SETS)
        for i, row in enumerate(raw):
            if i <= h_idx or not row: continue
            if row[0].strip() != '' and not any(x in row[0] for x in ['진영', '팀', '소대']):
                parsed = parse_agent_data(raw, i, h_idx)
                if parsed: 
                    new_db[row[0].strip()] = parsed
                    ex_s.update(parsed.get("display_sets", []))
        st.session_state.char_db = new_db
        st.session_state.dynamic_sets = sorted([s for s in ex_s if s.strip()])
    except Exception as e:
        st.error(f"CSV 파싱 에러: {e}")

# 초기 구동 시 로컬 ZZZ_Settings.csv가 있으면 자동 로드
if not st.session_state.char_db and os.path.exists("ZZZ_Settings.csv"):
    with open("ZZZ_Settings.csv", 'r', encoding='utf-8-sig') as f:
        process_csv_data(f.readlines())

# --- 5. 웹 UI ---
st.set_page_config(page_title="ZZZ | HYBRID ADEPTI-ENGINE", layout="wide")
st.title("ZZZ | HYBRID ADEPTI-ENGINE (Web Ver.)")

col_left, col_right = st.columns([1, 1.2])

with col_left:
    st.header("🗃️ INVENTORY")
    
    st.markdown("##### ⚙️ 데이터 연동 (CSV / JSON)")
    fc1, fc2 = st.columns(2)
    csv_file = fc1.file_uploader("캐릭터 DB (CSV 엑셀)", type=['csv'])
    if csv_file:
        content = csv_file.getvalue().decode('utf-8-sig').splitlines()
        process_csv_data(content)
        st.success("CSV 데이터 갱신 완료!")
        
    json_file = fc2.file_uploader("인벤토리 백업 (JSON)", type=['json'])
    if json_file:
        st.session_state.inventory = json.load(json_file)
        st.success("인벤토리 로드 완료!")
        
    if st.session_state.inventory:
        inv_json = json.dumps(st.session_state.inventory, ensure_ascii=False, indent=2)
        st.download_button("💾 현재 인벤토리 백업 (JSON)", data=inv_json, file_name="disk_data.json", mime="application/json")

    exclude_equipped = st.checkbox("타 캐릭터 장착 디스크 제외", value=True)
    
    st.subheader(f"보유 디스크 목록 (총 {len(st.session_state.inventory)}개)")
    if st.session_state.inventory:
        # 그리드 형태로 카드 출력
        cols = st.columns(4)
        for idx, d in enumerate(st.session_state.inventory):
            cols[idx % 4].markdown(render_disk_card(d), unsafe_allow_html=True)
            if cols[idx % 4].button("삭제", key=f"del_{idx}"):
                st.session_state.inventory.pop(idx)
                st.rerun()

with col_right:
    st.header("⚙️ ADEPTI SIMULATOR")
    
    char_list = list(st.session_state.char_db.keys())
    if not char_list:
        st.warning("CSV 파일을 로드해주세요.")
        st.stop()
        
    selected_char = st.selectbox("에이전트 선택", char_list)
    char_data = st.session_state.char_db[selected_char]
    
    # 캐릭별 가이드 박스 (원래 PyQt에서 note_box에 들어가던 내용)
    st.markdown(f"""
    <div style="background-color:#181A21; padding:15px; border:1px solid #2C2F36; border-radius:5px;">
        <b style='color:#00FFFF;'>[ {selected_char} 목표 스탯 ]</b><br>{char_data['target_str'].replace(chr(10), '<br>')}<br><br>
        <b style='color:#F4C20D;'>[ 가이드 노트 ]</b><br>{char_data['note'].replace(chr(10), '<br>')}
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🎯 목표 스탯 및 유효 부옵 설정")
    c1, c2 = st.columns(2)
    target_input = c1.text_area("목표 스탯 (직접 수정 가능)", value=char_data['target_str'])
    eff_input = c2.text_area("유효 부옵 (직접 수정 가능)", value=", ".join(char_data['eff_list']))
    
    st.markdown("### 🔧 엔진 및 코어 세팅")
    ec1, ec2, ec3, ec4 = st.columns(4)
    engine_atk = ec1.number_input("엔진 기초공", value=600)
    add_atk_p = ec2.number_input("추가 공(%)", value=0)
    add_ap = ec3.number_input("추가 이상마", value=0)
    add_cr = ec4.number_input("추가 치확(%)", value=0)
    
    st.markdown("### 🎲 세트 옵션 조건")
    sc1, sc2 = st.columns(2)
    s4_req = sc1.multiselect("요구 4세트", st.session_state.dynamic_sets, default=char_data['set4_opts'][:1] if char_data['set4_opts'] else None)
    s2_req = sc2.multiselect("요구 2세트", st.session_state.dynamic_sets, default=char_data['set2_opts'][:1] if char_data['set2_opts'] else None)

    if st.button("🚀 RUN HYBRID OPTIMIZATION", use_container_width=True, type="primary"):
        with st.spinner('가능한 모든 조합을 연산 중입니다...'):
            eff_list = extract_effective_subs(eff_input)
            target_stats = parse_target_stats_flat(target_input)
            
            candidates = []
            for i in range(1, 7):
                pool = [d for d in st.session_state.inventory if d["slot"] == i]
                if exclude_equipped:
                    pool = [d for d in pool if not d.get('owner') or d.get('owner') == selected_char]
                
                def disk_rv_score(d):
                    sc = 0.0
                    for s in d['subs']:
                        if s['name'].replace('이상 마스터리', '이상마') in eff_list: sc += (1 + int(s['upgrade']))
                    return sc
                candidates.append(sorted(pool, key=disk_rv_score, reverse=True)[:15])
            
            if any(not c for c in candidates):
                st.error("특정 슬롯의 디스크가 부족하여 조합을 계산할 수 없습니다.")
            else:
                max_eval, best_build, best_disk_stats, best_final_stats = -9999999.0, None, None, None
                
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
                            m2 = True; break
                            
                    base_rv = sum(calculate_adepti_score(d, eff_list) for d in combo)
                    score = base_rv * 100.0
                    if m4 and m2: score += 100000.0
                    elif m4: score += 50000.0
                    
                    disk_stats = {k: 0.0 for k in MAIN_VALUES.keys()}; disk_stats.update({k: 0.0 for k in SUB_ROLL_VALUES.keys()})
                    for d in combo:
                        m_type = d['main'].replace('이상 마스터리', '이상마')
                        if m_type in disk_stats: disk_stats[m_type] += MAIN_VALUES.get(m_type, 0)
                        for s in d['subs']:
                            sn = s['name'].replace('이상 마스터리', '이상마')
                            if sn in disk_stats: disk_stats[sn] += (1 + int(s['upgrade'])) * SUB_ROLL_VALUES.get(sn, 0)
                    
                    final_stats = {"공격력": (DEFAULT_BASE["atk"] + engine_atk) * ((100 + disk_stats["공격력%"] + add_atk_p) / 100) + disk_stats["공격력"], "치확": DEFAULT_BASE["crit_r"] + disk_stats["치확"] + add_cr, "치피": DEFAULT_BASE["crit_d"] + disk_stats["치피"], "이상마": DEFAULT_BASE["ap"] + disk_stats["이상마"] + add_ap}
                    
                    for t_name, t_val in target_stats.items():
                        c_val = final_stats.get(t_name, 0)
                        if c_val < t_val: score -= ((t_val - c_val) / t_val) ** 2 * 20000.0
                        else:
                            if t_name != "치확": score += ((c_val - t_val) / t_val) * 1000.0
                    if final_stats["치확"] > 100.0: score -= (final_stats["치확"] - 100.0) * 10.0
                    
                    if score > max_eval: max_eval, best_build, best_disk_stats, best_final_stats = score, combo, disk_stats, final_stats
                
                if best_build:
                    st.session_state.best_build = {"char": selected_char, "build": best_build}
                    st.success(f"최적화 완료! (점수: {int(max_eval%100000)})")
                    st.info(f"공격력: {int(best_final_stats['공격력'])} | 치확: {best_final_stats['치확']:.1f}% | 치피: {best_final_stats['치피']:.1f}% | 이상마: {int(best_final_stats['이상마'])}")
                    
                    # 결과 디스크 이미지 카드로 렌더링
                    r_cols = st.columns(3)
                    for idx, d in enumerate(best_build):
                        r_cols[idx%3].markdown(render_disk_card(d, is_result=True, eff_list=eff_list), unsafe_allow_html=True)
                else:
                    st.warning("조건을 만족하는 조합이 없습니다.")

    if st.session_state.best_build and st.session_state.best_build["char"] == selected_char:
        if st.button("✅ 이 조합 장착 (인벤토리 반영)", type="secondary"):
            char, build = st.session_state.best_build["char"], st.session_state.best_build["build"]
            for d in st.session_state.inventory:
                if d.get('owner') == char: d['owner'] = ""
            for d in build:
                for inv_d in st.session_state.inventory:
                    if inv_d == d: inv_d['owner'] = char
            st.session_state.best_build = None
            st.success(f"[{char}] 장착 완료! 백업하려면 왼쪽 아래 다운로드 버튼을 눌러.")
            st.rerun()
