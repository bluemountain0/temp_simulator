import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from conditions import ExposureCondition, OilCondition
from damage import DamageLevel, DamageVerdict, _THRESHOLDS, judge
from geometry import TubeGeometry
from thermal_solver import HybridFDSolver, RCSolver

# ─── 상수 ────────────────────────────────────────────────────────────────────
LEVEL_COLORS = {
    DamageLevel.SAFE:        ("#2ecc71", "✅ 안전"),
    DamageLevel.WARNING1:    ("#f39c12", "⚠️ 경고 1단계 (BTi-5 700°C)"),
    DamageLevel.DAMAGE1:     ("#e67e22", "🔴 손상 1단계 (BTi-5 고상선 840°C)"),
    DamageLevel.DAMAGE2:     ("#e74c3c", "🔴 손상 2단계 (BTi-5 액상선 880°C)"),
    DamageLevel.DAMAGE3:     ("#c0392b", "🔴 손상 3단계 (Cu 용융 1085°C)"),
    DamageLevel.DAMAGE4:     ("#922b21", "🔴 손상 4단계 (W 타겟 손상 2500°C)"),
    DamageLevel.FAILURE:     ("#1c2833", "💀 파국적 손상 (W 용융 3422°C)"),
    DamageLevel.OIL_WARNING: ("#2980b9", "🛢️ 오일 온도 경고 (100°C)"),
    DamageLevel.OIL_DANGER:  ("#1a5276", "🛢️ 오일 인화 위험 (150°C)"),
}

THRESHOLD_LINES = [
    (700,  "BTi-5 경고 700°C",   "#c5b0d5"),   # BTi5 연보라
    (840,  "BTi-5 고상선 840°C",  "#9467bd"),   # BTi5 보라
    (880,  "BTi-5 액상선 880°C",  "#6a3d9a"),   # BTi5 진보라
    (1085, "Cu 용융 1085°C",     "#2ca02c"),   # Cu_body 초록
    (2500, "W 손상4 2500°C",    "#d62728"),   # W surf 빨강
    (3422, "W 파국 3422°C",     "#8b0000"),   # W surf 다크레드
]

NODE_COLORS = ["#d62728", "#ff7f0e", "#9467bd", "#8c564b", "#2ca02c", "#1f77b4"]

# ─── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="X-ray 애노드 열손상 예측",
    page_icon="🔥",
    layout="wide",
)
st.title("🔥 X-ray 고정 애노드 열손상 예측 시뮬레이터")
st.caption("Phase 1.0b — HybridFD 솔버 (W 슬랩 1D-FD + RC 체인) | 허용 오차 ±30~50%")

# ─── 사이드바 ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")

    with st.expander("📡 조사 조건", expanded=True):
        mode = st.selectbox("조사 모드", ["DC 단발", "DC 사이클", "Pulse"])
        kV = st.number_input("관전압 [kV]", 10.0, 150.0, 100.0, 5.0)
        cur_type = st.radio("전류 입력", ["Peak", "Average"], horizontal=True)
        mA = st.number_input("관전류 [mA]", 0.1, 500.0, 12.0, 1.0)
        on_time = st.number_input("조사 시간 [s]", 0.001, 3600.0, 10.0, 1.0)

        if mode == "DC 사이클":
            off_time = st.number_input("휴지 시간 [s]", 0.0, 3600.0, 5.0, 1.0)
            cycles = int(st.number_input("사이클 수", 1, 100, 3, 1))
        else:
            off_time, cycles = 0.0, 1

        if mode == "Pulse":
            freq_hz = st.number_input("주파수 [Hz]", 0.1, 10000.0, 1000.0)
            duty = st.slider("듀티 사이클", 0.01, 1.0, 0.1, 0.01)
        else:
            freq_hz, duty = 0.0, 1.0

    with st.expander("🔍 포컬 스팟", expanded=False):
        L_eff = st.number_input("실효 길이 L_eff [mm]", 0.1, 10.0, 1.1, 0.1)
        W_eff = st.number_input("실효 폭 W_eff [mm]", 0.1, 10.0, 0.75, 0.05)

    with st.expander("🛢️ 냉각 조건", expanded=True):
        oil_vol = int(st.selectbox("절연유 부피 [L]", [25, 30], 0))
        ves_w = st.number_input("용기 가로 [cm]", 5.0, 200.0, 20.0, 1.0)
        ves_d = st.number_input("용기 세로 [cm]", 5.0, 200.0, 20.0, 1.0)
        conv = st.radio("대류", ["자연 (h=50 W/m²K)", "강제 (h=200 W/m²K)"], horizontal=False)
        h_oil = 50.0 if "자연" in conv else 200.0

    with st.expander("🧪 민감도", expanded=False):
        k_bti5 = int(st.selectbox("BTi-5 열전도율 [W/m·K]", [10, 20, 40], 1))
        use_hybrid = st.checkbox("HybridFD 솔버 사용 (권장)", value=True)

    st.divider()
    run_btn = st.button("▶ 실행", type="primary", use_container_width=True)
    val_btn = st.button("🧪 검증 케이스 (100kV·12mA·50s DC)", use_container_width=True)


# ─── 헬퍼 함수 ────────────────────────────────────────────────────────────────
def _make_exp(mode_str, kV_, mA_, cur_type_, on_, off_, cyc_, freq_, duty_):
    mode_map = {"DC 단발": "dc_single", "DC 사이클": "dc_cyclic", "Pulse": "pulse"}
    return ExposureCondition(
        mode=mode_map[mode_str], kV=kV_, mA_peak=mA_,
        on_time=on_, off_time=off_, cycles=cyc_,
        freq_hz=freq_, duty=duty_,
        current_input_type="peak" if cur_type_ == "Peak" else "average",
    )


def _make_oil(vol, vw, vd, h):
    return OilCondition(
        oil_volume_L=vol, vessel_w_cm=vw, vessel_d_cm=vd,
        h_oil=h, h_oil_air=10.0,
        convection_mode="natural" if h <= 50 else "forced",
    )


@st.cache_data
def run_sim(mode_, kV_, mA_, cur_type_, on_, off_, cyc_, freq_, duty_,
            L_, W_, vol_, vw_, vd_, h_, k_bti5_, use_hybrid_):
    exp = _make_exp(mode_, kV_, mA_, cur_type_, on_, off_, cyc_, freq_, duty_)
    oil = _make_oil(vol_, vw_, vd_, h_)
    geom = TubeGeometry(focal_L_eff_mm=L_, focal_W_eff_mm=W_)
    solver = HybridFDSolver() if use_hybrid_ else RCSolver()
    result = solver.solve(exp, geom, k_bti5=float(k_bti5_), oil_cond=oil)
    verdict = judge(result)
    return result, verdict


def _plot_temps(result):
    fig = go.Figure()
    for i, (name, color) in enumerate(zip(result.node_names, NODE_COLORS)):
        fig.add_trace(go.Scatter(
            x=result.t, y=result.T[i] - 273.15, name=name,
            line=dict(color=color),
        ))
    T_pk = result.T_w_surface_peak - 273.15
    if not np.allclose(T_pk, result.T[0] - 273.15, atol=0.5):
        fig.add_trace(go.Scatter(
            x=result.t, y=T_pk, name="W surf Peak (보정)",
            line=dict(color=NODE_COLORS[0], dash="dash"),
        ))
    fig.add_hline(
        y=result.ambient_K - 273.15, line_dash="dot", line_color="gray",
        annotation_text=f"Ambient {result.ambient_K-273.15:.0f}°C",
    )
    for thresh_C, label, color in THRESHOLD_LINES:
        fig.add_hline(
            y=thresh_C, line_dash="dash", line_color=color, line_width=0.8,
            annotation_text=label, annotation_position="right",
        )
    fig.update_layout(
        xaxis_title="시간 [s]", yaxis_title="온도 [°C]",
        title="노드 온도-시간 곡선", height=520,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _show_verdict(verdict: DamageVerdict):
    _, label = LEVEL_COLORS.get(verdict.level, ("gray", "?"))
    c1, c2, c3 = st.columns(3)
    c1.metric("손상 판정", label)
    c2.metric("최초 손상 부위", verdict.first_failed_node)
    c3.metric(
        "손상 도달 시각",
        f"{verdict.time_to_damage_s:.3f} s" if verdict.time_to_damage_s is not None else "없음",
    )
    if verdict.reasons:
        st.subheader("판정 근거")
        for r in verdict.reasons:
            st.warning(r)
    st.subheader("최고 온도 요약")
    st.dataframe(
        pd.DataFrame({
            "노드": list(verdict.max_temps.keys()),
            "최고 온도 [°C]": [f"{v:.1f}" for v in verdict.max_temps.values()],
        }),
        hide_index=True, use_container_width=True,
    )


def _make_csv(result) -> str:
    data: dict = {"시간[s]": result.t}
    for i, name in enumerate(result.node_names):
        data[f"{name}[°C]"] = result.T[i] - 273.15
    data["W_peak[°C]"] = result.T_w_surface_peak - 273.15

    T_series_K = {
        "W surface": result.T_w_surface_peak,
        "W bulk":    result.T[1],
        "BTi5":      result.T[2],
        "Cu top":    result.T[3],
        "Cu body":   result.T[4],
        "Oil":       result.T[5],
    }
    lv = np.zeros(len(result.t), dtype=int)
    for lvl_val, node, thresh_K in sorted(_THRESHOLDS, key=lambda x: x[0]):
        mask = T_series_K[node] >= thresh_K
        lv[mask] = np.maximum(lv[mask], int(lvl_val))
    data["손상_레벨"] = lv

    return pd.DataFrame(data).to_csv(index=False, encoding="utf-8-sig")


def _validity_warn(on_time_s: float, mode_str: str):
    t = on_time_s
    if mode_str == "Pulse":
        return  # pulse는 별도 경고 없음 (duty cycle로 on_time 다름)
    if t < 8.6e-3:
        st.info("ℹ️ t_on < 8.6 ms: 1D 열확산 지배 구간. 정확도 ±30~50%.")
    elif t < 0.1:
        st.warning("⚠️ 8.6 ms < t_on < 100 ms: 횡방향 확산 시작 경계. 정확도 ±50~100%.")
    else:
        st.warning("⚠️ t_on > 100 ms: 횡방향 포화 구간. RC/FD 모델 한계. 정확도 ±50~100%.")


# ─── 실행 로직 ─────────────────────────────────────────────────────────────────
_args = None
if run_btn:
    _args = (mode, kV, mA, cur_type, on_time, off_time, cycles, freq_hz, duty,
             L_eff, W_eff, oil_vol, ves_w, ves_d, h_oil, k_bti5, use_hybrid)
elif val_btn:
    _args = ("DC 단발", 100.0, 12.0, "Peak", 50.0, 0.0, 1, 0.0, 1.0,
             1.1, 0.75, 30, 20.0, 20.0, 50.0, 20, True)

result = None
verdict = None

if _args is not None:
    with st.spinner("계산 중..."):
        try:
            result, verdict = run_sim(*_args)
            st.success(f"완료 — {len(result.t)} 타임스텝")
        except ValueError as e:
            st.error(f"입력 오류: {e}")
        except Exception as e:
            st.error(f"계산 오류: {e}")

# ─── 결과 탭 ──────────────────────────────────────────────────────────────────
if result is not None and verdict is not None:
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📈 온도 그래프", "🔴 손상 판정", "📥 데이터 내보내기", "🧪 검증 케이스"]
    )

    with tab1:
        _validity_warn(_args[4], _args[0])
        st.plotly_chart(_plot_temps(result), use_container_width=True)

    with tab2:
        _show_verdict(verdict)

    with tab3:
        csv_str = _make_csv(result)
        st.download_button(
            "📥 CSV 다운로드", csv_str, "anode_sim.csv", "text/csv",
        )
        st.dataframe(
            pd.read_csv(pd.io.common.StringIO(csv_str)).head(20),
            use_container_width=True,
        )

    with tab4:
        st.subheader("🧪 검증 케이스: 100 kV · 12 mA · 50 s DC")
        st.markdown(
            "**조건:** TubeGeometry 기본값, BTi-5 k=20 W/m·K, 자연대류 h=50 W/m²K  \n"
            "**기대:** W 표면 온도 > 2500°C → DAMAGE4 이상  \n"
            "**모델 신뢰도:** ±50~100% (t_on=50s DC, 횡방향 포화 구간)"
        )
        v_res, v_verd = run_sim(
            "DC 단발", 100.0, 12.0, "Peak", 50.0, 0.0, 1, 0.0, 1.0,
            1.1, 0.75, 30, 20.0, 20.0, 50.0, 20, True,
        )
        _, lvl_label = LEVEL_COLORS[v_verd.level]
        c1, c2, c3 = st.columns(3)
        c1.metric("판정 결과", lvl_label)
        c2.metric("W 표면 최고 온도", f"{v_verd.max_temps.get('W surface', 0):.0f} °C")
        passed = v_verd.level >= DamageLevel.DAMAGE4
        c3.metric("검증", "통과 ✅" if passed else "실패 ❌")
        if passed:
            st.success("검증 통과: DAMAGE4 이상 판정")
        else:
            st.error(f"검증 실패: {v_verd.level.name} (기대: DAMAGE4 이상)")

else:
    st.info("← 사이드바에서 조건을 입력하고 '▶ 실행' 버튼을 클릭하세요.")
