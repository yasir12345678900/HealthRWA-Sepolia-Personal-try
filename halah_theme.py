import streamlit as st

CSS = """
<style>
:root{--navy:#0d3b4f;--navy3:#092a3a;--ink:#071e29;--teal:#2ec4b6;--green:#39d98a;--orange:#E07B1F;--gold:#F5C542;--text:#eaf6f6;--muted:#9fc4cf;}
.main-title,.subtitle,.info-panel{display:none!important}
.stApp{background:radial-gradient(900px 500px at 12% -10%,rgba(46,196,182,.16),transparent 60%),radial-gradient(800px 460px at 105% 115%,rgba(224,123,31,.10),transparent 55%),linear-gradient(160deg,#0d3b4f 0%,#0a3140 55%,#092a3a 100%);background-size:160% 160%,160% 160%,100% 100%;animation:bgDrift 22s ease-in-out infinite alternate;color:var(--text);}
@keyframes bgDrift{0%{background-position:0% 0%,100% 100%,0 0}100%{background-position:40% 20%,60% 70%,0 0}}
@keyframes fadeInUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes shimmer{0%{background-position:0% 50%}100%{background-position:300% 50%}}
@keyframes floatGlow{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(30px,-18px) scale(1.12)}}
@keyframes pulseGlow{0%,100%{box-shadow:0 0 0 0 rgba(46,196,182,.35)}50%{box-shadow:0 0 22px 4px rgba(46,196,182,.25)}}
@keyframes growBar{from{width:0;opacity:0}to{width:64px;opacity:1}}
.halah-hero{position:relative;overflow:hidden;background:linear-gradient(135deg,#0e4258 0%,#0a3140 60%,#092a3a 100%);border:1px solid rgba(46,196,182,.35);border-radius:18px;padding:34px 38px 30px;margin:6px 0 26px;box-shadow:0 14px 40px rgba(0,0,0,.35);animation:fadeInUp .6s ease both;}
.halah-hero::before{content:"";position:absolute;width:420px;height:420px;right:-120px;top:-160px;background:radial-gradient(circle,rgba(46,196,182,.28),transparent 62%);animation:floatGlow 9s ease-in-out infinite;}
.halah-hero::after{content:"";position:absolute;left:0;top:0;right:0;height:5px;background:linear-gradient(90deg,#2ec4b6,#39d98a,#F5C542,#E07B1F,#2ec4b6);background-size:300% 100%;animation:shimmer 6s linear infinite;}
.halah-title{font-size:3.2rem;font-weight:700;letter-spacing:6px;line-height:1.1;background:linear-gradient(90deg,#eaf6f6 0%,#2ec4b6 45%,#39d98a 75%,#F5C542 100%);-webkit-background-clip:text;background-clip:text;color:transparent;animation:fadeInUp .7s ease both;}
.halah-tag{margin-top:10px;color:var(--teal);font-weight:700;text-transform:uppercase;letter-spacing:3.5px;font-size:.95rem;animation:fadeInUp .7s ease .15s both;}
.halah-sub{margin-top:6px;color:var(--muted);font-size:1.02rem;animation:fadeInUp .7s ease .3s both;}
.halah-chips{margin-top:18px;display:flex;gap:12px;flex-wrap:wrap;animation:fadeInUp .7s ease .45s both;}
.chip{font-family:'Courier New',monospace;font-size:.95rem;font-weight:600;padding:8px 16px;border-radius:999px;transition:transform .25s ease;display:inline-block;}
.chip:hover{transform:translateY(-2px)}
.chip-gold{color:#F5C542;border:1.5px solid rgba(245,197,66,.65);background:rgba(245,197,66,.08);}
.chip-teal{color:#bff5ef;border:1.5px solid rgba(46,196,182,.65);background:rgba(46,196,182,.10);animation:pulseGlow 3.6s ease-in-out infinite;}
.chip-ver{color:var(--muted);border:1px dashed rgba(159,196,207,.5);background:rgba(159,196,207,.06);font-size:.8rem;}
section[data-testid="stMain"] h2,section[data-testid="stMain"] h3{color:var(--text)!important;letter-spacing:.4px;position:relative;padding-bottom:10px;}
section[data-testid="stMain"] h2::after,section[data-testid="stMain"] h3::after{content:"";position:absolute;left:0;bottom:0;height:4px;width:64px;border-radius:4px;background:linear-gradient(90deg,#2ec4b6,#F5C542);animation:growBar .8s ease .2s both;}
section[data-testid="stMain"] [data-testid="stMarkdownContainer"] p{color:var(--text);}
[data-testid="stMetric"]{background:linear-gradient(160deg,rgba(14,66,88,.92),rgba(9,42,58,.92));border:1px solid rgba(46,196,182,.28);border-radius:14px;padding:14px 16px;transition:transform .25s ease,box-shadow .25s ease;}
[data-testid="stMetric"]:hover{transform:translateY(-3px);box-shadow:0 10px 26px rgba(0,0,0,.35);}
[data-testid="stMetricValue"]{color:#F5C542!important;font-weight:800;}
[data-testid="stMetricLabel"]{color:var(--muted)!important;}
section[data-testid="stMain"] .stButton>button{background:linear-gradient(90deg,#2ec4b6 0%,#39d98a 100%)!important;color:#06222e!important;font-weight:800!important;border:none!important;border-radius:12px!important;padding:12px 26px!important;width:100%;box-shadow:0 8px 20px rgba(46,196,182,.28)!important;transition:all .28s cubic-bezier(.2,.8,.2,1)!important;}
section[data-testid="stMain"] .stButton>button:hover{background:linear-gradient(90deg,#E07B1F 0%,#F5C542 100%)!important;transform:translateY(-2px) scale(1.01);box-shadow:0 12px 26px rgba(224,123,31,.38)!important;}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{color:var(--text)!important;}
[data-testid="stTextInput"]>div,[data-testid="stTextArea"]>div,[data-baseweb="select"]>div{background:#092a3a!important;border-radius:10px!important;border:1px solid rgba(46,196,182,.25)!important;}
[data-testid="stTextInput"]>div:focus-within,[data-baseweb="select"]>div:focus-within{border-color:#2ec4b6!important;box-shadow:0 0 0 3px rgba(46,196,182,.22)!important;}
[data-testid="stWidgetLabel"] p{color:#bfe3e0!important;font-weight:600;}
[data-baseweb="select"] div{color:var(--text)!important;}
[data-baseweb="popover"] ul{background:#092a3a!important;}
[data-baseweb="popover"] li{color:var(--text)!important;}
[data-baseweb="tag"]{background:rgba(46,196,182,.18)!important;border:1px solid rgba(46,196,182,.5)!important;}
[data-baseweb="tag"] span{color:#bff5ef!important;}
[data-testid="stAlert"]{border-radius:12px!important;border:1px solid rgba(46,196,182,.25);background:rgba(10,49,64,.85)!important;animation:fadeInUp .45s ease both;}
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]){border-left:5px solid #39d98a!important;}
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]){border-left:5px solid #2ec4b6!important;}
div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]){border-left:5px solid #ff6b6b!important;}
[data-testid="stAlert"] p{color:var(--text)!important;}
[data-testid="stCode"] pre,.blockchain-badge{background:#071e29!important;color:#2ec4b6!important;border-left:4px solid #F5C542!important;border-radius:10px!important;animation:pulseGlow 4.5s ease-in-out infinite;}
[data-testid="stJson"]{background:#071e29!important;border-radius:10px;padding:6px;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0a3140 0%,#092a3a 100%)!important;border-right:1px solid rgba(46,196,182,.25);}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{color:#2ec4b6!important;letter-spacing:1.5px;text-transform:uppercase;font-size:.8rem;}
[data-testid="stAppDeployButton"]{display:none;}
header[data-testid="stHeader"]{background:transparent!important;}
</style>
"""

HERO = """
<div class="halah-hero">
  <div class="halah-title">HALAH</div>
  <div class="halah-tag">History Access Link for Authorised Healthcare</div>
  <div class="halah-sub">HealthRWA - Trusted Multi-Party Patient Consent on Blockchain</div>
  <div class="halah-chips">
    <span class="chip chip-gold">C = (I, A, P, E)</span>
    <span class="chip chip-teal">ALLOW = VI + VA + VP</span>
    <span class="chip chip-ver">Version 1</span>
  </div>
</div>
"""

def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(HERO, unsafe_allow_html=True)
