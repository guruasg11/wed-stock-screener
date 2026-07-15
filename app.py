"""
NSE EOD Tracker - Clean rewrite
All bugs fixed:
- Sector tracker now uses yf.download() batch (not one-by-one loop)
- No session objects passed to cached functions (not picklable)
- No time.sleep() in main thread
- No packages.txt needed (curl_cffi wheels are self-contained)
- fetch_ticker loop on rerun eliminated - batch cached as one unit per sector
"""

from datetime import date
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="NSE EOD Tracker", layout="wide", page_icon="📈")

st.markdown("""
<style>
  .block-container{padding-top:.6rem;padding-bottom:.6rem}
  .metric-card{
    background:#111827;border:1px solid #374151;border-radius:10px;
    padding:14px 8px;text-align:center;margin-bottom:4px;
  }
  .metric-card .num{font-size:1.75rem;font-weight:700;line-height:1.1}
  .metric-card .lbl{font-size:.7rem;color:#9ca3af;margin-top:3px;letter-spacing:.3px}
  .g{color:#22c55e} .r{color:#ef4444} .w{color:#f3f4f6}
</style>
""", unsafe_allow_html=True)

# ── SECTOR DATA ───────────────────────────────────────────────────────────────
SECTORS = {
    "My Watchlist":    ["ASTRAL","TATAMOTORS","BANKBARODA","PFC","RECLTD","HUDCO","RVNL","GODREJIND"],
    "Nifty 50":        ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","BHARTIARTL","ITC","LT",
                        "HINDUNILVR","SBIN","BAJFINANCE","KOTAKBANK","AXISBANK","ASIANPAINT",
                        "MARUTI","HCLTECH","SUNPHARMA","TITAN","WIPRO","ONGC","NTPC","POWERGRID",
                        "ULTRACEMCO","NESTLEIND","TECHM","INDUSINDBK","ADANIENT","ADANIPORTS",
                        "BAJAJFINSV","DRREDDY","DIVISLAB","CIPLA","BPCL","COALINDIA","HEROMOTOCO",
                        "M&M","TATASTEEL","JSWSTEEL","EICHERMOT","GRASIM"],
    "Nifty Bank":      ["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK","PNB","INDUSINDBK",
                        "BANDHANBNK","FEDERALBNK","IDFCFIRSTB","AUBANK","BANKBARODA"],
    "Nifty IT":        ["TCS","INFY","HCLTECH","WIPRO","TECHM","LTIM","PERSISTENT","MPHASIS","COFORGE","OFSS"],
    "Nifty Auto":      ["MARUTI","TATAMOTORS","M&M","BAJAJ-AUTO","HEROMOTOCO","EICHERMOT",
                        "BOSCHLTD","MRF","BALKRISIND","MOTHERSON","BHARATFORG","APOLLOTYRE"],
    "Nifty FMCG":      ["HINDUNILVR","ITC","NESTLEIND","BRITANNIA","DABUR","MARICO",
                        "COLPAL","GODREJCP","EMAMILTD","TATACONSUM","UBL","MCDOWELL-N"],
    "Nifty Pharma":    ["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB","APOLLOHOSP","TORNTPHARM",
                        "ALKEM","AUROPHARMA","LUPIN","BIOCON","IPCALAB","GLENMARK"],
    "Nifty Metal":     ["TATASTEEL","JSWSTEEL","HINDALCO","COALINDIA","VEDL","SAIL",
                        "NMDC","APLAPOLLO","NATIONALUM","HINDCOPPER","MOIL","WELCORP"],
    "Nifty Realty":    ["DLF","GODREJPROP","OBEROIRLTY","PHOENIXLTD","PRESTIGE",
                        "BRIGADE","SOBHA","SUNTECK","KOLTEPATIL","MAHLIFE"],
    "Nifty Energy":    ["RELIANCE","ONGC","NTPC","POWERGRID","BPCL","IOC","GAIL",
                        "TATAPOWER","ADANIGREEN","ADANIPOWER","CESC"],
    "Nifty Infra":     ["LT","ADANIPORTS","POWERGRID","NTPC","BHARTIARTL","RVNL","IRFC",
                        "PFC","RECLTD","HUDCO","NBCC","IRB"],
    "Nifty PSU Bank":  ["SBIN","PNB","BANKBARODA","CANARABANK","UNIONBANK","BANKINDIA",
                        "CENTRALBK","UCOBANK","MAHABANK","INDIANB"],
    "Nifty Midcap":    ["PERSISTENT","POLYCAB","FEDERALBNK","LTTS","MPHASIS","COFORGE",
                        "ABCAPITAL","SUNDARMFIN","VOLTAS","ASTRAL","PIIND","ZYDUSLIFE",
                        "MAXHEALTH","CAMS","ANGELONE","BSE","MCX","DIXON","AMBER","TRENT"],
    "Nifty Fin Svcs":  ["HDFCBANK","ICICIBANK","BAJFINANCE","KOTAKBANK","AXISBANK","SBIN",
                        "BAJAJFINSV","HDFCAMC","MUTHOOTFIN","CHOLAFIN","M&MFIN","LICHSGFIN"],
    "Nifty Oil & Gas": ["RELIANCE","ONGC","BPCL","IOC","GAIL","HINDPETRO",
                        "MGL","IGL","PETRONET","GSPL","CASTROLIND"],
    "Custom Basket":   [],
}

SECTOR_INDEX = {
    "Nifty 50":       "^NSEI",
    "Nifty Bank":     "^NSEBANK",
    "Nifty IT":       "^CNXIT",
    "Nifty Auto":     "^CNXAUTO",
    "Nifty FMCG":     "^CNXFMCG",
    "Nifty Pharma":   "^CNXPHARMA",
    "Nifty Metal":    "^CNXMETAL",
    "Nifty Realty":   "^CNXREALTY",
    "Nifty Energy":   "^CNXENERGY",
    "Nifty Infra":    "^CNXINFRA",
    "Nifty PSU Bank": "^CNXPSUBANK",
    "Nifty Fin Svcs": "^CNXFIN",
    "Nifty Oil & Gas":"^CNXOILGAS",
}

AD_UNIVERSE = list(dict.fromkeys([
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","BHARTIARTL","ITC","LT",
    "HINDUNILVR","SBIN","BAJFINANCE","KOTAKBANK","AXISBANK","ASIANPAINT",
    "MARUTI","HCLTECH","SUNPHARMA","TITAN","WIPRO","ONGC","NTPC","POWERGRID",
    "ULTRACEMCO","NESTLEIND","TECHM","INDUSINDBK","ADANIENT","ADANIPORTS",
    "BAJAJFINSV","DRREDDY","DIVISLAB","CIPLA","BPCL","COALINDIA","HEROMOTOCO",
    "M&M","TATASTEEL","JSWSTEEL","EICHERMOT","GRASIM",
    "DMART","SIEMENS","HAVELLS","PIDILITIND","DABUR","MARICO","COLPAL",
    "GODREJCP","TATACONSUM","BRITANNIA","MUTHOOTFIN","CHOLAFIN",
    "SHREECEM","BERGEPAINT","TORNTPHARM","LUPIN","BIOCON","ALKEM","AUROPHARMA",
    "AMBUJACEM","GAIL","HINDPETRO","IOC","PETRONET","MGL","IGL",
    "DLF","GODREJPROP","OBEROIRLTY","PHOENIXLTD","PRESTIGE",
    "APOLLOHOSP","MAXHEALTH","FORTIS","LALPATHLAB",
    "PERSISTENT","POLYCAB","LTTS","MPHASIS","COFORGE","ZYDUSLIFE",
    "CAMS","ANGELONE","BSE","MCX","VOLTAS","ASTRAL","PIIND",
    "ABCAPITAL","SUNDARMFIN","FEDERALBNK","IDFCFIRSTB","AUBANK","BANDHANBNK",
    "PNB","BANKBARODA","CANARABANK","UNIONBANK","BANKINDIA","CENTRALBK","INDIANB",
    "TATAMOTORS","PFC","RECLTD","HUDCO","RVNL","IRFC","RAILTEL","IRCON",
    "RITES","NBCC","HFCL","SUZLON","NHPC","SJVN","TATAPOWER",
    "ADANIGREEN","ADANIPOWER","CESC","JSWENERGY","TORNTPOWER",
    "BAJAJ-AUTO","BOSCHLTD","MRF","BALKRISIND","MOTHERSON","BHARATFORG","APOLLOTYRE",
    "VEDL","NMDC","APLAPOLLO","NATIONALUM","HINDCOPPER","MOIL","SAIL","HINDALCO",
    "HDFCAMC","HDFCLIFE","SBILIFE","M&MFIN","LICHSGFIN",
    "DIXON","AMBER","WHIRLPOOL","BLUESTAR","CROMPTON","VGUARD",
    "ZOMATO","NYKAA","DELHIVERY","TRENT","RAYMOND","VEDANT","ABFRL",
    "UPL","COROMANDEL","CHAMBLFERT","DEEPAKNTR",
    "OFSS","KPITTECH","TATAELXSI","HAPPYMNDS","MASTEK","LTIM",
    "VARUNBEV","RADICO","UBL","MCDOWELL-N",
    "JUBLFOOD","DEVYANI","KAJARIACER","GRINDWELL",
    "GODREJIND","EMAMILTD","IPCALAB","GLENMARK","BRIGADE","SOBHA",
    "IRB","GSPL","WELCORP","MAHLIFE","SUNTECK","KOLTEPATIL",
]))


# ── HELPERS ───────────────────────────────────────────────────────────────────
def add_ns(sym):
    return f"{sym.strip().upper().replace('.NS','')}.NS"

def drop_today(df):
    if df.empty: return df
    df.index = pd.to_datetime(df.index)
    if str(df.index[-1].date()) == date.today().isoformat():
        df = df.iloc[:-1]
    return df

def cell_bg(val, cap=20):
    if pd.isna(val): return ""
    try: val = float(val)
    except: return ""
    i = min(abs(val)/cap, 1.0)
    if val >= 0:
        r,g,b = int(255-i*195), int(255-i*55),  int(255-i*195)
    else:
        r,g,b = int(255-i*35),  int(255-i*205), int(255-i*205)
    return f"background-color:rgb({r},{g},{b});color:#000;font-weight:600;"

def style_table(df, pct_cols, cap=20):
    cols = [c for c in pct_cols if c in df.columns]
    num  = [c for c in df.columns if c != "Symbol"]
    fmt  = {c:"{:.2f}" for c in num}
    s    = df.style.format(fmt, na_rep="—")
    fn   = s.map if hasattr(s,"map") else s.applymap
    return fn(lambda v: cell_bg(v, cap), subset=cols)


# ── BATCH DOWNLOAD (used for BOTH pages) ──────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=86400)
def batch_download(symbols_tuple: tuple) -> pd.DataFrame:
    """
    One HTTP round-trip for all tickers via yf.download().
    Cached by the frozenset of symbols - won't re-fetch for 24h.
    No session arg = no pickling issue.
    """
    yf_syms = [add_ns(s) for s in symbols_tuple]
    try:
        raw = yf.download(
            tickers=yf_syms,
            period="1y",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
            multi_level_index=True,
        )
    except Exception:
        return pd.DataFrame()
    return drop_today(raw)


@st.cache_data(show_spinner=False, ttl=86400)
def fetch_index(symbol: str) -> dict:
    """Single index ticker fetch - these are not in batch."""
    try:
        raw = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True)
    except Exception as e:
        return {"Symbol": symbol, "Error": str(e)}
    raw = drop_today(raw)
    if raw.empty or len(raw) < 5:
        return {"Symbol": symbol, "Error": "No data"}
    return _calc(raw, symbol, symbol)


# ── CALCULATION ───────────────────────────────────────────────────────────────
def _calc(raw, sym_label, original_sym):
    """Compute all metrics from a single-ticker OHLCV dataframe."""
    close = raw["Close"].astype(float)
    high  = raw["High"].astype(float)
    low   = raw["Low"].astype(float)

    if len(close) < 5:
        return {"Symbol": sym_label, "Error": "Insufficient data"}

    ltp = float(close.iloc[-1])

    def ret(n):
        if len(close) <= n: return np.nan
        p = float(close.iloc[-(n+1)])
        return round(((ltp-p)/p)*100, 2) if p else np.nan

    def ema(span):
        return round(float(close.ewm(span=span, adjust=False).mean().iloc[-1]), 2)

    h52 = round(float(high.max()), 2)
    l52 = round(float(low.min()),  2)

    return {
        "Symbol":    sym_label,
        "LTP":       round(ltp, 2),
        "1D %":      ret(1),
        "3D %":      ret(3),
        "1W %":      ret(5),
        "2W %":      ret(10),
        "1M %":      ret(21),
        "2M %":      ret(42),
        "3M %":      ret(63),
        "6M %":      ret(126),
        "1Y %":      ret(251),
        "4 EMA":     ema(4),
        "10 EMA":    ema(10),
        "20 EMA":    ema(20),
        "50 EMA":    ema(50),
        "100 EMA":   ema(100),
        "52W High":  h52,
        "vs 52WH%":  round(((ltp-h52)/h52)*100, 2),
        "52W Low":   l52,
        "vs 52WL%":  round(((ltp-l52)/l52)*100, 2),
        "Error":     None,
    }


def extract_from_batch(raw: pd.DataFrame, sym: str) -> dict:
    """Pull one ticker's data out of a batch-downloaded MultiIndex DataFrame."""
    yf_sym = add_ns(sym)
    try:
        if isinstance(raw.columns, pd.MultiIndex):
            sub = pd.DataFrame({
                "Close": raw["Close"][yf_sym],
                "High":  raw["High"][yf_sym],
                "Low":   raw["Low"][yf_sym],
            }).dropna()
        else:
            sub = raw[["Close","High","Low"]].dropna()

        if len(sub) < 5:
            return {"Symbol": sym, "Error": "No data"}
        return _calc(sub, sym, sym)
    except Exception as e:
        return {"Symbol": sym, "Error": str(e)}


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
if "custom_stocks" not in st.session_state:
    st.session_state.custom_stocks = []

st.sidebar.title("📈 NSE EOD Tracker")
page = st.sidebar.radio("View", ["📊 Sector Tracker", "📉 Advance / Decline"],
                         label_visibility="collapsed")

PCT_COLS = ["1D %","3D %","1W %","2W %","1M %","2M %","3M %","6M %","1Y %",
            "vs 52WH%","vs 52WL%"]


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 1 – SECTOR TRACKER
# ═════════════════════════════════════════════════════════════════════════════
if page == "📊 Sector Tracker":
    st.header("📊 Sector Tracker")

    sector_names = [s for s in SECTORS if s != "Custom Basket"] + ["Custom Basket"]
    sel_sector   = st.sidebar.selectbox("Sector / Basket", sector_names)
    def_stocks   = SECTORS.get(sel_sector, [])

    all_opts   = sorted(set(def_stocks + st.session_state.custom_stocks))
    ms_default = st.session_state.custom_stocks if sel_sector == "Custom Basket" else def_stocks

    sel_stocks = st.sidebar.multiselect("Stocks", options=all_opts, default=ms_default)

    inp = st.sidebar.text_input("Add stock (e.g. ZOMATO)").upper().strip()
    ca, cb = st.sidebar.columns(2)
    with ca:
        if st.button("➕ Add") and inp:
            if inp not in st.session_state.custom_stocks:
                st.session_state.custom_stocks.append(inp)
                st.rerun()
    with cb:
        if st.button("🗑 Clear"):
            st.session_state.custom_stocks = []
            st.rerun()

    final = list(dict.fromkeys(sel_stocks + st.session_state.custom_stocks))
    if not final:
        st.info("Select stocks from the sidebar.")
        st.stop()

    # ── Single batch download for ALL stocks in this sector ──────────────────
    with st.spinner(f"Loading {sel_sector} data…"):
        raw = batch_download(tuple(sorted(final)))   # sorted so cache key is stable

    if raw.empty:
        st.error("Could not fetch data from Yahoo Finance. Please try again in a moment.")
        st.stop()

    # ── Parse each stock from batch ──────────────────────────────────────────
    results, errors = [], []
    for sym in final:
        d = extract_from_batch(raw, sym)
        if d.get("Error"):
            errors.append(f"**{sym}**: {d['Error']}")
        else:
            d.pop("Error", None)
            results.append(d)

    if errors:
        with st.expander(f"⚠️ {len(errors)} ticker(s) had no data"):
            for e in errors: st.write(e)

    if not results:
        st.warning("No data could be parsed. Check your ticker symbols.")
        st.stop()

    df = pd.DataFrame(results)

    # ── Sector index row ──────────────────────────────────────────────────────
    idx_row = None
    idx_sym = SECTOR_INDEX.get(sel_sector)
    if idx_sym:
        with st.spinner("Fetching index…"):
            d = fetch_index(idx_sym)
        if not d.get("Error"):
            d.pop("Error", None)
            d["Symbol"] = f"▶ {sel_sector} INDEX"
            idx_row = d

    # ── Average summary row ───────────────────────────────────────────────────
    num_cols = [c for c in df.columns if c != "Symbol"]
    avg = {"Symbol": f"📊 {sel_sector} AVG"}
    avg.update(df[num_cols].mean(numeric_only=True).round(2).to_dict())

    frames = []
    if idx_row: frames.append(pd.DataFrame([idx_row]))
    frames.append(pd.DataFrame([avg]))
    frames.append(df)
    df_all = pd.concat(frames, ignore_index=True)

    st.caption(f"{sel_sector} · {len(final)} stocks  |  🟢 positive  🔴 negative  |  EOD data, cached 24 h")
    st.dataframe(style_table(df_all, PCT_COLS), use_container_width=True, height=600)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 2 – ADVANCE / DECLINE
# ═════════════════════════════════════════════════════════════════════════════
else:
    st.header("📉 Market Advance / Decline")
    st.caption(f"Universe: {len(AD_UNIVERSE)} NSE stocks (market cap ≥ ₹1000 Cr)")

    col_btn, col_note = st.columns([1, 4])
    with col_btn:
        refresh = st.button("🔄 Refresh")
    with col_note:
        st.caption("Data cached for 1 hour. First load takes ~30 sec.")

    if refresh:
        # Clear the specific cache entry so it re-fetches
        batch_download.clear()
        st.session_state.pop("ad_df", None)

    if "ad_df" not in st.session_state:
        with st.spinner("Downloading market breadth data… (~30 seconds)"):
            raw_ad = batch_download(tuple(sorted(AD_UNIVERSE)))
        if raw_ad.empty:
            st.error("Could not fetch market data. Try refreshing.")
            st.stop()

        rows = []
        for sym in AD_UNIVERSE:
            yf_sym = add_ns(sym)
            try:
                if isinstance(raw_ad.columns, pd.MultiIndex):
                    close_s = raw_ad["Close"][yf_sym].dropna()
                    high_s  = raw_ad["High"][yf_sym].dropna()
                    low_s   = raw_ad["Low"][yf_sym].dropna()
                else:
                    close_s = raw_ad["Close"].dropna()
                    high_s  = raw_ad["High"].dropna()
                    low_s   = raw_ad["Low"].dropna()

                if len(close_s) < 10: continue

                ltp  = float(close_s.iloc[-1])
                prev = float(close_s.iloc[-2])

                def ema(span, s=close_s):
                    return float(s.ewm(span=span, adjust=False).mean().iloc[-1])

                e4,e10,e20,e50,e100 = ema(4),ema(10),ema(20),ema(50),ema(100)
                h52 = float(high_s.max())
                l52 = float(low_s.min())

                rows.append({
                    "Symbol":    sym,
                    "LTP":       round(ltp,2),
                    "Day Chg%":  round(((ltp-prev)/prev)*100,2),
                    ">4EMA":     "✅" if ltp>e4   else "❌",
                    "4 EMA":     round(e4,2),
                    ">10EMA":    "✅" if ltp>e10  else "❌",
                    "10 EMA":    round(e10,2),
                    ">20EMA":    "✅" if ltp>e20  else "❌",
                    "20 EMA":    round(e20,2),
                    ">50EMA":    "✅" if ltp>e50  else "❌",
                    "50 EMA":    round(e50,2),
                    ">100EMA":   "✅" if ltp>e100 else "❌",
                    "100 EMA":   round(e100,2),
                    "vs 52WH%":  round(((ltp-h52)/h52)*100,2),
                    "vs 52WL%":  round(((ltp-l52)/l52)*100,2),
                    "52W High":  round(h52,2),
                    "52W Low":   round(l52,2),
                })
            except Exception:
                continue

        st.session_state.ad_df = pd.DataFrame(rows)

    df_ad = st.session_state.ad_df
    if df_ad.empty:
        st.warning("No data available.")
        st.stop()

    total = len(df_ad)

    # ── Summary cards ─────────────────────────────────────────────────────────
    adv  = int((df_ad["Day Chg%"] > 0).sum())
    dec  = int((df_ad["Day Chg%"] < 0).sum())
    unch = total - adv - dec

    a4   = int((df_ad[">4EMA"]  =="✅").sum())
    a10  = int((df_ad[">10EMA"] =="✅").sum())
    a20  = int((df_ad[">20EMA"] =="✅").sum())
    a50  = int((df_ad[">50EMA"] =="✅").sum())
    a100 = int((df_ad[">100EMA"]=="✅").sum())

    at52h   = int((df_ad["vs 52WH%"] >= 0).sum())
    near52h = int((df_ad["vs 52WH%"] >= -5).sum())
    near52l = int((df_ad["vs 52WL%"] <= 10).sum())
    at52l   = int((df_ad["vs 52WL%"] <= 5).sum())

    def card(num, lbl, color):
        return (f'<div class="metric-card">'
                f'<div class="num {color}">{num}</div>'
                f'<div class="lbl">{lbl}</div>'
                f'</div>')

    st.markdown("#### Today's Breadth")
    c = st.columns(4)
    c[0].markdown(card(adv,   "Advancing",     "g"), unsafe_allow_html=True)
    c[1].markdown(card(dec,   "Declining",     "r"), unsafe_allow_html=True)
    c[2].markdown(card(unch,  "Unchanged",     "w"), unsafe_allow_html=True)
    c[3].markdown(card(total, "Total Tracked", "w"), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Stocks Above EMA")
    c = st.columns(5)
    for col, ab, lbl in zip(c,
                             [a4, a10, a20, a50, a100],
                             ["4 EMA","10 EMA","20 EMA","50 EMA","100 EMA"]):
        pct = round(ab/total*100,1) if total else 0
        clr = "g" if ab >= total/2 else "r"
        col.markdown(
            f'<div class="metric-card">'
            f'<div class="num {clr}">{ab}'
            f'<span style="font-size:.85rem;color:#6b7280"> /{total}</span></div>'
            f'<div class="lbl">{lbl} · {pct}%</div>'
            f'</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 52-Week Extremes")
    c = st.columns(4)
    c[0].markdown(card(at52h,   "At / Above 52W High",  "g"), unsafe_allow_html=True)
    c[1].markdown(card(near52h, "Within 5% of 52W High","g"), unsafe_allow_html=True)
    c[2].markdown(card(at52l,   "Within 5% of 52W Low", "r"), unsafe_allow_html=True)
    c[3].markdown(card(near52l, "Within 10% of 52W Low","r"), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Stock Detail")

    bool_cols = [">4EMA",">10EMA",">20EMA",">50EMA",">100EMA"]
    skip_fmt  = ["Symbol"] + bool_cols
    fmt_ad    = {c:"{:.2f}" for c in df_ad.columns if c not in skip_fmt}
    ad_pct    = ["Day Chg%","vs 52WH%","vs 52WL%"]

    s  = df_ad.style.format(fmt_ad, na_rep="—")
    fn = s.map if hasattr(s,"map") else s.applymap
    s  = fn(lambda v: cell_bg(v, 10), subset=[c for c in ad_pct if c in df_ad.columns])

    st.dataframe(s, use_container_width=True, height=580)
    st.caption("✅ price above EMA  ·  ❌ price below EMA  ·  EOD data")
