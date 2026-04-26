"""
BARITA WEALTH ADVISOR — app.py
Flask Backend | OpenAI GPT-4o + Gemini Flash fallback
Correlation-Aware Diversification | Behavioral Risk Adjustment
Dynamic Weight Allocation | Confidence Score
"""

import os, io, json, math, time
from datetime import datetime

import requests
import numpy as np
try:
    import scipy.optimize as sco
    import scipy.stats as scs
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("[WARN] scipy not installed — MVO disabled, using score-based weights")

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from openai import OpenAI
import firebase_admin
from firebase_admin import credentials, auth as fb_auth, firestore
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle, HRFlowable)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from dotenv import load_dotenv

load_dotenv()

# ── CONFIG ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY           = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY           = os.environ.get("GEMINI_API_KEY", "")
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")
DD_API_KEY               = os.environ.get("DIMENSION_DEPTHS_API_KEY", "")
DD_BASE_URL              = os.environ.get("DIMENSION_DEPTHS_BASE_URL",
    "https://dimension-depths-v2-production.up.railway.app").rstrip("/")

app = Flask(__name__, static_folder="public", static_url_path="")
CORS(app, origins=["*"])

# ── FIREBASE ──────────────────────────────────────────────────────────────────
if FIREBASE_SERVICE_ACCOUNT:
    cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT))
else:
    cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ── AI CLIENTS ────────────────────────────────────────────────────────────────
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Gemini via OpenAI-compatible endpoint
gemini_client = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
) if GEMINI_API_KEY else None

def call_ai(messages, max_tokens=700, system=None):
    """
    Call OpenAI GPT-4o. Falls back to Gemini Flash if OpenAI fails or is unavailable.
    Returns (text, provider_used)
    """
    if system:
        messages = [{"role": "system", "content": system}] + messages

    # Try OpenAI first
    if openai_client:
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o", max_tokens=max_tokens, messages=messages
            )
            return resp.choices[0].message.content, "gpt-4o"
        except Exception as e:
            print(f"[AI] OpenAI failed: {e} — trying Gemini")

    # Fallback to Gemini
    if gemini_client:
        try:
            resp = gemini_client.chat.completions.create(
                model="gemini-2.0-flash", max_tokens=max_tokens, messages=messages
            )
            return resp.choices[0].message.content, "gemini-2.0-flash"
        except Exception as e:
            print(f"[AI] Gemini also failed: {e}")

    return "AI advisor temporarily unavailable. Your portfolio has been generated successfully.", "none"

# ── AUTH ──────────────────────────────────────────────────────────────────────
def verify_token(req):
    header = req.headers.get("Authorization", "")
    if not header.startswith("Bearer "): return None, "Missing token"
    try: return fb_auth.verify_id_token(header.split("Bearer ")[1]), None
    except Exception as e: return None, str(e)

# ── DD API ────────────────────────────────────────────────────────────────────
DD_HEADERS     = {"Authorization": f"Api-Key {DD_API_KEY}"}
_cached_assets = None
_cached_corr   = None
_cached_cov    = None

def dd_get(endpoint, params=None):
    try:
        r = requests.get(f"{DD_BASE_URL}{endpoint}", headers=DD_HEADERS,
                         params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[DD] {endpoint}: {e}")
        return None

def fetch_all_assets():
    global _cached_assets
    if _cached_assets is not None: return _cached_assets
    data = dd_get("/api/soc/assets/")
    if not data: return []
    if isinstance(data, list): _cached_assets = data
    elif isinstance(data, dict):
        _cached_assets = data.get("data") or data.get("results") or []
    else: _cached_assets = []
    print(f"[DD] Fetched {len(_cached_assets)} assets")
    return _cached_assets

def fetch_covariance():
    global _cached_cov
    if _cached_cov is not None: return _cached_cov
    _cached_cov = dd_get("/api/soc/covariance/assets/") or {}
    return _cached_cov

def fetch_correlations():
    global _cached_corr
    if _cached_corr is not None: return _cached_corr
    _cached_corr = dd_get("/api/soc/correlations/assets/") or {}
    return _cached_corr

# ── RISK SCORING ──────────────────────────────────────────────────────────────
def score_answers(answers):
    s = 0
    s += {"I'm completely new to investing":0,"I have basic knowledge but no real experience":1,
          "I've been learning and have some experience":2,"I have a lot of investing experience":3
          }.get(answers.get("knowledge_level",""), 1)
    s += {"Sell everything to avoid further losses":0,"Sell some to reduce losses":1,
          "Wait for recovery":2,"Invest more at lower prices":3
          }.get(answers.get("drop_reaction",""), 1)
    s += {"I worry a lot about losing money":0,"I'm okay with small changes, but big losses stress me":1,
          "I understand ups and downs and stay calm":2,
          "I'm comfortable with big risks and see drops as opportunities":3
          }.get(answers.get("risk_relationship",""), 1)
    s += 0 if answers.get("loss_vs_gain") == "Suffering a 20% loss" else 1
    s += {"Up to 10%":0,"Up to 20%":1,"Up to 40%":2,"More than 40%":3}.get(answers.get("max_loss","Up to 20%"), 1)
    s += {"Less than 3 months":0,"3-6 months":1,"6-12 months":2,"1-2 years":3,"More than 2 years":4
          }.get(answers.get("income_loss_runway",""), 2)
    s += {"Significant debt":0,"Moderate debt":1,"Minor debt":2,"Debt-free":3
          }.get(answers.get("debt_situation",""), 1)
    s += {"More than 25%":0,"10-25%":1,"Less than 10%":2,"No withdrawals":3
          }.get(answers.get("withdrawal_time",""), 2)
    s += {"Fully passive":0,"Mostly passive":1,"Balanced":2,"Mostly active":3,"Fully active":4
          }.get(answers.get("invest_style",""), 2)
    s += {"No - keep it fixed":0,"Yes - small changes":1,"Yes - moderate changes":2,"Yes - fully active":3
          }.get(answers.get("market_adjustment",""), 1)

    pct = s / 30.0
    if pct < 0.35:   profile, label = "Conservative", "Beginner Investor"
    elif pct < 0.65: profile, label = "Moderate",     "Intermediate Investor"
    else:            profile, label = "Aggressive",   "Experienced Investor"

    el = {"I'm completely new to investing":0,"I have basic knowledge but no real experience":1,
          "I've been learning and have some experience":2,"I have a lot of investing experience":3
          }.get(answers.get("knowledge_level",""), 1)
    return s, profile, label, ("Beginner" if el<=1 else ("Experienced" if el==3 else "Intermediate"))

# ── CLASS COLORS ──────────────────────────────────────────────────────────────
CLASS_COLORS = {
    "Cash": "#10B981", "Fixed Income": "#0BB8A9", "Equity": "#3B82F6",
    "Real Estate": "#FB923C", "Alternatives": "#8B5CF6", "Commodities": "#F59E0B",
}

# ── CLIENT CONTEXT ────────────────────────────────────────────────────────────
def derive_client_context(answers):
    ctx = {}
    ctx["goal_equity_bias"] = {
        "Wealth accumulation / growth": 1.0, "Retirement planning": 0.4,
        "Education funding": 0.3, "Property purchase": 0.0,
        "Income generation": -0.5, "Capital preservation": -1.0,
        "Emergency fund building": -1.5,
    }.get(answers.get("primary_goal",""), 0.0)

    ctx["horizon_liquidity_need"] = {
        "More than 25%": 2.0, "10-25%": 1.0,
        "Less than 10%": 0.5, "No withdrawals": 0.0,
    }.get(answers.get("withdrawal_time",""), 0.5)

    ctx["loss_equity_headroom"] = {
        "Up to 10%": -1.5, "Up to 20%": -0.5,
        "Up to 40%": 0.5,  "More than 40%": 1.5,
    }.get(answers.get("max_loss","Up to 20%"), 0.0)

    runway = {"Less than 3 months":-2.0,"3-6 months":-1.0,"6-12 months":0.0,
              "1-2 years":0.5,"More than 2 years":1.0}.get(answers.get("income_loss_runway",""), 0.0)
    debt   = {"Significant debt":-2.0,"Moderate debt":-1.0,"Minor debt":0.0,
              "Debt-free":0.5}.get(answers.get("debt_situation",""), 0.0)
    ctx["resilience_score"] = runway + debt

    ctx["active_style_score"] = {
        "Fully passive":0,"Mostly passive":1,"Balanced":2,"Mostly active":3,"Fully active":4,
    }.get(answers.get("invest_style","Balanced"), 2)

    earn  = answers.get("earn_currency","Mostly JMD")
    spend = answers.get("spend_currency","Mostly JMD")
    usd_l = answers.get("usd_liabilities","None")
    eu = 1.0 if earn=="USD only"  else (0.5 if "USD" in earn  else -0.5)
    su = 1.0 if spend=="USD only" else (0.5 if "USD" in spend else -0.5)
    lu = {"None":0.0,"Under USD $10K":0.3,"USD $10K-$50K":0.6,
          "USD $50K-$200K":1.0,"Over USD $200K":1.5}.get(usd_l, 0.0)
    ctx["usd_bias"] = eu + su + lu

    ic = {"Not sure":0.0,"Minimal":0.0,"Moderate":0.5,"Significant":1.0,"Severe":1.5
          }.get(answers.get("inflation_impact","Moderate"), 0.5)
    ip = {"Not sure":0.0,"Not necessary":0.0,"Somewhat":0.5,"Yes - strong focus":1.5
          }.get(answers.get("inflation_protection","Somewhat"), 0.5)
    ctx["inflation_hedge_need"] = ic + ip

    return ctx

# ═══════════════════════════════════════════════════════════════════════════════
#  LAYER 2: BEHAVIORAL RISK ADJUSTMENT (Psychology Layer)
#  Detects psychological biases and adjusts the raw risk profile
# ═══════════════════════════════════════════════════════════════════════════════

def behavioral_risk_adjustment(answers, raw_profile):
    """
    Detect behavioral biases from questionnaire patterns:
    - Loss aversion gap: stated tolerance vs actual reaction diverge
    - Overconfidence: high knowledge + high risk without resilience
    - Anchoring: benchmarking to original investment (loss-averse signal)
    - Recency bias: very high or very low max_loss tolerance
    Returns adjusted profile and a behavioral_flags dict for the report
    """
    flags = {}
    adjustment = 0  # negative = more conservative, positive = more aggressive

    # ── Loss aversion gap ─────────────────────────────────────────────────────
    drop  = answers.get("drop_reaction","")
    loss  = answers.get("loss_vs_gain","")
    max_l = answers.get("max_loss","")

    sell_reaction = drop in ("Sell everything to avoid further losses","Sell some to reduce losses")
    fears_loss    = loss == "Suffering a 20% loss"
    low_tolerance = max_l in ("Up to 10%","Up to 20%")

    if sell_reaction and fears_loss and low_tolerance:
        flags["loss_aversion"] = {
            "detected": True,
            "note": "Your responses suggest a strong aversion to losses. We've applied a more protective allocation to match your actual comfort level."
        }
        adjustment -= 1

    # ── Overconfidence ────────────────────────────────────────────────────────
    knowledge = answers.get("knowledge_level","")
    runway    = answers.get("income_loss_runway","")
    debt      = answers.get("debt_situation","")
    high_exp  = knowledge == "I have a lot of investing experience"
    low_safety= runway in ("Less than 3 months","3-6 months") or debt in ("Significant debt","Moderate debt")

    if high_exp and low_safety and raw_profile == "Aggressive":
        flags["overconfidence"] = {
            "detected": True,
            "note": "High investment confidence combined with limited financial safety net detected. Portfolio tempered to protect against a forced sell at the worst time."
        }
        adjustment -= 1

    # ── Anchoring bias ────────────────────────────────────────────────────────
    benchmark = answers.get("performance_benchmark","")
    if benchmark == "The amount I originally invested":
        flags["anchoring"] = {
            "detected": True,
            "note": "You tend to measure performance against your original investment — a natural human tendency. Your portfolio is structured to minimise the chance of ending below your starting point."
        }
        adjustment -= 0.5

    # ── Overoptimism ──────────────────────────────────────────────────────────
    if max_l == "More than 40%" and drop == "Invest more at lower prices" and low_safety:
        flags["overoptimism"] = {
            "detected": True,
            "note": "Your stated risk appetite is very high, but your financial safety net is limited. We've slightly moderated the allocation to account for real-world constraints."
        }
        adjustment -= 0.5

    # Apply adjustment to profile
    profile_order = ["Conservative", "Moderate", "Aggressive"]
    idx = profile_order.index(raw_profile)
    new_idx = max(0, min(2, round(idx + adjustment)))
    adjusted_profile = profile_order[new_idx]

    if adjusted_profile != raw_profile:
        flags["profile_adjusted"] = {
            "original": raw_profile,
            "adjusted": adjusted_profile,
            "reason": "Behavioral analysis suggested a more suitable risk level based on your response patterns."
        }

    return adjusted_profile, flags

# ═══════════════════════════════════════════════════════════════════════════════
#  LAYER 3: CORRELATION-AWARE DIVERSIFICATION
#  Uses the actual DD correlation matrix to penalise highly correlated pairs
# ═══════════════════════════════════════════════════════════════════════════════

def get_correlation(corr_data, ticker_a, ticker_b):
    """Extract correlation between two assets from DD correlation matrix."""
    if not corr_data or not isinstance(corr_data, dict):
        return 0.0
    matrix = corr_data.get("matrix") or corr_data.get("data") or corr_data
    if not isinstance(matrix, dict): return 0.0
    row = matrix.get(ticker_a, {})
    if isinstance(row, dict): return float(row.get(ticker_b, 0.0))
    return 0.0

def diversification_penalty(asset, selected_so_far, corr_data):
    """
    Calculate how much adding this asset REDUCES diversification.
    High average correlation with already-selected assets = high penalty.
    """
    if not selected_so_far or not corr_data:
        return 0.0
    ta = asset.get("ticker","")
    corrs = []
    for s in selected_so_far:
        tb = s.get("ticker","")
        c  = abs(get_correlation(corr_data, ta, tb))
        corrs.append(c)
    return sum(corrs) / len(corrs) if corrs else 0.0

def correlation_aware_select(candidates, target_n, max_per_class, corr_data):
    """
    Greedy selection that balances individual asset score with portfolio diversification.
    Each round: pick the asset with best (score - correlation_penalty).
    """
    selected   = []
    class_counts = {}
    # Threshold for correlation penalty weight
    CORR_WEIGHT = 0.8

    remaining = list(candidates)
    while len(selected) < target_n and remaining:
        best_asset = None
        best_combined = -999

        for asset in remaining:
            ac = asset["_class"]
            if class_counts.get(ac, 0) >= max_per_class:
                continue
            corr_pen  = diversification_penalty(asset, selected, corr_data)
            combined  = asset["_score"] - CORR_WEIGHT * corr_pen * 2.0
            if combined > best_combined:
                best_combined = combined
                best_asset    = asset

        if best_asset is None:
            # Relax class limit and try again
            for asset in remaining:
                if asset not in selected:
                    corr_pen = diversification_penalty(asset, selected, corr_data)
                    combined = asset["_score"] - CORR_WEIGHT * corr_pen * 2.0
                    if combined > best_combined:
                        best_combined = combined
                        best_asset    = asset
            if best_asset is None:
                break

        ac = best_asset["_class"]
        best_asset["_corr_penalty"] = diversification_penalty(best_asset, selected, corr_data)
        selected.append(best_asset)
        class_counts[ac] = class_counts.get(ac, 0) + 1
        remaining.remove(best_asset)

    return selected

# ═══════════════════════════════════════════════════════════════════════════════
#  LAYER 4: DYNAMIC WEIGHT ALLOCATION
#  Not fixed % — weights driven by score, caps, and correlation-adjusted
#  contribution to portfolio Sharpe
# ═══════════════════════════════════════════════════════════════════════════════

def classify_asset(a):
    sc  = (a.get("super_class") or a.get("asset_class") or "").lower()
    sub = (a.get("sub_class")   or a.get("subclass")    or "").lower()
    nm  = (a.get("name")        or a.get("ticker")      or "").lower()
    if "cash" in sc or "money market" in sc or "t-bill" in sub or "tbill" in nm: return "Cash"
    if "fixed" in sc or "bond" in sc or "debt" in sc:   return "Fixed Income"
    if "equit" in sc or "stock" in sc or "share" in sc: return "Equity"
    if "real estate" in sc or "reit" in sc:             return "Real Estate"
    if "altern" in sc or "hedge" in sc:                 return "Alternatives"
    if "commod" in sc or "gold" in sc:                  return "Commodities"
    if "bond" in sub or "fixed" in sub: return "Fixed Income"
    if "equit" in sub or "stock" in sub: return "Equity"
    return sc.title() if sc else "Other"

def score_asset(asset, profile, ctx):
    sc     = 0.0
    ac     = classify_asset(asset)
    ret    = float(asset.get("total_expected_return") or asset.get("expected_return") or 0)
    vol    = float(asset.get("volatility_ann")        or asset.get("volatility")       or 0)
    sharpe = float(asset.get("sharpe_ratio")          or 0)
    ticker = (asset.get("ticker") or "").upper()
    is_usd = "USD" in ticker

    base = {
        "Conservative": {"Cash":3.0,"Fixed Income":2.8,"Real Estate":1.2,"Equity":0.4,"Alternatives":0.2,"Commodities":0.1},
        "Moderate":     {"Cash":0.8,"Fixed Income":2.0,"Real Estate":1.6,"Equity":2.2,"Alternatives":1.0,"Commodities":0.7},
        "Aggressive":   {"Cash":0.2,"Fixed Income":0.7,"Real Estate":1.4,"Equity":3.2,"Alternatives":2.2,"Commodities":1.4},
    }
    sc += base.get(profile, base["Moderate"]).get(ac, 0.5)

    gb = ctx.get("goal_equity_bias", 0)
    if gb > 0 and ac == "Equity":                  sc += gb * 0.6
    elif gb < 0 and ac in ("Cash","Fixed Income"): sc += abs(gb) * 0.6

    liq = ctx.get("horizon_liquidity_need", 0.5)
    if liq >= 1.5 and ac == "Cash": sc += 1.2
    elif liq >= 0.5 and ac == "Cash": sc += 0.5

    lh = ctx.get("loss_equity_headroom", 0)
    rm = max(1.0, min(3.0 + lh, 6.0))
    sc += min(ret * rm, 2.5)

    res      = ctx.get("resilience_score", 0)
    base_tol = {"Conservative":0.05,"Moderate":0.12,"Aggressive":0.22}.get(profile, 0.12)
    vtol     = max(0.02, base_tol + res * 0.02)
    if vol > vtol: sc -= (vol - vtol) * max(2.0, 4.0 - res * 0.5)

    sc += min(sharpe * 0.5, 1.2)

    ub = ctx.get("usd_bias", 0)
    if ub > 0.5 and is_usd:     sc += min(ub * 0.4, 1.0)
    elif ub < -0.2 and not is_usd: sc += 0.4

    ih = ctx.get("inflation_hedge_need", 0)
    if ih >= 1.0 and ac in ("Real Estate","Commodities","Equity"): sc += min(ih * 0.35, 1.0)
    elif ac == "Cash" and ih >= 1.5: sc -= 0.5

    return sc

def apply_exclusions(assets, answers):
    avoid = answers.get("avoid_assets",[])
    am = {"Equities (Stocks)":"Equity","Fixed Income (Bonds)":"Fixed Income",
          "Real Estate":"Real Estate","Commodities":"Commodities",
          "Cash and Cash Equivalents":"Cash","Alternative Investments":"Alternatives"}
    ac_set = {am[a] for a in avoid if a in am}
    if not ac_set: return assets
    f = [a for a in assets if classify_asset(a) not in ac_set]
    return f if f else assets

def derive_class_caps(profile, ctx):
    base = {
        "Conservative": {"Cash":45,"Fixed Income":50,"Equity":15,"Real Estate":20,"Alternatives":10,"Commodities":5},
        "Moderate":     {"Cash":15,"Fixed Income":40,"Equity":55,"Real Estate":20,"Alternatives":15,"Commodities":10},
        "Aggressive":   {"Cash":10,"Fixed Income":20,"Equity":75,"Real Estate":20,"Alternatives":25,"Commodities":15},
    }
    caps = dict(base.get(profile, base["Moderate"]))
    gb=ctx.get("goal_equity_bias",0); liq=ctx.get("horizon_liquidity_need",0.5)
    lh=ctx.get("loss_equity_headroom",0); res=ctx.get("resilience_score",0)
    ih=ctx.get("inflation_hedge_need",0)

    es = round(gb*5)
    caps["Equity"]       = max(5,  min(80, caps["Equity"]       + es))
    caps["Fixed Income"] = max(5,  min(60, caps["Fixed Income"] - es//2))

    if liq >= 1.5:
        caps["Cash"]         = min(caps["Cash"]        +15, 60)
        caps["Equity"]       = max(caps["Equity"]      -10, 5)
        caps["Fixed Income"] = min(caps["Fixed Income"] +5, 60)
    elif liq >= 0.5:
        caps["Cash"]         = min(caps["Cash"]+5, 50)

    caps["Equity"] = max(5, min(80, caps["Equity"] + round(lh*4)))

    if res < -1:
        red = min(abs(round(res*4)), 20)
        caps["Equity"]       = max(5, caps["Equity"]      - red)
        caps["Alternatives"] = max(0, caps["Alternatives"]- red//2)
        caps["Cash"]         = min(60,caps["Cash"]        + red//2)

    if ih >= 1.0:
        b = min(round(ih*5), 15)
        caps["Real Estate"] = min(caps["Real Estate"]+b, 30)
        caps["Commodities"] = min(caps["Commodities"]+b, 15)

    return caps

def assign_weights(assets, profile, ctx):
    """Dynamic weight allocation using score-proportional softmax + class caps."""
    if not assets: return []
    caps   = derive_class_caps(profile, ctx)
    scores = [max(a["_score"], 0.01) for a in assets]
    total  = sum(scores)
    rw     = [s/total*100 for s in scores]

    ct = {}
    for i,a in enumerate(assets):
        ac=classify_asset(a); ct[ac]=ct.get(ac,0)+rw[i]

    # Scale down over-cap
    for i,a in enumerate(assets):
        ac=classify_asset(a); cap=caps.get(ac,30)
        if ct.get(ac,0) > cap: rw[i] *= cap/ct[ac]

    rw    = [min(w, 35.0) for w in rw]
    t2    = sum(rw)
    if t2 == 0: return []
    wts   = [round(w/t2*100, 1) for w in rw]
    diff  = round(100.0 - sum(wts), 1)
    if wts: wts[0] = round(wts[0]+diff, 1)

    out = []
    for i,a in enumerate(assets):
        ac = classify_asset(a)
        out.append({
            "label":           a.get("name") or a.get("ticker", f"Asset {i+1}"),
            "ticker":          a.get("ticker","—"),
            "pct":             wts[i],
            "color":           CLASS_COLORS.get(ac,"#6B7280"),
            "class":           ac,
            "expected_return": a.get("total_expected_return") or a.get("expected_return"),
            "volatility":      a.get("volatility_ann") or a.get("volatility"),
            "sharpe_ratio":    a.get("sharpe_ratio"),
            "corr_penalty":    round(a.get("_corr_penalty",0), 3),
        })
    out.sort(key=lambda x: -x["pct"])
    return out

# ═══════════════════════════════════════════════════════════════════════════════
#  LAYER 5: CONFIDENCE SCORE
#  How well the portfolio matches the client's stated preferences
# ═══════════════════════════════════════════════════════════════════════════════

def compute_confidence_score(allocations, answers, profile, behavioral_flags, corr_data):
    """
    Confidence score (0-100) reflecting:
    - Completeness of questionnaire (20pts)
    - Profile-allocation alignment (25pts)
    - Diversification quality via avg pairwise correlation (25pts)
    - Financial resilience of the client (15pts)
    - Absence of behavioral risk flags (15pts)
    """
    score = 0
    breakdown = {}

    # ── Completeness (20pts) ─────────────────────────────────────────────────
    key_fields = ["primary_goal","withdrawal_time","max_loss","income_loss_runway",
                  "debt_situation","earn_currency","spend_currency","invest_style",
                  "knowledge_level","inflation_impact"]
    filled = sum(1 for f in key_fields if answers.get(f))
    completeness = round(filled / len(key_fields) * 20)
    score += completeness
    breakdown["completeness"] = {"pts": completeness, "max": 20,
                                  "label": f"{filled}/{len(key_fields)} key questions answered"}

    # ── Profile-allocation alignment (25pts) ─────────────────────────────────
    class_totals = {}
    for a in allocations:
        ac = a.get("class","Other")
        class_totals[ac] = class_totals.get(ac,0) + a["pct"]

    ideal = {
        "Conservative": {"Cash":35,"Fixed Income":45,"Equity":10,"Real Estate":10},
        "Moderate":     {"Cash":10,"Fixed Income":35,"Equity":40,"Real Estate":15},
        "Aggressive":   {"Cash":5, "Fixed Income":15,"Equity":65,"Real Estate":10},
    }.get(profile, {})

    misalignment = sum(abs(class_totals.get(ac,0) - ideal.get(ac,0))
                       for ac in set(list(class_totals.keys())+list(ideal.keys()))) / 2
    alignment_pts = max(0, round(25 - misalignment * 0.5))
    score += alignment_pts
    breakdown["alignment"] = {"pts": alignment_pts, "max": 25,
                               "label": f"Portfolio aligns with {profile} profile"}

    # ── Diversification quality (25pts) ──────────────────────────────────────
    tickers = [a["ticker"] for a in allocations]
    corr_sum = 0; pairs = 0
    for i in range(len(tickers)):
        for j in range(i+1, len(tickers)):
            c = abs(get_correlation(corr_data, tickers[i], tickers[j]))
            corr_sum += c; pairs += 1
    avg_corr = corr_sum/pairs if pairs > 0 else 0.5
    # Lower avg correlation = better diversification
    div_pts = round(25 * (1 - avg_corr))
    score += div_pts
    breakdown["diversification"] = {"pts": div_pts, "max": 25,
                                     "label": f"Avg pairwise correlation: {avg_corr:.2f}"}

    # ── Financial resilience (15pts) ──────────────────────────────────────────
    runway = {"Less than 3 months":0,"3-6 months":3,"6-12 months":6,
              "1-2 years":10,"More than 2 years":15
              }.get(answers.get("income_loss_runway",""), 6)
    debt   = {"Significant debt":-3,"Moderate debt":0,"Minor debt":3,"Debt-free":5
              }.get(answers.get("debt_situation",""), 0)
    res_pts = max(0, min(15, runway + debt))
    score += res_pts
    breakdown["resilience"] = {"pts": res_pts, "max": 15,
                                "label": "Financial safety net strength"}

    # ── Behavioral flags (15pts) ──────────────────────────────────────────────
    flag_count  = sum(1 for k,v in behavioral_flags.items()
                      if isinstance(v,dict) and v.get("detected"))
    behav_pts   = max(0, 15 - flag_count * 5)
    score += behav_pts
    breakdown["behavioral"] = {"pts": behav_pts, "max": 15,
                                "label": f"{flag_count} behavioral flag(s) detected"}

    score = min(100, score)
    if score >= 80:   grade, label = "A", "Excellent match"
    elif score >= 65: grade, label = "B", "Good match"
    elif score >= 50: grade, label = "C", "Moderate match"
    else:             grade, label = "D", "Review recommended"

    return {"score": score, "grade": grade, "label": label, "breakdown": breakdown}

# ── PORTFOLIO METRICS ─────────────────────────────────────────────────────────
def compute_portfolio_metrics(allocs, cov):
    wts  = [a["pct"]/100 for a in allocs]
    rets = [float(a.get("expected_return") or 0) for a in allocs]
    vols = [float(a.get("volatility")      or 0) for a in allocs]
    pr   = sum(w*r for w,r in zip(wts,rets))
    pv   = 0.0
    if cov and isinstance(cov, dict):
        try:
            tks = [a["ticker"] for a in allocs]
            cm  = cov.get("matrix") or cov.get("data") or cov
            var = 0.0
            for i,ti in enumerate(tks):
                for j,tj in enumerate(tks):
                    row = cm.get(ti) if isinstance(cm,dict) else {}
                    cv  = float(row.get(tj,0)) if isinstance(row,dict) else 0.0
                    var += wts[i]*wts[j]*cv
            pv = math.sqrt(max(var,0))
        except: pv=0.0
    if pv==0 and vols: pv = sum(w*v for w,v in zip(wts,vols))*0.75
    rf = 0.04
    sh = (pr-rf)/pv if pv>0 else 0.0
    return {"expected_return":f"{pr*100:.1f}%","volatility":f"{pv*100:.1f}%","sharpe_ratio":f"{sh:.2f}"}

def build_risk_breakdown(allocs):
    t={}
    for a in allocs: t[a.get("class","Other")]=t.get(a.get("class","Other"),0)+a["pct"]
    return {ac:{"pct":round(p),"color":CLASS_COLORS.get(ac,"#6B7280")}
            for ac,p in sorted(t.items(),key=lambda x:-x[1])}

# ── FULL DD PIPELINE ──────────────────────────────────────────────────────────
def build_portfolio_from_dd(profile, answers, behavioral_profile=None):
    effective_profile = behavioral_profile or profile

    all_assets = fetch_all_assets()
    if not all_assets: return None,None,None,None

    filtered = [a for a in all_assets
                if (float(a.get("total_expected_return") or a.get("expected_return") or 0)!=0
                    or float(a.get("volatility_ann") or a.get("volatility") or 0)!=0)
                and classify_asset(a) != "Other"]

    if not filtered: return None,None,None,None

    filtered = apply_exclusions(filtered, answers)
    ctx      = derive_client_context(answers)

    for a in filtered:
        a["_class"] = classify_asset(a)
        a["_score"] = score_asset(a, effective_profile, ctx)

    active        = ctx.get("active_style_score",2)
    target_n      = max(4, {"Conservative":5,"Moderate":7,"Aggressive":9}.get(effective_profile,7)-(4-active))
    max_per_class = 2 if active<=1 else (3 if active<=2 else 4)

    filtered.sort(key=lambda x: x["_score"], reverse=True)

    # Use correlation-aware selection
    corr_data = fetch_correlations()
    selected  = correlation_aware_select(filtered, target_n, max_per_class, corr_data)

    if len(selected) < 4:
        for a in filtered:
            if a not in selected and len(selected) < target_n: selected.append(a)

    print(f"[DD] Selected {len(selected)} assets, {len({a['_class'] for a in selected})} classes")

    cov     = fetch_covariance()

    # Try MVO first (score-based selection already done)
    primary_goal = answers.get("primary_goal", "Wealth accumulation / growth")
    mvo_allocs, mvo_rb, mvo_metrics, mvo_w = build_portfolio_with_mvo(
        selected, effective_profile, primary_goal, corr_data, ctx
    )

    if mvo_allocs:
        print(f"[MVO] Success — strategy: {mvo_metrics.get('mvo_strategy','?')}")
        return mvo_allocs, mvo_rb, mvo_metrics, corr_data
    else:
        # MVO failed — use score-based dynamic weights
        print("[MVO] Falling back to score-based weights")
        allocs  = assign_weights(selected, effective_profile, ctx)
        if not allocs: return None,None,None,None
        metrics = compute_portfolio_metrics(allocs, cov)
        rb      = build_risk_breakdown(allocs)
        return allocs, rb, metrics, corr_data

def build_fallback_portfolio(profile, answers, behavioral_profile=None):
    effective_profile = behavioral_profile or profile
    ctx  = derive_client_context(answers)
    if effective_profile=="Conservative":
        raw=[{"label":"JMD T-Bills","ticker":"TBILLJMD","pct":25,"color":"#10B981","class":"Cash"},
             {"label":"USD T-Bills","ticker":"TBILLUSD","pct":15,"color":"#6EE7B7","class":"Cash"},
             {"label":"Short Gov Bonds","ticker":"PVAU / CWPU","pct":25,"color":"#0BB8A9","class":"Fixed Income"},
             {"label":"Long Gov Bonds","ticker":"JFG / QPESE","pct":20,"color":"#38BDF8","class":"Fixed Income"},
             {"label":"Real Estate Fund","ticker":"XEAK","pct":10,"color":"#FB923C","class":"Real Estate"},
             {"label":"Domestic Defensives","ticker":"PDTOU / XPMCJ","pct":5,"color":"#A78BFA","class":"Equity"}]
        metrics={"expected_return":"7.4%","volatility":"4.2%","sharpe_ratio":"1.41"}
    elif effective_profile=="Moderate":
        raw=[{"label":"Short Gov Bonds","ticker":"PVAU / CWPU","pct":18,"color":"#0BB8A9","class":"Fixed Income"},
             {"label":"Long Gov Bonds","ticker":"JFG / QPESE","pct":12,"color":"#38BDF8","class":"Fixed Income"},
             {"label":"Corporate Bonds","ticker":"IRKXL / DTOT","pct":10,"color":"#FBBF24","class":"Fixed Income"},
             {"label":"Domestic Financials","ticker":"XKFZ / KBJZN","pct":15,"color":"#3B82F6","class":"Equity"},
             {"label":"Domestic Defensives","ticker":"PDTOU / XPMCJ","pct":15,"color":"#8B5CF6","class":"Equity"},
             {"label":"Global Tech Equity","ticker":"WBG / MOSWO","pct":15,"color":"#EC4899","class":"Equity"},
             {"label":"Real Estate Fund","ticker":"XEAK","pct":10,"color":"#FB923C","class":"Real Estate"},
             {"label":"Alt Investments","ticker":"IGRIG","pct":5,"color":"#6B7280","class":"Alternatives"}]
        metrics={"expected_return":"11.8%","volatility":"9.6%","sharpe_ratio":"0.97"}
    else:
        raw=[{"label":"Domestic Financials","ticker":"XKFZ / KBJZN / TIHE","pct":18,"color":"#3B82F6","class":"Equity"},
             {"label":"Domestic Cyclicals","ticker":"MBTTD / YTR / IZQLN","pct":14,"color":"#EF4444","class":"Equity"},
             {"label":"Global Tech Equity","ticker":"WBG / MOSWO / RJK","pct":20,"color":"#8B5CF6","class":"Equity"},
             {"label":"Emerging Markets","ticker":"BQB / EMWB / CQOAC","pct":15,"color":"#06B6D4","class":"Equity"},
             {"label":"Corporate Bonds","ticker":"IRKXL / DTOT","pct":12,"color":"#FBBF24","class":"Fixed Income"},
             {"label":"Real Estate Fund","ticker":"XEAK","pct":10,"color":"#FB923C","class":"Real Estate"},
             {"label":"Alt Investments","ticker":"IGRIG","pct":8,"color":"#6B7280","class":"Alternatives"},
             {"label":"JMD T-Bills","ticker":"TBILLJMD","pct":3,"color":"#10B981","class":"Cash"}]
        metrics={"expected_return":"17.3%","volatility":"16.8%","sharpe_ratio":"0.88"}

    raw   = apply_exclusions(raw, answers)
    caps  = derive_class_caps(effective_profile, ctx)
    for a in raw: a["_score"]=caps.get(a["class"],10)/100.0; a["_class"]=a["class"]; a["_corr_penalty"]=0.0
    allocs = assign_weights(raw, effective_profile, ctx)
    if not allocs:
        t=sum(a["pct"] for a in raw)
        for a in raw: a["pct"]=round(a["pct"]/t*100)
        d=100-sum(a["pct"] for a in raw)
        if raw and d!=0: raw[0]["pct"]+=d
        allocs=raw
    return allocs, build_risk_breakdown(allocs), metrics, {}

# ═══════════════════════════════════════════════════════════════════════════════
#  MVO + MONTE CARLO ENGINE  (per Technical Design Document v1.0.0)
#  Mean-Variance Optimisation → Max Sharpe / Min Vol / Income-Constrained
#  + Monte Carlo simulation for probability-of-goal validation
# ═══════════════════════════════════════════════════════════════════════════════

def build_return_covariance_from_dd(assets_list, cov_data):
    """
    Build expected return vector (mu) and covariance matrix (Sigma)
    from Dimension Depths asset data and covariance endpoint.
    Falls back to estimated covariance from volatility if DD matrix unavailable.
    """
    n       = len(assets_list)
    tickers = [a.get("ticker","") for a in assets_list]

    # Expected returns vector
    mu = np.array([float(a.get("total_expected_return") or
                         a.get("expected_return") or 0.08) for a in assets_list])

    # Covariance matrix — try DD first
    sigma = np.zeros((n, n))
    cov_matrix = None
    if cov_data and isinstance(cov_data, dict):
        cov_matrix = cov_data.get("matrix") or cov_data.get("data") or cov_data

    if cov_matrix and isinstance(cov_matrix, dict):
        for i, ti in enumerate(tickers):
            for j, tj in enumerate(tickers):
                row = cov_matrix.get(ti, {})
                val = float(row.get(tj, 0.0)) if isinstance(row, dict) else 0.0
                sigma[i, j] = val
        # Ensure positive semi-definite
        sigma = (sigma + sigma.T) / 2
        min_eig = np.linalg.eigvalsh(sigma).min()
        if min_eig < 0:
            sigma += (-min_eig + 1e-6) * np.eye(n)
    else:
        # Estimate from volatilities with average correlation 0.3
        vols = np.array([float(a.get("volatility_ann") or a.get("volatility") or 0.12)
                         for a in assets_list])
        for i in range(n):
            for j in range(n):
                sigma[i, j] = 0.3 * vols[i] * vols[j] if i != j else vols[i] ** 2

    return mu, sigma, tickers


def mvo_max_sharpe(mu, sigma, risk_free=0.04, constraints_extra=None):
    """Maximise Sharpe Ratio via scipy minimisation."""
    n = len(mu)
    if n == 0: return None

    def neg_sharpe(w):
        port_ret = float(np.dot(w, mu))
        port_vol = float(np.sqrt(np.dot(w, np.dot(sigma, w))))
        return -(port_ret - risk_free) / port_vol if port_vol > 1e-8 else 0.0

    w0          = np.ones(n) / n
    bounds      = tuple((0.02, 0.40) for _ in range(n))
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    if constraints_extra:
        constraints += constraints_extra

    try:
        res = sco.minimize(neg_sharpe, w0, method="SLSQP",
                           bounds=bounds, constraints=constraints,
                           options={"maxiter": 1000, "ftol": 1e-9})
        if res.success:
            w = np.abs(res.x)
            return w / w.sum()
    except Exception as e:
        print(f"[MVO] max_sharpe failed: {e}")
    return None


def mvo_min_volatility(mu, sigma, constraints_extra=None):
    """Minimise portfolio volatility (Global Minimum Variance)."""
    n = len(mu)
    if n == 0: return None

    def port_vol(w):
        return float(np.sqrt(np.dot(w, np.dot(sigma, w))))

    w0          = np.ones(n) / n
    bounds      = tuple((0.02, 0.40) for _ in range(n))
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    if constraints_extra:
        constraints += constraints_extra

    try:
        res = sco.minimize(port_vol, w0, method="SLSQP",
                           bounds=bounds, constraints=constraints,
                           options={"maxiter": 1000, "ftol": 1e-9})
        if res.success:
            w = np.abs(res.x)
            return w / w.sum()
    except Exception as e:
        print(f"[MVO] min_vol failed: {e}")
    return None


def mvo_income_constrained(mu, sigma, yields, min_yield=0.035, constraints_extra=None):
    """Minimise volatility subject to portfolio yield >= min_yield (Income client)."""
    n = len(mu)
    if n == 0 or yields is None: return None

    def port_vol(w):
        return float(np.sqrt(np.dot(w, np.dot(sigma, w))))

    y_arr       = np.array(yields)
    w0          = np.ones(n) / n
    bounds      = tuple((0.02, 0.40) for _ in range(n))
    constraints = [
        {"type": "eq",  "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq","fun": lambda w: float(np.dot(w, y_arr)) - min_yield},
    ]
    if constraints_extra:
        constraints += constraints_extra

    try:
        res = sco.minimize(port_vol, w0, method="SLSQP",
                           bounds=bounds, constraints=constraints,
                           options={"maxiter": 1000, "ftol": 1e-9})
        if res.success:
            w = np.abs(res.x)
            return w / w.sum()
    except Exception as e:
        print(f"[MVO] income_constrained failed: {e}")
    return None


def run_monte_carlo(weights, mu, sigma, initial=100_000, years=10, sims=5000):
    """
    Monte Carlo simulation — 5,000 scenarios × 10-year horizon.
    Returns dict with probability metrics for Goal-Based validation.
    """
    w          = np.array(weights)
    port_ret   = float(np.dot(w, mu))
    port_vol   = float(np.sqrt(np.dot(w, np.dot(sigma, w))))

    # Simulate annual returns (normal dist — skew/kurtosis enhancement possible)
    np.random.seed(42)
    ann_returns = np.random.normal(port_ret, port_vol, (sims, years))
    wealth      = initial * np.cumprod(1 + ann_returns, axis=1)  # shape (sims, years)
    final       = wealth[:, -1]

    # Goal thresholds
    double_goal = initial * 2
    preserve    = initial * 0.9

    return {
        "prob_double":     round(float((final > double_goal).mean() * 100), 1),
        "prob_preserve":   round(float((final > preserve).mean()  * 100), 1),
        "median_final":    round(float(np.median(final)), 0),
        "p10_final":       round(float(np.percentile(final, 10)), 0),
        "p90_final":       round(float(np.percentile(final, 90)), 0),
        "port_return":     round(port_ret * 100, 2),
        "port_vol":        round(port_vol * 100, 2),
        "sharpe":          round((port_ret - 0.04) / port_vol if port_vol > 0 else 0, 3),
        "years":           years,
        "simulations":     sims,
        "initial":         initial,
    }


def choose_mvo_strategy(profile, primary_goal):
    """Pick MVO objective based on client profile and goal."""
    income_goals = {"Income generation", "Capital preservation", "Emergency fund building"}
    if primary_goal in income_goals:
        return "income"
    if profile == "Conservative":
        return "min_vol"
    return "max_sharpe"  # Moderate + Aggressive


def apply_mvo_weights(assets_list, weights_arr, cov_data):
    """Convert MVO weight array back to allocation dicts."""
    out = []
    for i, a in enumerate(assets_list):
        ac = classify_asset(a)
        out.append({
            "label":           a.get("name") or a.get("ticker", f"Asset {i+1}"),
            "ticker":          a.get("ticker", "—"),
            "pct":             round(float(weights_arr[i]) * 100, 1),
            "color":           CLASS_COLORS.get(ac, "#6B7280"),
            "class":           ac,
            "expected_return": a.get("total_expected_return") or a.get("expected_return"),
            "volatility":      a.get("volatility_ann") or a.get("volatility"),
            "sharpe_ratio":    a.get("sharpe_ratio"),
            "corr_penalty":    round(a.get("_corr_penalty", 0), 3),
        })
    # Fix rounding
    total = sum(x["pct"] for x in out)
    if out and abs(total - 100) > 0.05:
        out[0]["pct"] = round(out[0]["pct"] + (100 - total), 1)
    out.sort(key=lambda x: -x["pct"])
    return out


def build_portfolio_with_mvo(assets_list, profile, primary_goal, cov_data, ctx):
    """
    Full MVO pipeline:
    1. Build mu + Sigma from DD data
    2. Select strategy (Max Sharpe / Min Vol / Income)
    3. Run MVO optimisation
    4. Run Monte Carlo validation
    5. Return allocations + extended metrics
    """
    if not HAS_SCIPY or not assets_list:
        return None, None, None, None

    mu, sigma, tickers = build_return_covariance_from_dd(assets_list, cov_data)
    strategy = choose_mvo_strategy(profile, primary_goal)
    print(f"[MVO] Strategy: {strategy} | Assets: {len(assets_list)}")

    weights = None
    if strategy == "income":
        yields = [float(a.get("income_yield_ann") or a.get("total_expected_return") or 0.04)
                  for a in assets_list]
        weights = mvo_income_constrained(mu, sigma, yields, min_yield=0.035)
        if weights is None:  # fallback if income constraint infeasible
            weights = mvo_min_volatility(mu, sigma)
    elif strategy == "min_vol":
        weights = mvo_min_volatility(mu, sigma)
    else:
        weights = mvo_max_sharpe(mu, sigma)

    if weights is None:
        print("[MVO] Optimisation failed — falling back to score weights")
        return None, None, None, None

    # Monte Carlo
    mc = run_monte_carlo(weights, mu, sigma)

    allocs  = apply_mvo_weights(assets_list, weights, cov_data)
    rb      = build_risk_breakdown(allocs)

    cov     = fetch_covariance()
    metrics = compute_portfolio_metrics(allocs, cov)
    # Enrich metrics with MVO-derived numbers (more precise than heuristic)
    metrics["expected_return"] = f"{mc['port_return']:.1f}%"
    metrics["volatility"]      = f"{mc['port_vol']:.1f}%"
    metrics["sharpe_ratio"]    = f"{mc['sharpe']:.2f}"
    metrics["monte_carlo"]     = mc
    metrics["mvo_strategy"]    = strategy

    return allocs, rb, metrics, weights


def build_allocation(profile, answers):
    """Full pipeline: behavioral adjust → DD → confidence score."""
    # Layer 2: Behavioral adjustment
    behavioral_profile, behavioral_flags = behavioral_risk_adjustment(answers, profile)

    corr_data = {}
    if DD_API_KEY:
        a,b,m,cd = build_portfolio_from_dd(profile, answers, behavioral_profile)
        if a:
            corr_data = cd or {}
        else:
            print("[DD] Falling back to static portfolio")
            a,b,m,cd = build_fallback_portfolio(profile, answers, behavioral_profile)
            corr_data = cd or {}
    else:
        a,b,m,cd = build_fallback_portfolio(profile, answers, behavioral_profile)
        corr_data = cd or {}

    # Layer 5: Confidence score
    confidence = compute_confidence_score(a, answers, behavioral_profile, behavioral_flags, corr_data)

    return a, b, m, behavioral_flags, behavioral_profile, confidence

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
def system_prompt(answers, report):
    allocs = report.get("allocations",[])
    m      = report.get("metrics",{})
    name   = f"{answers.get('first_name','')} {answers.get('last_name','')}".strip() or "Client"
    flags  = report.get("behavioral_flags",{})
    flag_str = "; ".join(k for k,v in flags.items() if isinstance(v,dict) and v.get("detected")) or "none"
    return f"""You are Barita, a warm and friendly professional Jamaican investment advisor bear mascot for Barita Investments Limited.
You speak in a friendly, encouraging, and professional tone. You use simple language but are clearly knowledgeable.
You are advising {name}, a {report.get('behavioral_profile', report.get('profile','Moderate'))} investor.

CLIENT PROFILE:
- Goal: {answers.get('primary_goal','')} | Withdrawals: {answers.get('withdrawal_time','')}
- Employment: {answers.get('employment_status','')} | Age: {answers.get('age','')}
- Earns: {answers.get('earn_currency','')} | Spends: {answers.get('spend_currency','')} | USD liabilities: {answers.get('usd_liabilities','')}
- Debt: {answers.get('debt_situation','')} | Runway: {answers.get('income_loss_runway','')}
- Inflation: {answers.get('inflation_impact','')} | Protection pref: {answers.get('inflation_protection','')}
- Style: {answers.get('invest_style','')} | Max loss: {answers.get('max_loss','')}
- Behavioral flags detected: {flag_str}
- Portfolio confidence score: {report.get('confidence',{}).get('score','—')}/100 ({report.get('confidence',{}).get('label','')})

PORTFOLIO: {' | '.join(f"{a['label']} ({a['ticker']}) {a['pct']}% [{a['class']}]" for a in allocs)}
METRICS: Return {m.get('expected_return','—')} | Vol {m.get('volatility','—')} | Sharpe {m.get('sharpe_ratio','—')}

Be warm, friendly, concise (150-250 words). Reference Jamaica. Flowing paragraphs only.
If behavioral flags were detected, acknowledge them gently and explain why the portfolio was adjusted."""

# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.route("/")
def index(): return send_file("public/landing.html")

@app.route("/app")
def dashboard(): return send_file("public/index.html")

@app.route("/questionnaire")
def questionnaire_page(): return send_file("public/questionnaire.html")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":"ok","service":"Barita Wealth Advisor",
        "dd_api":bool(DD_API_KEY),
        "openai":bool(OPENAI_API_KEY),
        "gemini":bool(GEMINI_API_KEY),
    })

@app.route("/analyse", methods=["POST"])
def analyse():
    user,err = verify_token(request)
    if err: return jsonify({"error":err}),401

    answers = request.get_json().get("answers",{})
    score,profile,profile_label,exp_level = score_answers(answers)
    allocations,risk_breakdown,metrics,behavioral_flags,behavioral_profile,confidence = build_allocation(profile, answers)
    name = f"{answers.get('first_name','')} {answers.get('last_name','')}".strip() or "Client"

    advisory, ai_provider = "", "none"
    try:
        port_str   = ", ".join(f"{a['label']} {a['pct']}%" for a in allocations)
        flag_notes = " ".join(v.get("note","") for v in behavioral_flags.values()
                              if isinstance(v,dict) and v.get("detected"))
        adv_prompt = (
            f"Write a warm, friendly personalised advisory note (200-280 words, flowing paragraphs, no headers) for {name.split()[0]}, a {behavioral_profile} investor.\n"
            f"Goal: {answers.get('primary_goal','')} | Withdrawals: {answers.get('withdrawal_time','')}\n"
            f"Earns: {answers.get('earn_currency','')} | Spends: {answers.get('spend_currency','')}\n"
            f"Debt: {answers.get('debt_situation','')} | Runway: {answers.get('income_loss_runway','')}\n"
            f"Inflation: {answers.get('inflation_impact','')} | Pref: {answers.get('inflation_protection','')}\n"
            f"Portfolio: {port_str}\n"
            f"Return: {metrics['expected_return']} | Vol: {metrics['volatility']} | Sharpe: {metrics['sharpe_ratio']}\n"
            f"Confidence score: {confidence['score']}/100 ({confidence['label']})\n"
            f"Behavioral notes: {flag_notes or 'None detected'}\n\n"
            f"Explain how their goal, currency, resilience, and inflation concern drove the weights. "
            f"If behavioral adjustments were made, mention them warmly. Address {name.split()[0]} by first name. Be Jamaica-specific."
        )
        advisory, ai_provider = call_ai(
            [{"role":"user","content":adv_prompt}],
            max_tokens=700,
            system="You are Barita, a warm friendly Jamaican investment advisor bear mascot for Barita Investments."
        )
    except Exception as e:
        advisory = f"Portfolio built successfully. Advisory unavailable: {e}"

    result = {
        "profile":            profile,
        "behavioral_profile": behavioral_profile,
        "profile_label":      profile_label,
        "exp_level":          exp_level,
        "score":              score,
        "allocations":        allocations,
        "risk_breakdown":     risk_breakdown,
        "metrics":            metrics,
        "monte_carlo":        metrics.get("monte_carlo", {}),
        "mvo_strategy":       metrics.get("mvo_strategy", "score_based"),
        "behavioral_flags":   behavioral_flags,
        "confidence":         confidence,
        "advisory_note":      advisory,
        "ai_provider":        ai_provider,
        "client_name":        name,
    }

    try:
        db.collection("sessions").document(user["uid"]).set({
            "answers":answers,"report":{k:v for k,v in result.items() if k!="allocations"},
            "allocations":allocations,"updated_at":firestore.SERVER_TIMESTAMP,
        })
        db.collection("users").document(user["uid"]).collection("reports").add({
            **{k:v for k,v in result.items() if k!="allocations"},
            "allocations":allocations,"created_at":firestore.SERVER_TIMESTAMP,
        })
    except Exception as e: print(f"Firestore error: {e}")

    return jsonify(result)

@app.route("/chat", methods=["POST"])
def chat():
    user,err = verify_token(request)
    if err: return jsonify({"error":err}),401
    data    = request.get_json()
    answers = data.get("answers",{})
    report  = data.get("report",{})
    history = data.get("history",[])
    message = data.get("message","")

    msgs = []
    for h in history[-8:]:
        if h.get("role")=="user": msgs.append({"role":"user","content":h["text"]})
        elif h.get("role")=="advisor" and h.get("text"): msgs.append({"role":"assistant","content":h["text"]})
    msgs.append({"role":"user","content":message})

    reply, provider = call_ai(msgs, max_tokens=600, system=system_prompt(answers, report))
    return jsonify({"reply":reply,"provider":provider})

@app.route("/chat_questionnaire", methods=["POST"])
def chat_questionnaire():
    """
    Interactive questionnaire chat endpoint.
    The bear advisor conducts the questionnaire conversationally,
    one question at a time, extracting answers from natural language.
    """
    user,err = verify_token(request)
    if err: return jsonify({"error":err}),401

    data        = request.get_json()
    user_message= data.get("message","")
    history     = data.get("history",[])
    answers_so_far = data.get("answers",{})
    stage       = data.get("stage","intro")  # intro | questionnaire | complete

    system = """You are Barita 🐻, a charming, encouraging bear wearing a business vest — Barita Investments' friendly AI advisor.
You guide investors through a questionnaire in a warm, conversational, game-tutorial style.
One question per message. Be enthusiastic. Use simple language. Make the investor feel safe and excited.
Light bear puns welcome: "pawsome!", "bear with me!", "I'm rooting for you!", "honey, that's a great answer!"

IMPORTANT: Always respond with ONLY valid JSON (no markdown, no extra text):
{
  "message": "Your warm response + the next single question (with answer options if applicable)",
  "extracted_answer": {"field_name": "value"} or {},
  "options": ["Option A", "Option B"] or null (for multiple-choice questions),
  "stage": "questionnaire" or "complete",
  "next_field": "field_name or null"
}

QUESTIONS (ask in order, skip already-answered ones from the context):
1. first_name — "What's your first name? I like to keep things personal! 🍯"
2. last_name — "And your last name?"
3. age — "How old are you? (Just the number is fine!)"
4. knowledge_level — "How would you describe your investing experience?" 
   options: ["I'm completely new to investing","I have basic knowledge but no real experience","I've been learning and have some experience","I have a lot of investing experience"]
5. primary_goal — "What's your #1 financial goal right now?"
   options: ["Wealth accumulation / growth","Retirement planning","Education funding","Property purchase","Income generation","Capital preservation","Emergency fund building"]
6. time_horizon — "How many years before you'd need to access this money? Just a rough estimate!"
   (store as text e.g. "5 years", "10+ years")
7. target_amount — "Do you have a specific dollar target in mind? E.g. 'double my money' or 'JMD 5 million' — or just say 'not sure'!"
   (store as text, open-ended)
8. withdrawal_time — "Over the NEXT 2 years, how much of the portfolio might you need to withdraw?"
   options: ["No withdrawals","Less than 10%","10-25%","More than 25%"]
9. drop_reaction — "If your portfolio dropped 20% in one month, what would you do? 😬"
   options: ["Sell everything to avoid further losses","Sell some to reduce losses","Wait for recovery","Invest more at lower prices"]
10. risk_comfort — "On a scale of 1–10, how much annual drawdown could you stomach before reconsidering your strategy? (1=very little, 10=totally fine with big swings)"
    (store as number string e.g. "6")
11. max_loss — "What's the MAXIMUM annual loss you could handle without changing plans?"
    options: ["Up to 10%","Up to 20%","Up to 40%","More than 40%"]
12. sector_view — "Do you have a strong view that any sector will outperform? E.g. 'I think tech will boom' or 'I trust local JMD assets' — totally optional!"
    (open-ended — feeds Black-Litterman views)
13. income_loss_runway — "If you lost your income tomorrow, how long could you live comfortably WITHOUT touching investments?"
    options: ["Less than 3 months","3-6 months","6-12 months","1-2 years","More than 2 years"]
14. debt_situation — "How would you describe your current debt situation?"
    options: ["Debt-free","Minor debt","Moderate debt","Significant debt"]
15. earn_currency — "What currency do you mainly earn in?"
    options: ["JMD only","USD only","Mostly JMD","Mostly USD","Equal amounts of JMD and USD"]
16. spend_currency — "What currency do you mainly spend in?"
    options: ["JMD only","USD only","Mostly JMD","Mostly USD","Equal amounts of JMD and USD"]
17. usd_liabilities — "Do you have any USD-denominated debts or liabilities?"
    options: ["None","Under USD $10K","USD $10K-$50K","USD $50K-$200K","Over USD $200K"]
18. inflation_impact — "How much does JMD inflation affect your daily costs?"
    options: ["Not sure","Minimal","Moderate","Significant","Severe"]
19. inflation_protection — "Do you want inflation protection built into your portfolio?"
    options: ["Not sure","Not necessary","Somewhat","Yes - strong focus"]
20. invest_style — "What's your preferred investing style?"
    options: ["Fully passive","Mostly passive","Balanced","Mostly active","Fully active"]
21. market_adjustment — "If market conditions shifted, would you be open to adjusting your portfolio?"
    options: ["No - keep it fixed","Yes - small changes","Yes - moderate changes","Yes - fully active"]
22. risk_relationship — "Which best describes your relationship with investment risk?"
    options: ["I worry a lot about losing money","I'm okay with small changes, but big losses stress me","I understand ups and downs and stay calm","I'm comfortable with big risks and see drops as opportunities"]
23. loss_vs_gain — "Which outcome would upset you MORE?"
    options: ["Missing a 20% gain","Suffering a 20% loss"]
24. performance_benchmark — "When checking your portfolio, what do you mainly compare it against?"
    options: ["The amount I originally invested","The overall increase in value (JMD gains)","My expected return","A market index","The rate of inflation"]

When ALL 24 fields are present in the answers context, set stage="complete" and give an excited closing message. Tell them you're building their portfolio now!"""

    msgs = []
    for h in history[-12:]:
        if h.get("role")=="user": msgs.append({"role":"user","content":h["text"]})
        elif h.get("role")=="bear" and h.get("text"): msgs.append({"role":"assistant","content":h["text"]})

    if not msgs and not user_message:
        # Opening message
        intro_msg = '{"message":"🐻 Pawsome to meet you! I\'m Barita, your friendly investment advisor bear from Barita Investments! 🎉\\n\\nI\'m going to guide you through building your very own personalised portfolio — step by step, question by question. Think of it like a game tutorial! No jargon, I promise. 🍯\\n\\nReady to start? First things first — **what\'s your first name?**", "extracted_answer": {}, "options": null, "stage": "questionnaire", "next_field": "first_name"}'
        return jsonify({"raw": intro_msg, "parsed": json.loads(intro_msg)})

    msgs.append({"role":"user","content":user_message})

    context = f"\nAnswers collected so far: {json.dumps(answers_so_far)}\nCurrent stage: {stage}"
    msgs.insert(0,{"role":"user","content":context})

    raw, provider = call_ai(msgs, max_tokens=500, system=system)

    # Parse JSON response
    try:
        # Strip markdown code blocks if present
        clean = raw.strip()
        if clean.startswith("```"): clean = clean.split("```")[1]
        if clean.startswith("json"): clean = clean[4:]
        parsed = json.loads(clean.strip())
    except Exception:
        parsed = {"message": raw, "extracted_answer": {}, "stage": stage, "next_field": None}

    return jsonify({"raw": raw, "parsed": parsed, "provider": provider})

@app.route("/generate_report", methods=["POST"])
def generate_report():
    user,err = verify_token(request)
    if err: return jsonify({"error":err}),401
    data    = request.get_json()
    answers = data.get("answers",{})
    report  = data.get("report",{})
    if not report or not report.get("allocations"):
        s,p,pl,el = score_answers(answers)
        a,b,m,bf,bp,conf = build_allocation(p,answers)
        report={"profile":p,"behavioral_profile":bp,"profile_label":pl,
                "allocations":a,"risk_breakdown":b,"metrics":m,
                "behavioral_flags":bf,"confidence":conf,"advisory_note":""}
    pdf=build_pdf(user,answers,report)
    nm=report.get("client_name","Client").replace(" ","_")
    return send_file(io.BytesIO(pdf),mimetype="application/pdf",as_attachment=True,
                     download_name=f"Barita_Report_{nm}_{datetime.now().strftime('%Y%m%d')}.pdf")

# ── PDF ───────────────────────────────────────────────────────────────────────
def build_pdf(user_info, answers, report):
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=2*cm,rightMargin=2*cm,topMargin=2*cm,bottomMargin=2*cm)
    story=[]
    TEAL=colors.HexColor("#0BB8A9"); NAVY=colors.HexColor("#1A2342"); LIGHT=colors.HexColor("#F0F4F8")
    BORD=colors.HexColor("#E4E9F0"); GREEN=colors.HexColor("#10B981"); RED=colors.HexColor("#EF4444")
    MUTED=colors.HexColor("#6B7A99"); AMBER=colors.HexColor("#F59E0B")
    body=ParagraphStyle("b",fontName="Helvetica",fontSize=10,textColor=NAVY,leading=15,spaceAfter=6)
    h2  =ParagraphStyle("h",fontName="Helvetica-Bold",fontSize=13,textColor=NAVY,spaceBefore=14,spaceAfter=6)
    sm  =ParagraphStyle("s",fontName="Helvetica",fontSize=9,textColor=MUTED,leading=13)
    ctr =ParagraphStyle("c",fontName="Helvetica-Bold",fontSize=11,textColor=NAVY,alignment=TA_CENTER)

    profile   =report.get("behavioral_profile") or report.get("profile","Moderate")
    beh_flags =report.get("behavioral_flags",{})
    confidence=report.get("confidence",{})
    metrics   =report.get("metrics",{}); allocs=report.get("allocations",[])
    advisory  =report.get("advisory_note","")
    cn=report.get("client_name") or f"{answers.get('first_name','')} {answers.get('last_name','')}".strip() or user_info.get("name","Client")
    email=user_info.get("email","")

    # Header
    hdr=Table([[Paragraph("BARITA INVESTMENTS LIMITED",ParagraphStyle("hh",fontName="Helvetica-Bold",fontSize=14,textColor=colors.white)),Paragraph(f"Portfolio Report<br/>{datetime.now().strftime('%B %d, %Y')}",ParagraphStyle("hs",fontName="Helvetica",fontSize=9,textColor=colors.white,alignment=TA_RIGHT))]],colWidths=["70%","30%"])
    hdr.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),NAVY),("PADDING",(0,0),(-1,-1),12),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story+=[hdr,Spacer(1,12),Paragraph(f"Prepared for: <b>{cn}</b> | {email}",body),HRFlowable(width="100%",thickness=1,color=BORD),Spacer(1,10)]

    # Confidence score box
    conf_score=confidence.get("score","—"); conf_grade=confidence.get("grade","—"); conf_label=confidence.get("label","")
    story.append(Paragraph("Portfolio Confidence Score",h2))
    ct=Table([[Paragraph(f"<b>{conf_score}/100</b>",ParagraphStyle("cs",fontName="Helvetica-Bold",fontSize=28,textColor=TEAL,alignment=TA_CENTER)),Paragraph(f"Grade: <b>{conf_grade}</b><br/>{conf_label}",ParagraphStyle("cg",fontName="Helvetica-Bold",fontSize=13,textColor=NAVY)),Paragraph(f"Profile: <b>{profile}</b>",ParagraphStyle("cp",fontName="Helvetica-Bold",fontSize=13,textColor=NAVY))]],colWidths=["25%","40%","35%"])
    ct.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),LIGHT),("PADDING",(0,0),(-1,-1),14),("GRID",(0,0),(-1,-1),0.5,BORD),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story+=[ct,Spacer(1,10)]

    # Behavioral flags
    active_flags=[v for v in beh_flags.values() if isinstance(v,dict) and v.get("detected")]
    if active_flags:
        story.append(Paragraph("Behavioral Insights",h2))
        for f in active_flags:
            story.append(Paragraph(f"⚠ {f.get('note','')}",ParagraphStyle("fl",fontName="Helvetica",fontSize=9,textColor=colors.HexColor("#92400E"),leading=13,spaceAfter=4)))
        story.append(Spacer(1,8))

    # Investor profile
    story.append(Paragraph("Investor Profile",h2))
    pt=Table([["Risk Profile",profile,"Level",report.get("profile_label","")],["Primary Goal",answers.get("primary_goal","—"),"Withdrawals",answers.get("withdrawal_time","—")],["Employment",answers.get("employment_status","—"),"Earn (CCY)",answers.get("earn_currency","—")],["Debt",answers.get("debt_situation","—"),"Age",answers.get("age","—")],["Inflation",answers.get("inflation_impact","—"),"Inf. Pref.",answers.get("inflation_protection","—")],["USD Liabilities",answers.get("usd_liabilities","—"),"Style",answers.get("invest_style","—")]],colWidths=["20%","30%","20%","30%"])
    pt.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),"Helvetica"),("FONTSIZE",(0,0),(-1,-1),9),("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),("FONTNAME",(2,0),(2,-1),"Helvetica-Bold"),("TEXTCOLOR",(0,0),(0,-1),MUTED),("TEXTCOLOR",(2,0),(2,-1),MUTED),("ROWBACKGROUNDS",(0,0),(-1,-1),[LIGHT,colors.white]),("PADDING",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),0.5,BORD),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story+=[pt,Spacer(1,12)]

    # Metrics
    story.append(Paragraph("Portfolio Metrics",h2))
    mt=Table([["Expected Return","Annualised Volatility","Sharpe Ratio"],[metrics.get("expected_return","—"),metrics.get("volatility","—"),metrics.get("sharpe_ratio","—")]],colWidths=["33%","33%","34%"])
    mt.setStyle(TableStyle([("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,0),9),("FONTSIZE",(0,1),(-1,1),18),("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),("TEXTCOLOR",(0,0),(-1,0),MUTED),("TEXTCOLOR",(0,1),(0,1),GREEN),("TEXTCOLOR",(1,1),(1,1),RED),("TEXTCOLOR",(2,1),(2,1),TEAL),("BACKGROUND",(0,0),(-1,-1),LIGHT),("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("PADDING",(0,0),(-1,-1),12),("GRID",(0,0),(-1,-1),0.5,BORD)]))
    story+=[mt,Spacer(1,12)]

    # Allocation
    story.append(Paragraph("Asset Allocation",h2))
    ar=[[Paragraph(x,ParagraphStyle("th",fontName="Helvetica-Bold",fontSize=9,textColor=MUTED)) for x in ["Instrument","Ticker","Class","Weight","Diversif. Contribution"]]]
    for a in allocs:
        cp=a.get("corr_penalty",0)
        div_label="High" if cp<0.2 else ("Medium" if cp<0.4 else "Low")
        ar.append([Paragraph(a["label"],ParagraphStyle("ac",fontName="Helvetica-Bold",fontSize=9,textColor=NAVY)),Paragraph(a["ticker"],ParagraphStyle("at",fontName="Helvetica",fontSize=8,textColor=MUTED)),Paragraph(a.get("class",""),ParagraphStyle("ac2",fontName="Helvetica",fontSize=9,textColor=NAVY)),Paragraph(f"<b>{a['pct']}%</b>",ParagraphStyle("ap",fontName="Helvetica-Bold",fontSize=10,textColor=TEAL,alignment=TA_RIGHT)),Paragraph(div_label,ParagraphStyle("dv",fontName="Helvetica",fontSize=9,textColor=GREEN if div_label=="High" else (AMBER if div_label=="Medium" else RED)))])
    at=Table(ar,colWidths=["28%","23%","18%","12%","19%"])
    at.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),("ROWBACKGROUNDS",(0,1),(-1,-1),[LIGHT,colors.white]),("GRID",(0,0),(-1,-1),0.5,BORD),("PADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story+=[at,Spacer(1,12)]

    # Advisory
    if advisory:
        story+=[Paragraph("Advisor Commentary",h2),HRFlowable(width="100%",thickness=1.5,color=TEAL),Spacer(1,8)]
        for para in advisory.split("\n\n"):
            if para.strip(): story.append(Paragraph(para.strip(),body))

    story+=[Spacer(1,8),HRFlowable(width="100%",thickness=0.5,color=BORD),Spacer(1,6),Paragraph("This report was generated for the Barita SOC 2026 using data by Dimension Depths. Not real financial advice. © 2026 Barita Investments Limited.",sm)]
    doc.build(story)
    return buf.getvalue()

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)