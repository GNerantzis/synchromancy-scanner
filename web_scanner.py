import streamlit as st
import ccxt
import pandas as pd
import requests
import time

# ================= PAGE CONFIG =================

st.set_page_config(
    page_title="Synchromancy Trend Scanner",
    layout="wide"
)

# ================= MEDIEVAL THEME =================

st.markdown("""
<style>

/* IMPORT REAL MEDIEVAL FONT */
@import url('https://fonts.googleapis.com/css2?family=MedievalSharp&display=swap');

.stApp {
    background: radial-gradient(circle at top, #2b004f, #0d001a);
}

/* APPLY FONT TO EVERYTHING */
html, body, [class*="css"]  {
    font-family: 'MedievalSharp', cursive !important;
}

/* TITLE */
h1 {
    text-align: center;
    color: gold;
    font-family: 'MedievalSharp', cursive !important;
    font-size: 52px;
    letter-spacing: 2px;
}

/* dataframe panel */
div[data-testid="stDataFrame"] > div {
    border: 6px solid #ff9933;
    border-radius: 14px;
    padding: 8px;
    background: #0b1220;
}

/* container width */
.block-container {
    max-width: 95%;
    padding-left: 2rem;
    padding-right: 2rem;
}
            
/* Fix scroll bleed, isolate dataframe scrolling */
div[data-testid="stDataFrame"] {
    overscroll-behavior-y: contain !important;
}

div[data-testid="stDataFrame"] > div {
    overscroll-behavior-y: contain !important;
}

div[data-testid="stDataFrame"] > div > div {
    overscroll-behavior-y: contain !important;
}

/* Critical, stop wheel propagation */
div[data-testid="stDataFrame"] * {
    overscroll-behavior-y: contain !important;
}            

</style>
""", unsafe_allow_html=True)

st.markdown("<h1>✨Synchromancy Trend Scanner🏰🧙🏻‍♀️</h1>", unsafe_allow_html=True)

# ================= INPUT =================

target_count = st.number_input(
    "Number of coins to scan",
    min_value=1,
    max_value=200,
    value=35
)

# ================= EXCHANGE INIT =================

@st.cache_resource
def get_exchange():
    return ccxt.bybit({
        "enableRateLimit": True,
        "options": {"defaultType": "swap"}
    })

exchange = get_exchange()

# ================= FETCH FUNCTION =================

def fetch(symbol, tf):

    data = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=500)

    df = pd.DataFrame(
        data,
        columns=["time","open","high","low","close","volume"]
    )

    df["time"] = pd.to_datetime(df["time"], unit="ms")

    return df

# ================= SUPERTREND =================

ATR_LENGTH = 8
MULTIPLIER = 2

def supertrend(df):

    df = df.copy().reset_index(drop=True)

    df["prev_close"] = df["close"].shift(1)

    df["tr"] = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["prev_close"]).abs(),
        (df["low"] - df["prev_close"]).abs()
    ], axis=1).max(axis=1)

    df["atr"] = 0.0
    df.loc[ATR_LENGTH-1, "atr"] = df["tr"].iloc[:ATR_LENGTH].mean()

    for i in range(ATR_LENGTH, len(df)):

        df.loc[i, "atr"] = (
            (df.loc[i-1, "atr"] * (ATR_LENGTH - 1) + df.loc[i, "tr"])
            / ATR_LENGTH
        )

    hl2 = (df["high"] + df["low"]) / 2

    df["upper"] = hl2 + MULTIPLIER * df["atr"]
    df["lower"] = hl2 - MULTIPLIER * df["atr"]

    df["final_upper"] = df["upper"]
    df["final_lower"] = df["lower"]

    df["trend"] = 1

    for i in range(1, len(df)):

        if (
            df.loc[i, "upper"] < df.loc[i-1, "final_upper"]
            or df.loc[i-1, "close"] > df.loc[i-1, "final_upper"]
        ):
            df.loc[i, "final_upper"] = df.loc[i, "upper"]
        else:
            df.loc[i, "final_upper"] = df.loc[i-1, "final_upper"]

        if (
            df.loc[i, "lower"] > df.loc[i-1, "final_lower"]
            or df.loc[i-1, "close"] < df.loc[i-1, "final_lower"]
        ):
            df.loc[i, "final_lower"] = df.loc[i, "lower"]
        else:
            df.loc[i, "final_lower"] = df.loc[i-1, "final_lower"]

        if df.loc[i-1, "trend"] == 1:

            if df.loc[i, "close"] < df.loc[i-1, "final_lower"]:
                df.loc[i, "trend"] = -1
            else:
                df.loc[i, "trend"] = 1

        else:

            if df.loc[i, "close"] > df.loc[i-1, "final_upper"]:
                df.loc[i, "trend"] = 1
            else:
                df.loc[i, "trend"] = -1

    return df



# ================= DAYS SINCE FLIP =================

def days_since_flip(df):

    trend = df["trend"].iloc[-1]
    now = df["time"].iloc[-1]
    flip = df["time"].iloc[0]

    for i in range(len(df)-2, -1, -1):

        if df["trend"].iloc[i] != trend:
            flip = df["time"].iloc[i+1]
            break

    return (now - flip).days


# ================= PERCENTAGE SINCE FLIP =================

def percent_since_flip(df):

    current_trend = df["trend"].iloc[-1]

    flip_index = 0

    for i in range(len(df)-2, -1, -1):

        if df["trend"].iloc[i] != current_trend:
            flip_index = i + 1
            break

    flip_price = df["close"].iloc[flip_index]
    current_price = df["close"].iloc[-1]

    pct = (current_price - flip_price) / flip_price * 100

    return round(pct, 2)
# ================= FORMAT NUMBER =================

def format_num(n):

    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f} B"

    elif n >= 1_000_000:
        return f"{n/1_000_000:.2f} M"

    return str(n)

# ================= COINGECKO WITH CACHE =================

@st.cache_data(ttl=600)
def get_coins_page(page):

    try:

        url = "https://api.coingecko.com/api/v3/coins/markets"

        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": page
        }

        r = requests.get(url, params=params, timeout=15)

        if r.status_code != 200:
            return []

        data = r.json()

        if isinstance(data, list):
            return data

        return []

    except:
        return []
    
    # ================= FORMAT PRICE =================

def format_price(p):

    if p >= 1000:
        return f"${p:,.2f}"

    elif p >= 1:
        return f"${p:.2f}"

    else:
        return f"${p:.6f}"
    # ================= TRADINGVIEW LINK =================

def tradingview_link(pair):
    clean = pair.replace("/", "")
    return f"https://www.tradingview.com/chart/?symbol=BYBIT:{clean}"


# ================= COLOR FUNCTIONS =================

def color_trend(val):

    if "Bullish" in str(val):
        return "color: #00ff88; font-weight: bold;"

    if "Bearish" in str(val):
        return "color: #ff4b4b; font-weight: bold;"

    return ""


def color_percent(val):

    try:
        num = float(str(val).replace("%",""))

        if num > 0:
            return "color: #00ff88; font-weight: bold;"

        elif num < 0:
            return "color: #ff4b4b; font-weight: bold;"

    except:
        pass

    return ""

# ================= SCAN =================

if st.button("🔮 Scan"):

    results = []

    progress_bar = st.progress(0)
    status = st.empty()

    page = 1
    max_pages = 10

    while len(results) < target_count and page <= max_pages:

        coins = get_coins_page(page)

        if len(coins) == 0:
            break

        for coin in coins:

            if not isinstance(coin, dict):
                continue

            symbol = coin["symbol"].upper()
            pair = f"{symbol}/USDT"

            try:

                df_d = supertrend(fetch(pair, "1d"))
                df_w = supertrend(fetch(pair, "1w"))

                results.append({

                    "Logo": coin["image"],
                    "Coin": coin["name"],
                    "Symbol": pair,
                    "Price Raw": df_d["close"].iloc[-1],
                    "Open Chart": tradingview_link(pair),

                    "Daily": "🟢 ↑ Bullish" if df_d["trend"].iloc[-1] == 1 else "🔴 ↓ Bearish",
                    "Days Since Flip D": days_since_flip(df_d),
                    "% Since Flip D": percent_since_flip(df_d),

                    "Weekly": "🟢 ↑ Bullish" if df_w["trend"].iloc[-1] == 1 else "🔴 ↓ Bearish",
                    "Days Since Fleep W": days_since_flip(df_w),
                    "% Since Flip W": percent_since_flip(df_w),
                    "Market Cap Raw": coin["market_cap"],
                    "Market Cap": format_num(coin["market_cap"]),
                    "Volume Raw": coin["total_volume"],
                    "Volume 24h": format_num(coin["total_volume"])

                })

                progress = len(results) / target_count
                progress_bar.progress(min(progress, 1.0))
                status.text(f"Scanning {len(results)} / {target_count}")

                if len(results) >= target_count:
                    break

            except:
                continue

        page += 1
        time.sleep(0.3)

    if len(results) == 0:

        st.error("No coins scanned. CoinGecko rate limit may still be active.")

    else:

        df = pd.DataFrame(results)

        # ensure RAW columns exist and are numeric
        df["Market Cap Raw"] = pd.to_numeric(df["Market Cap Raw"], errors="coerce")
        df["Volume Raw"] = pd.to_numeric(df["Volume Raw"], errors="coerce")
        df["Price Raw"] = pd.to_numeric(df["Price Raw"], errors="coerce")

        # SORT ONLY USING RAW
        df = df.sort_values("Market Cap Raw", ascending=False)

        # reset index AFTER sorting
        df = df.reset_index(drop=True)

        # ranking column
        df.insert(0, "#", df.index + 1)

        # CREATE DISPLAY VERSION
        display_df = df.copy()

        # Keep values numeric for proper sorting and Streamlit formatting
        display_df["Market Cap"] = display_df["Market Cap Raw"]
        display_df["Volume 24h"] = display_df["Volume Raw"]
        display_df["Price"] = display_df["Price Raw"]

        # Remove raw columns from visible display
        # Keep numeric backbone
        display_df = display_df.drop(columns=[
            "Market Cap Raw",
            "Volume Raw",
            "Price Raw"
        ])

        # Create unified Coin display column
        display_df["Coin Display"] = display_df["Coin"]

        # Reorder columns (Coin Display replaces Logo and Coin)
        display_df = display_df[[
            "#",
            "Logo",
            "Coin Display",
            "Price",
            "Open Chart",

            "Daily",
            "% Since Flip D",
            "Days Since Flip D",

            "Weekly",
            "% Since Flip W",
            "Days Since Fleep W",

            "Market Cap",
            "Volume 24h"
        ]]
        # Format Price with $
        display_df["Price"] = display_df["Price"].apply(lambda x: f"${x:,.2f}")

        # Format percentages with % symbol
        display_df["% Since Flip D"] = display_df["% Since Flip D"].apply(lambda x: f"{x:.2f}%")
        display_df["% Since Flip W"] = display_df["% Since Flip W"].apply(lambda x: f"{x:.2f}%")
        # SHOW
    
    styled_df = display_df.style.applymap(color_trend, subset=["Daily", "Weekly"]) \
                             .applymap(color_percent, subset=["% Since Flip D", "% Since Flip W"])

    st.dataframe(
        styled_df,
        column_config={

            "Logo": st.column_config.ImageColumn("Coin"),

            "Open Chart": st.column_config.LinkColumn(
                "TradingView",
                display_text="Open"
            ),

            "Market Cap": st.column_config.NumberColumn(
                "Market Cap",
                format="compact"
            ),

            "Volume 24h": st.column_config.NumberColumn(
                "Volume 24h",
                format="compact"
            ),

        },
        use_container_width=True,
        hide_index=True,
        height=600
)