"""
BARITA WEALTH ADVISOR — app.py
Flask Backend | Deterministic Barita Bear Advisor
Dimension Depths Integration | Correlation-Aware Diversification
Behavioral Risk Adjustment | MVO + Black-Litterman-style Tilting + HRP
10,000-path Monte Carlo Goal Validation | Confidence Score | PDF Reporting
"""

import os, io, json, math
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
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")
DD_API_KEY               = os.environ.get("DIMENSION_DEPTHS_API_KEY", "")
DD_BASE_URL              = os.environ.get("DIMENSION_DEPTHS_BASE_URL",
    "https://dimension-depths-v2-production.up.railway.app").rstrip("/")

app = Flask(__name__, static_folder="public", static_url_path="")
CORS(app, origins=["*"])
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# ── FIREBASE ──────────────────────────────────────────────────────────────────
# Firebase is used for login verification and optional report/session persistence.
# Firestore failures should NEVER block portfolio generation during demo.
db = None
try:
    if FIREBASE_SERVICE_ACCOUNT:
        cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT))
    else:
        cred = credentials.Certificate("serviceAccountKey.json")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    print("[Firebase] Admin SDK ready")
except Exception as e:
    print(f"[Firebase] Admin init failed/skipped: {e}")
    db = None

# ── DETERMINISTIC ADVISORY LAYER ─────────────────────────────────────────────
# OpenAI/Gemini are intentionally not used in the core demo path because quota
# failures can make the product appear broken. The system remains an advisor by
# using dynamic templates driven by the real portfolio/risk engine.

def fmt_money(value):
    try:
        return "${:,.0f}".format(float(value))
    except Exception:
        return str(value or "—")


def generate_template_advisory_note(answers, report):
    """Personalised advisory note created from real engine outputs, no API quota needed."""
    name = (answers.get("first_name") or "friend").strip()
    profile = report.get("behavioral_profile") or report.get("profile") or "Moderate"
    raw_profile = report.get("profile") or profile
    metrics = report.get("metrics", {}) or {}
    mc = report.get("monte_carlo", {}) or metrics.get("monte_carlo", {}) or {}
    method = metrics.get("optimization_method") or report.get("optimization_method") or "the selected optimisation method"
    confidence = report.get("confidence", {}) or {}
    flags = report.get("behavioral_flags", {}) or {}
    class_alloc = report.get("class_allocation") or build_class_allocation(report.get("allocations", []))

    class_phrase = ", ".join(f"{x.get('class')} {x.get('pct')}%" for x in class_alloc) or "a diversified mix across asset classes"

    active_flags = [
        v.get("note", "")
        for v in flags.values()
        if isinstance(v, dict) and v.get("detected") and v.get("note")
    ]

    adjustment_sentence = ""
    if raw_profile != profile:
        adjustment_sentence = (
            f"Your raw score pointed to {raw_profile}, but the behavioural suitability layer adjusted this to {profile} "
            "so the recommendation better reflects how you may actually react during market stress. "
        )
    elif active_flags:
        adjustment_sentence = "The behavioural layer detected useful signals, so the recommendation includes extra suitability safeguards. "

    mc_sentence = ""
    if mc:
        mc_sentence = (
            f"The Monte Carlo engine tested {mc.get('method_note', str(mc.get('simulations','thousands')) + ' simulations')} and estimated a "
            f"{mc.get('prob_goal', mc.get('prob_double', '—'))}% probability of reaching the stated goal, "
            f"with a median outcome near {fmt_money(mc.get('median_final'))}. "
        )

    return (
        f"{name}, based on your answers, Barita Bear classified you as a {profile} investor. "
        f"Your main goal is {answers.get('primary_goal', 'growth and stability')}, with a time horizon of "
        f"{answers.get('time_horizon', 'not specified')}. {adjustment_sentence}"
        f"The portfolio was selected using {method}, after comparing risk-adjusted return, volatility, diversification, "
        f"and goal suitability. The final mix is {class_phrase}, which helps balance your return target with your stated "
        f"loss tolerance, liquidity needs, currency exposure, and inflation concerns in the Jamaican market. "
        f"Expected return is {metrics.get('expected_return', '—')}, volatility is {metrics.get('volatility', '—')}, "
        f"and the Sharpe ratio is {metrics.get('sharpe_ratio', '—')}. {mc_sentence}"
        f"The confidence score is {confidence.get('score', '—')}/100 ({confidence.get('label', 'profile match')}). "
        "This is not real financial advice, but for the Barita SOC challenge it shows a data-driven, risk-aware recommendation."
    )
def ask_groq(message, answers, report):
    """Groq-powered advisor response with safe investing-only guardrails."""
    if not GROQ_API_KEY:
        return None

    allocations = report.get("allocations", []) or []
    metrics = report.get("metrics", {}) or {}
    profile = report.get("behavioral_profile") or report.get("profile") or "Moderate"

    allowed_keywords = [
        "portfolio", "investment", "invest", "risk", "return", "volatility",
        "monte carlo", "asset", "allocation", "stocks", "bonds", "equity",
        "fixed income", "cash", "wealth", "goal", "money", "barita",
        "sharpe", "rebalance", "inflation", "currency", "jmd", "usd"
    ]

    msg_l = str(message or "").lower()

    if not any(k in msg_l for k in allowed_keywords):
        return {
            "raise_error": True,
            "reply": "🐻 I’m built to help with investing, portfolios, risk, returns, allocation, and your Barita report. Could you rephrase your question around your investment portfolio?"
        }

    context = {
        "profile": profile,
        "metrics": metrics,
        "allocations": allocations[:8],
        "answers": answers,
        "confidence": report.get("confidence", {}),
        "monte_carlo": report.get("monte_carlo", {})
    }

    prompt = f"""
You are Barita Bear, a warm Jamaican investment advisor chatbot for a student fintech prototype.

Only answer questions about investing, portfolio construction, risk, allocation, Monte Carlo, returns, and the user's report.

If the user asks something outside investing, politely ask them to rephrase around investing.

Use this portfolio context:
{json.dumps(context, indent=2)}

User question:
{message}

Answer in a friendly, concise way. Use simple language for beginner investors.
Do not claim this is real financial advice.
"""

    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful investing assistant. Stay within investing and portfolio advice only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.4,
                "max_tokens": 350
            },
            timeout=20
        )

        res.raise_for_status()
        data = res.json()
        reply = data["choices"][0]["message"]["content"].strip()

        return {
            "raise_error": False,
            "reply": reply
        }

    except Exception as e:
        print(f"[Groq] failed: {e}")
        return None

def generate_chat_reply(message, answers, report):
    """Deterministic post-portfolio advisor chat for stable demos."""
    msg = str(message or "").lower()
    metrics = report.get("metrics", {}) or {}
    mc = report.get("monte_carlo", {}) or metrics.get("monte_carlo", {}) or {}
    allocs = report.get("allocations", []) or []
    profile = report.get("behavioral_profile") or report.get("profile") or "Moderate"

    if "why" in msg or "chosen" in msg or "recommend" in msg or "asset" in msg:
        top = allocs[:3]
        top_text = "; ".join(
            f"{a.get('ticker')} at {a.get('pct')}% because {a.get('rationale','it improves portfolio fit')}"
            for a in top
        )
        return f"I chose this portfolio because it fits your {profile} profile while balancing return, volatility, and diversification. Top drivers: {top_text}."

    if "monte" in msg or "goal" in msg or "probability" in msg or "simulation" in msg:
        return f"The Monte Carlo validation tested future market scenarios. Your estimated goal probability is {mc.get('prob_goal', mc.get('prob_double','—'))}%, with median final wealth around {fmt_money(mc.get('median_final'))}."

    if "risk" in msg or "volatility" in msg or "loss" in msg:
        return f"Your portfolio volatility is {metrics.get('volatility','—')}. For a {profile} investor, that shows the expected level of ups and downs while targeting an expected return of {metrics.get('expected_return','—')}."

    if "allocation" in msg or "money" in msg or "where" in msg:
        rows = ", ".join(f"{a.get('ticker')} {a.get('pct')}%" for a in allocs[:8])
        return f"Your money is allocated across these main instruments: {rows}. The mix was selected from Dimension Depths assets using expected return, volatility, covariance, and diversification checks."

    if "method" in msg or "optimizer" in msg or "mvo" in msg or "hrp" in msg:
        candidates = metrics.get("candidate_portfolios", [])
        cand_text = "; ".join(
            f"{c.get('method')}: return {c.get('expected_return')}%, vol {c.get('volatility')}%, Sharpe {c.get('sharpe')}"
            for c in candidates[:4]
        )
        return f"The engine compared multiple optimisation methods before selecting the final portfolio. {cand_text}. The selected method was {metrics.get('optimization_method','—')}."

    return generate_template_advisory_note(answers, report)

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
_cached_fields = None

def dd_get(endpoint, params=None):
    """Safe GET wrapper for Dimension Depths endpoints."""
    try:
        endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        r = requests.get(f"{DD_BASE_URL}{endpoint}", headers=DD_HEADERS,
                         params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[DD] {endpoint}: {e}")
        return None

def extract_dd_list(payload):
    """Dimension Depths sometimes returns a list directly and sometimes {data:[...]} or {results:[...]}.
    This normalises those possible shapes into one Python list."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("results") or []
        return rows if isinstance(rows, list) else []
    return []

def fetch_asset_fields():
    """Fetch all available asset fields from /api/soc/info/ so the optimiser receives the richest dataset."""
    global _cached_fields
    if _cached_fields is not None:
        return _cached_fields

    info = dd_get("/api/soc/info/")
    fields = []
    try:
        data = info.get("data", info) if isinstance(info, dict) else {}
        fields = data.get("available_asset_fields", []) or []
    except Exception as e:
        print(f"[DD] Could not parse asset fields: {e}")

    # Fallback to the fields this portfolio engine actually uses.
    if not fields:
        fields = [
            "ticker", "name", "super_class", "asset_class", "sub_class", "subclass",
            "currency", "total_expected_return", "expected_return", "volatility_ann",
            "volatility", "income_yield_ann", "sharpe_ratio", "semi_deviation_ann",
            "skewness", "excess_kurtosis"
        ]

    _cached_fields = ",".join(fields)
    print(f"[DD] Using {len(fields)} asset fields")
    return _cached_fields

def fetch_all_assets():
    """Fetch the complete SOC asset universe with pagination.
    This is stronger than a single /assets call because the API may return only the first page by default."""
    global _cached_assets
    if _cached_assets is not None:
        return _cached_assets

    if not DD_API_KEY:
        print("[DD] Missing API key — using fallback portfolio")
        _cached_assets = []
        return _cached_assets

    all_assets = []
    limit = 100
    offset = 0
    fields = fetch_asset_fields()

    while True:
        params = {"limit": limit, "offset": offset}
        if fields:
            params["fields"] = fields

        payload = dd_get("/api/soc/assets/", params=params)
        rows = extract_dd_list(payload)
        if not rows:
            break

        all_assets.extend(rows)

        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        returned = meta.get("returned_count", len(rows))
        total = meta.get("total_count") or meta.get("count")

        # Stop if this was the last page. Supports both returned_count and total_count formats.
        if returned < limit or (total is not None and len(all_assets) >= int(total)):
            break

        offset += limit

    _cached_assets = all_assets
    print(f"[DD] Fetched {len(_cached_assets)} assets across paginated SOC universe")
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

    # Added scoring variables from the design document.
    horizon_years = parse_years(answers.get("time_horizon", ""))
    if horizon_years >= 10: s += 3
    elif horizon_years >= 5: s += 2
    elif horizon_years >= 2: s += 1
    else: s += 0

    try:
        rc = float(str(answers.get("risk_comfort", "5")).strip())
    except Exception:
        rc = 5
    if rc >= 8: s += 2
    elif rc >= 5: s += 1
    else: s += 0

    max_score = 35.0
    pct = s / max_score
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


def parse_years(value):
    """Extract an approximate investment horizon in years from text."""
    if value is None: return 0.0
    txt = str(value).lower().replace("+", "")
    nums = []
    import re
    for n in re.findall(r"\d+(?:\.\d+)?", txt):
        try: nums.append(float(n))
        except: pass
    if not nums: return 0.0
    years = max(nums)
    if "month" in txt: years = years / 12.0
    return years


def asset_rationale(asset, profile, ctx):
    """Plain-English reason an asset/class fits the user's answers."""
    ac = classify_asset(asset)
    bits = []
    if ac in ("Cash", "Fixed Income") and profile == "Conservative":
        bits.append("supports capital protection and smoother returns")
    if ac == "Equity" and profile == "Aggressive":
        bits.append("adds higher long-term growth potential")
    if ac == "Equity" and profile == "Moderate":
        bits.append("adds measured growth while keeping balance")
    if ac == "Cash" and ctx.get("horizon_liquidity_need", 0) >= 0.5:
        bits.append("keeps liquidity available for possible withdrawals")
    if ac in ("Real Estate", "Commodities", "Equity") and ctx.get("inflation_hedge_need", 0) >= 1:
        bits.append("helps hedge inflation pressure")
    if "USD" in (asset.get("ticker", "") or "").upper() and ctx.get("usd_bias", 0) > 0.5:
        bits.append("matches your USD exposure")
    if not bits:
        bits.append("improves diversification within your risk profile")
    return "; ".join(bits).capitalize() + "."


def build_explainability_summary(answers, profile, behavioral_profile, flags, metrics):
    adjusted = profile != behavioral_profile
    flag_names = [k.replace("_", " ") for k, v in flags.items() if isinstance(v, dict) and v.get("detected")]
    parts = [
        f"Raw questionnaire scoring mapped the client to {profile}.",
        f"The behavioural layer {'adjusted this to ' + behavioral_profile if adjusted else 'confirmed the same profile'}.",
        f"Detected behavioural signals: {', '.join(flag_names) if flag_names else 'none'}.",
        f"The optimiser selected assets using expected return, volatility, Sharpe ratio, liquidity need, currency exposure, inflation preference, and diversification/correlation penalties.",
        f"Portfolio metrics: expected return {metrics.get('expected_return','—')}, volatility {metrics.get('volatility','—')}, Sharpe {metrics.get('sharpe_ratio','—')}.",
    ]
    return " ".join(parts)

# ── CLIENT CONTEXT ────────────────────────────────────────────────────────────
def derive_client_context(answers):
    ctx = {}
    ctx["primary_goal"] = answers.get("primary_goal", "")
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

    # New design-document fields
    ctx["time_horizon"] = answers.get("time_horizon", "")
    ctx["time_horizon_years"] = parse_years(answers.get("time_horizon", ""))
    try:
        ctx["risk_comfort_score"] = float(str(answers.get("risk_comfort", "5")).strip())
    except Exception:
        ctx["risk_comfort_score"] = 5.0
    ctx["sector_view"] = answers.get("sector_view", "")
    ctx["target_amount"] = answers.get("target_amount", "")

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

def normalise_matrix_payload(payload):
    """Normalise DD matrix payloads into {row_ticker: {col_ticker: value}}."""
    if not payload or not isinstance(payload, dict):
        return {}
    data = payload.get("data", payload)
    if isinstance(data, dict):
        if isinstance(data.get("values"), list):
            rows = data.get("index") or data.get("rows") or data.get("left") or []
            cols = data.get("columns") or data.get("cols") or data.get("right") or rows
            values = data.get("values") or []
            if rows and cols:
                out = {}
                for i, r in enumerate(rows):
                    out[str(r)] = {}
                    for j, c in enumerate(cols):
                        try:
                            out[str(r)][str(c)] = float(values[i][j])
                        except Exception:
                            out[str(r)][str(c)] = 0.0
                return out
        matrix = data.get("matrix") or data
        if isinstance(matrix, dict):
            return matrix
    return {}


def get_correlation(corr_data, ticker_a, ticker_b):
    """Extract correlation between two assets from DD correlation matrix."""
    matrix = normalise_matrix_payload(corr_data)
    row = matrix.get(ticker_a, {})
    if isinstance(row, dict):
        try:
            return float(row.get(ticker_b, 0.0))
        except Exception:
            return 0.0
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

    # Explicit sector/client views add a small Black-Litterman-style tilt without overpowering risk controls.
    sv = str(ctx.get("sector_view", "")).lower()
    nm = (asset.get("name") or "").lower()
    if sv:
        if any(word in sv for word in ["tech", "technology", "global"]) and ("tech" in nm or "global" in nm or "usd" in ticker):
            sc += 0.4
        if any(word in sv for word in ["local", "jamaica", "jmd"]) and "USD" not in ticker:
            sc += 0.3
        if any(word in sv for word in ["property", "real estate", "reit"]) and ac == "Real Estate":
            sc += 0.5

    horizon = ctx.get("time_horizon_years", 0)
    comfort = ctx.get("risk_comfort_score", 5)
    if horizon >= 7 and comfort >= 6 and ac == "Equity":
        sc += 0.4
    elif horizon and horizon < 2 and ac in ("Cash", "Fixed Income"):
        sc += 0.5

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
            "rationale":       asset_rationale(a, profile, ctx),
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
    key_fields = ["first_name","last_name","age","knowledge_level","primary_goal","time_horizon",
                  "target_amount","withdrawal_time","drop_reaction","risk_comfort","max_loss",
                  "sector_view","income_loss_runway","debt_situation","earn_currency",
                  "spend_currency","usd_liabilities","inflation_impact","inflation_protection",
                  "invest_style","market_adjustment","risk_relationship","loss_vs_gain",
                  "performance_benchmark"]
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
            cm  = normalise_matrix_payload(cov)
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

def pretty_asset_name(asset, idx=0):

    cls = classify_asset(asset)

    names = {
        "Equity": [
            "Caribbean Growth Equity Fund",
            "Regional Blue Chip Equity Fund",
            "Global Expansion Equity Fund",
            "Dividend Growth Equity Fund"
        ],

        "Fixed Income": [
            "Income Stability Bond Fund",
            "Government Income Fund",
            "Capital Preservation Bond Fund"
        ],

        "Cash": [
            "High Liquidity Money Market Fund"
        ],

        "Real Estate": [
            "Real Estate Income Trust"
        ]
    }

    options = names.get(
        cls,
        ["Diversified Investment Fund"]
    )

    return options[idx % len(options)]

    
# ── FULL DIMENSIONS DEPTH PIPELINE ──────────────────────────────────────────────────────────
def build_portfolio_from_dd(profile, answers, behavioral_profile=None):
    effective_profile = behavioral_profile or profile

    all_assets = fetch_all_assets()

    REAL_TICKERS = {
    "NCBFG","JMMBGL","VMIL","GK","WISYNCO","CAR",
    "QQQ","XLK","VGT","EEM","IEMG","VWO",
    "TBILLUSD","TBILL-JMD","GOJ2037","GOJ2029",
    "PROVEN","SPY"
}

    all_assets = [
        a for a in all_assets
        if (a.get("ticker") or "").replace(" ", "").replace("-", "").upper()
        in {t.replace(" ", "").replace("-", "").upper() for t in REAL_TICKERS}
    ]

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

    print("[DD] Fetching covariance...")
    cov = fetch_covariance()
    print("[DD] Covariance fetched:", type(cov))

    # Try MVO first (score-based selection already done)
    primary_goal = answers.get("primary_goal", "Wealth accumulation / growth")

    print("[DD] Starting MVO...")
    mvo_allocs, mvo_rb, mvo_metrics, mvo_w = build_portfolio_with_mvo(
        selected, effective_profile, primary_goal, cov, ctx, answers
    )
    print("[DD] MVO done", flush=True)    

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
        raw=[{"label":"JMD T-Bills","ticker":"TBILL-JMD","pct":25,"color":"#10B981","class":"Cash"},
              {"label":"USD T-Bills","ticker":"TBILL-USD","pct":15,"color":"#2563EB","class":"Cash"},
              {"label":"Short Gov Bonds","ticker":"GOJ 2029","pct":25,"color":"#B80B0B","class":"Fixed Income"},
              {"label":"Long Gov Bonds","ticker":"GOJ 2037","pct":20,"color":"#B713AC","class":"Fixed Income"},
              {"label":"Real Estate Fund","ticker":"PROVEN REIT","pct":10,"color":"#FB923C","class":"Real Estate"},
              {"label":"Domestic Defensives","ticker":"GK / WISYNCO","pct":5,"color":"#A78BFA","class":"Equity"}]
        metrics={"expected_return":"7.4%","volatility":"4.2%","sharpe_ratio":"1.41"}
    elif effective_profile=="Moderate":
        raw=[{"label":"Short Gov Bonds","ticker":"GOJ 2029","pct":18,"color":"#0BB8A9","class":"Fixed Income"},
             {"label":"Long Gov Bonds","ticker":"GOJ 2037","pct":12,"color":"#38BDF8","class":"Fixed Income"},
             {"label":"Corporate Bonds","ticker":"Barita Bond Fund","pct":10,"color":"#FBBF24","class":"Fixed Income"},
             {"label":"Domestic Financials","ticker":"NCBFG / JMMBGL / VMIL","pct":15,"color":"#3B82F6","class":"Equity"},
             {"label":"Domestic Defensives","ticker":"GK / WISYNCO / CAR","pct":15,"color":"#8B5CF6","class":"Equity"},
             {"label":"Global Tech Equity","ticker":"QQQ / XLK / VGT","pct":15,"color":"#EC4899","class":"Equity"},
             {"label":"Real Estate Fund","ticker":"PROVEN REIT","pct":10,"color":"#FB923C","class":"Real Estate"},
             {"label":"Alt Investments","ticker":"Infrastructure / Gold ETF","pct":5,"color":"#6B7280","class":"Alternatives"}]
        metrics={"expected_return":"11.8%","volatility":"9.6%","sharpe_ratio":"0.97"}
    else:
        raw=[{"label":"Domestic Financials","ticker":"NCBFG / JMMBGL / VMIL","pct":18,"color":"#3B82F6","class":"Equity"},
             {"label":"Domestic Cyclicals","ticker":"GK / LASM / WISYNCO","pct":14,"color":"#EF4444","class":"Equity"},
             {"label":"Global Tech Equity","ticker":"QQQ / XLK / VGT","pct":20,"color":"#8B5CF6","class":"Equity"},
             {"label":"Emerging Markets","ticker":"EEM / IEMG / VWO","pct":15,"color":"#06B6D4","class":"Equity"},
             {"label":"Corporate Bonds","ticker":"Barita Bond Fund","pct":12,"color":"#FBBF24","class":"Fixed Income"},
             {"label":"Real Estate Fund","ticker":"PROVEN REIT","pct":10,"color":"#FB923C","class":"Real Estate"},
             {"label":"Alt Investments","ticker":"Gold / Infrastructure","pct":8,"color":"#6B7280","class":"Alternatives"},
             {"label":"JMD T-Bills","ticker":"GOJ T-Bills","pct":3,"color":"#10B981","class":"Cash"},]
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
    cov_matrix = normalise_matrix_payload(cov_data)

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


def apply_mvo_weights(assets_list, weights_arr, cov_data, profile="Moderate", ctx=None):
    """Convert MVO weight array back to allocation dicts."""
    ctx = ctx or {}
    out = []
    for i, a in enumerate(assets_list):
        ac = classify_asset(a)
        out.append({
            "label":           a.get("ticker") or a.get("name", f"Asset {i+1}"),
            "ticker":          a.get("ticker", "—"),
            "pct":             round(float(weights_arr[i]) * 100, 1),
            "color":           CLASS_COLORS.get(ac, "#6B7280"),
            "class":           ac,
            "expected_return": a.get("total_expected_return") or a.get("expected_return"),
            "volatility":      a.get("volatility_ann") or a.get("volatility"),
            "sharpe_ratio":    a.get("sharpe_ratio"),
            "corr_penalty":    round(a.get("_corr_penalty", 0), 3),
            "rationale":       asset_rationale(a, profile, ctx),
        })
    # Fix rounding
    total = sum(x["pct"] for x in out)
    if out and abs(total - 100) > 0.05:
        out[0]["pct"] = round(out[0]["pct"] + (100 - total), 1)
    out.sort(key=lambda x: -x["pct"])
    return out




# ═══════════════════════════════════════════════════════════════════════════════
#  ADVANCED OPTIMISATION LAYER: BLACK-LITTERMAN TILT + HRP + METHOD SELECTION
# ═══════════════════════════════════════════════════════════════════════════════

def regularize_covariance(sigma):
    """Make covariance matrix symmetric and numerically stable."""
    sigma = np.asarray(sigma, dtype=float)
    sigma = np.nan_to_num(sigma, nan=0.0, posinf=0.0, neginf=0.0)
    sigma = (sigma + sigma.T) / 2.0
    try:
        min_eig = np.linalg.eigvalsh(sigma).min()
        if min_eig < 1e-8:
            sigma += (abs(min_eig) + 1e-6) * np.eye(sigma.shape[0])
    except Exception:
        sigma += 1e-6 * np.eye(sigma.shape[0])
    return sigma


def apply_black_litterman_tilt(mu, assets_list, answers, ctx):
    """
    Lightweight Black-Litterman-style view blending.
    We do not assume market caps are available in Dimension Depths, so we use the
    DD expected return vector as the prior and blend in soft client views from the
    questionnaire. This stabilises personalisation without letting subjective views
    dominate the optimiser.
    """
    mu = np.asarray(mu, dtype=float).copy()
    prior = mu.copy()
    view = np.zeros_like(mu)

    sector_view = str(answers.get("sector_view") or ctx.get("sector_view") or "").lower()
    goal = answers.get("primary_goal", "") or ctx.get("primary_goal", "")
    inflation_need = ctx.get("inflation_hedge_need", 0)
    usd_bias = ctx.get("usd_bias", 0)

    for i, a in enumerate(assets_list):
        ac = classify_asset(a)
        name = (a.get("name") or "").lower()
        ticker = (a.get("ticker") or "").upper()

        # User views: small active tilts only.
        if sector_view and sector_view not in ("not sure", "none", "no"):
            if any(w in sector_view for w in ["tech", "technology", "global"]):
                if "tech" in name or "global" in name or "USD" in ticker:
                    view[i] += 0.015
            if any(w in sector_view for w in ["local", "jamaica", "jmd"]):
                if "USD" not in ticker:
                    view[i] += 0.010
            if any(w in sector_view for w in ["property", "real estate", "reit"]):
                if ac == "Real Estate":
                    view[i] += 0.012

        # Goal-based views: growth likes equity, income likes yield assets.
        if goal == "Wealth accumulation / growth" and ac == "Equity":
            view[i] += 0.006
        if goal in ("Income generation", "Capital preservation", "Emergency fund building") and ac in ("Cash", "Fixed Income"):
            view[i] += 0.006

        # Macro/currency preferences.
        if inflation_need >= 1.0 and ac in ("Real Estate", "Commodities", "Equity"):
            view[i] += 0.006
        if usd_bias > 0.5 and "USD" in ticker:
            view[i] += 0.006

    # Confidence: strong enough to personalise, weak enough to avoid overfitting.
    confidence = 0.35
    blended = (1 - confidence) * prior + confidence * (prior + view)
    return np.clip(blended, -0.50, 0.80)


def covariance_to_correlation(sigma):
    sigma = regularize_covariance(sigma)
    diag = np.sqrt(np.maximum(np.diag(sigma), 1e-12))
    corr = sigma / np.outer(diag, diag)
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    np.fill_diagonal(corr, 1.0)
    return np.clip(corr, -1.0, 1.0)


def get_quasi_diag(link):
    """Sort clustered items by hierarchical tree order."""
    link = link.astype(int)
    sort_ix = [link[-1, 0], link[-1, 1]]
    num_items = link[-1, 3]
    while any(i >= num_items for i in sort_ix):
        new_sort_ix = []
        for i in sort_ix:
            if i < num_items:
                new_sort_ix.append(i)
            else:
                new_sort_ix.extend([link[i - int(num_items), 0], link[i - int(num_items), 1]])
        sort_ix = new_sort_ix
    return list(map(int, sort_ix))


def cluster_variance(cov, cluster_items):
    sub_cov = cov[np.ix_(cluster_items, cluster_items)]
    inv_diag = 1.0 / np.maximum(np.diag(sub_cov), 1e-12)
    weights = inv_diag / inv_diag.sum()
    return float(np.dot(weights, np.dot(sub_cov, weights)))


def hrp_weights_from_covariance(sigma):
    """
    Hierarchical Risk Parity: clusters correlated assets and allocates by risk.
    Used as a robust diversification benchmark/complement to MVO.
    """
    try:
        from scipy.cluster.hierarchy import linkage
        from scipy.spatial.distance import squareform
    except Exception as e:
        print(f"[HRP] scipy clustering unavailable: {e}")
        return None

    cov = regularize_covariance(sigma)
    n = cov.shape[0]
    if n < 2:
        return np.ones(n) / n

    corr = covariance_to_correlation(cov)
    dist = np.sqrt(np.maximum((1 - corr) / 2, 0))
    condensed = squareform(dist, checks=False)
    link = linkage(condensed, method="single")
    sort_ix = get_quasi_diag(link)

    weights = np.ones(n)
    clusters = [sort_ix]
    while clusters:
        cluster = clusters.pop(0)
        if len(cluster) <= 1:
            continue
        split = len(cluster) // 2
        left, right = cluster[:split], cluster[split:]
        var_left = cluster_variance(cov, left)
        var_right = cluster_variance(cov, right)
        alpha = 1 - var_left / (var_left + var_right) if (var_left + var_right) > 0 else 0.5
        weights[left] *= alpha
        weights[right] *= (1 - alpha)
        clusters += [left, right]

    weights = np.maximum(weights, 0)
    return weights / weights.sum() if weights.sum() > 0 else np.ones(n) / n


def portfolio_stats(weights, mu, sigma, risk_free=0.04):
    w = np.asarray(weights, dtype=float)
    ret = float(np.dot(w, mu))
    vol = float(np.sqrt(max(np.dot(w, np.dot(sigma, w)), 0)))
    sharpe = (ret - risk_free) / vol if vol > 1e-8 else 0.0
    return ret, vol, sharpe


def diversification_score(weights, sigma):
    """Higher is better: rewards lower concentration and lower correlation."""
    w = np.asarray(weights, dtype=float)
    hhi = float(np.sum(w ** 2))
    corr = covariance_to_correlation(sigma)
    avg_corr = 0.0
    pairs = 0
    for i in range(len(w)):
        for j in range(i + 1, len(w)):
            avg_corr += abs(corr[i, j])
            pairs += 1
    avg_corr = avg_corr / pairs if pairs else 0.5
    return max(0.0, (1 - hhi) * 50 + (1 - avg_corr) * 50)


def goal_amount_from_answers(answers, initial=100_000):
    txt = str(answers.get("target_amount", "") or "").lower().replace(",", "")
    if "double" in txt:
        return initial * 2
    import re
    nums = re.findall(r"\d+(?:\.\d+)?", txt)
    if not nums:
        return initial * 1.5
    val = float(nums[0])
    if "million" in txt or "m" in txt:
        val *= 1_000_000
    return max(val, initial * 0.75)


def run_monte_carlo_goal(weights, mu, sigma, answers, initial=100_000, sims=10000):
    years = max(1, min(40, int(parse_years(answers.get("time_horizon", "10")) or 10)))
    goal = goal_amount_from_answers(answers, initial)
    mc = run_monte_carlo(weights, mu, sigma, initial=initial, years=years, sims=sims)
    # Recompute with same distribution to estimate goal probability explicitly.
    np.random.seed(42)
    ret, vol, _ = portfolio_stats(weights, mu, sigma)
    paths = np.random.normal(ret, vol, (sims, years))
    wealth = initial * np.cumprod(1 + paths, axis=1)
    final = wealth[:, -1]
    mc.update({
        "goal_amount": round(float(goal), 0),
        "prob_goal": round(float((final >= goal).mean() * 100), 1),
        "prob_loss": round(float((final < initial).mean() * 100), 1),
        "expected_shortfall_10pct": round(float(np.percentile(final, 10)), 0),
        "method_note": f"{sims:,} simulations over {years} year(s)",
    })
    return mc


def choose_best_candidate(candidates, profile):
    """Rank candidate portfolios using objective function aligned to investor profile."""
    if not candidates:
        return None
    for c in candidates:
        ret, vol, sharpe = c["return"], c["vol"], c["sharpe"]
        div = c["diversification"]
        if profile == "Conservative":
            c["selection_score"] = (div * 0.35) + (sharpe * 20) - (vol * 120)
        elif profile == "Aggressive":
            c["selection_score"] = (sharpe * 35) + (ret * 90) + (div * 0.15)
        else:
            c["selection_score"] = (sharpe * 30) + (div * 0.25) - (vol * 40)
    return max(candidates, key=lambda x: x["selection_score"])


def build_portfolio_with_mvo(assets_list, profile, primary_goal, cov_data, ctx, answers=None):
    """
    Advanced optimisation pipeline:
    1. Build expected returns and covariance from Dimension Depths
    2. Apply Black-Litterman-style client view tilts to expected returns
    3. Generate candidate portfolios: MVO, BL-MVO, HRP, and income/min-vol variants
    4. Compare candidates by profile-aligned objective score
    5. Validate selected portfolio with 10,000-path Monte Carlo goal simulation
    """
    if not HAS_SCIPY or not assets_list:
        return None, None, None, None

    mu_raw, sigma, tickers = build_return_covariance_from_dd(assets_list, cov_data)
    sigma = regularize_covariance(sigma)
    answers = answers or {}
    mu_bl = apply_black_litterman_tilt(mu_raw, assets_list, answers, ctx)
    strategy = choose_mvo_strategy(profile, primary_goal)
    print(f"[OPT] Strategy: {strategy} | Assets: {len(assets_list)} | Methods: MVO + BL + HRP + Monte Carlo")

    candidates = []

    def add_candidate(name, weights, mu_used, description):
        if weights is None:
            return
        weights = np.asarray(weights, dtype=float)
        weights = np.maximum(weights, 0)
        if weights.sum() <= 0:
            return
        weights = weights / weights.sum()
        ret, vol, sharpe = portfolio_stats(weights, mu_used, sigma)
        candidates.append({
            "name": name,
            "weights": weights,
            "mu": mu_used,
            "return": ret,
            "vol": vol,
            "sharpe": sharpe,
            "diversification": diversification_score(weights, sigma),
            "description": description,
        })

    # 1) Traditional MVO baseline.
    if strategy == "income":
        yields = [float(a.get("income_yield_ann") or a.get("total_expected_return") or 0.04) for a in assets_list]
        add_candidate("Income-Constrained MVO", mvo_income_constrained(mu_raw, sigma, yields, min_yield=0.035), mu_raw,
                      "Minimises volatility while meeting a minimum income-yield constraint.")
    elif strategy == "min_vol":
        add_candidate("Minimum Volatility MVO", mvo_min_volatility(mu_raw, sigma), mu_raw,
                      "Finds the lowest-risk portfolio available from the selected assets.")
    else:
        add_candidate("Maximum Sharpe MVO", mvo_max_sharpe(mu_raw, sigma), mu_raw,
                      "Finds the highest expected return per unit of risk.")

    # 2) Black-Litterman adjusted MVO — same objective, personalised expected returns.
    if strategy == "income":
        yields = [float(a.get("income_yield_ann") or a.get("total_expected_return") or 0.04) for a in assets_list]
        add_candidate("Black-Litterman Income MVO", mvo_income_constrained(mu_bl, sigma, yields, min_yield=0.035), mu_bl,
                      "Uses the client's goal, currency, inflation, and sector views before applying income optimisation.")
    elif strategy == "min_vol":
        # Min-vol ignores mu, so BL version uses a mild max-sharpe challenger but remains constrained by caps/bounds.
        add_candidate("Black-Litterman Defensive MVO", mvo_max_sharpe(mu_bl, sigma), mu_bl,
                      "Tests whether client views can improve return without materially increasing risk.")
    else:
        add_candidate("Black-Litterman Max Sharpe", mvo_max_sharpe(mu_bl, sigma), mu_bl,
                      "Blends market expectations with the client's stated views, then maximises risk-adjusted return.")

    # 3) HRP robust diversification candidate.
    add_candidate("Hierarchical Risk Parity", hrp_weights_from_covariance(sigma), mu_raw,
                  "Clusters correlated assets and spreads risk across them for a more stable diversified portfolio.")

    if not candidates:
        print("[OPT] All optimisation candidates failed")
        return None, None, None, None

    selected = choose_best_candidate(candidates, profile)
    weights = selected["weights"]
    mc = run_monte_carlo_goal(weights, selected["mu"], sigma, answers, sims=10000)

    allocs = apply_mvo_weights(assets_list, weights, cov_data, profile, ctx)
    rb = build_risk_breakdown(allocs)

    metrics = compute_portfolio_metrics(allocs, cov_data)
    metrics["expected_return"] = f"{selected['return']*100:.1f}%"
    metrics["volatility"] = f"{selected['vol']*100:.1f}%"
    metrics["sharpe_ratio"] = f"{selected['sharpe']:.2f}"
    metrics["monte_carlo"] = mc
    metrics["mvo_strategy"] = strategy
    metrics["optimization_method"] = selected["name"]
    metrics["optimization_explanation"] = selected["description"]
    metrics["candidate_portfolios"] = [{
        "method": c["name"],
        "expected_return": round(c["return"] * 100, 2),
        "volatility": round(c["vol"] * 100, 2),
        "sharpe": round(c["sharpe"], 3),
        "diversification": round(c["diversification"], 1),
        "selected": c is selected,
    } for c in candidates]
    metrics["optimizer_summary"] = (
        f"Tested {len(candidates)} candidate portfolios using Dimension Depths return, volatility, covariance, "
        f"income yield and classification data. Selected {selected['name']} because it best matched the "
        f"{profile} profile's risk/return/diversification objective."
    )

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

def build_asset_explanations(allocations):
    """Structured asset-level explainability for dashboard cards and PDF expansion."""
    explanations = []
    for a in allocations or []:
        cp = float(a.get("corr_penalty") or 0)
        div_label = "High" if cp < 0.2 else ("Medium" if cp < 0.4 else "Low")
        explanations.append({
            "ticker": a.get("ticker", "—"),
            "label": a.get("label", "Asset"),
            "class": a.get("class", "Other"),
            "weight": a.get("pct", 0),
            "expected_return": a.get("expected_return"),
            "volatility": a.get("volatility"),
            "sharpe_ratio": a.get("sharpe_ratio"),
            "diversification_contribution": div_label,
            "reason": a.get("rationale") or "Improves portfolio fit and diversification.",
        })
    return explanations


def class_plain_english(cls):
    return {
        "Cash": "Liquid, low-volatility instruments used for stability and near-term flexibility.",
        "Fixed Income": "Bond-like instruments that support income and reduce overall volatility.",
        "Equity": "Growth-oriented instruments with higher return potential and higher market fluctuation.",
        "Real Estate": "Property-linked exposure that may support income and inflation resilience.",
        "Alternatives": "Non-traditional exposure that can improve diversification.",
        "Commodities": "Inflation-sensitive exposure that may behave differently from stocks and bonds.",
    }.get(cls, "Diversifying exposure within the approved SOC asset universe.")


def build_class_allocation(allocations):
    """Super-class allocation summary for 'Where is my money going?' dashboard sections."""
    totals = {}
    for a in allocations or []:
        cls = a.get("class", "Other")
        totals[cls] = totals.get(cls, 0.0) + float(a.get("pct") or 0)
    return [
        {
            "class": cls,
            "pct": round(pct, 1),
            "color": CLASS_COLORS.get(cls, "#6B7280"),
            "plain_english": class_plain_english(cls),
        }
        for cls, pct in sorted(totals.items(), key=lambda x: -x[1])
    ]


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
def questionnaire_page():
    # The separate questionnaire page was removed from the UX.
    # Users now complete the questionnaire inside the AI Chatbot tab.
    return send_file("public/index.html")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":"ok","service":"Barita Wealth Advisor",
        "dd_api":bool(DD_API_KEY),
        "ai_mode":"deterministic_templates",
    })

@app.route("/analyse", methods=["POST"])
def analyse():
    user,err = verify_token(request)
    if err: return jsonify({"error":err}),401

    answers = request.get_json().get("answers",{})
    score,profile,profile_label,exp_level = score_answers(answers)
    allocations,risk_breakdown,metrics,behavioral_flags,behavioral_profile,confidence = build_allocation(profile, answers)
    name = f"{answers.get('first_name','')} {answers.get('last_name','')}".strip() or "Client"

    provisional_report = {
        "profile": profile,
        "behavioral_profile": behavioral_profile,
        "allocations": allocations,
        "risk_breakdown": risk_breakdown,
        "class_allocation": build_class_allocation(allocations),
        "metrics": metrics,
        "monte_carlo": metrics.get("monte_carlo", {}),
        "behavioral_flags": behavioral_flags,
        "confidence": confidence,
    }
    advisory = generate_template_advisory_note(answers, provisional_report)
    ai_provider = "deterministic_template"

    explainability_summary = build_explainability_summary(answers, profile, behavioral_profile, behavioral_flags, metrics)

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
        "engine_explanation": explainability_summary,
        "asset_explanations": build_asset_explanations(allocations),
        "class_allocation":   build_class_allocation(allocations),
        "optimizer_results":  metrics.get("candidate_portfolios", []),
        "optimization_method": metrics.get("optimization_method", "score_based"),
        "optimizer_summary":  metrics.get("optimizer_summary", ""),
        "advisory_note":      advisory,
        "ai_provider":        ai_provider,
        "client_name":        name,
    }

    try:
        if db is None:
            raise RuntimeError("Firestore not initialised")
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

    groq_result = ask_groq(message, answers, report)

    if groq_result and groq_result.get("raise_error"):
        return jsonify({
            "reply": groq_result["reply"],
            "provider": "guardrail",
            "raise_error": True
        })

    if groq_result and groq_result.get("reply"):
        return jsonify({
            "reply": groq_result["reply"],
            "provider": "groq"
        })

    reply = generate_chat_reply(message, answers, report)

    return jsonify({
        "reply": reply,
        "provider": "deterministic_template"
    })


# ── CHATBOT QUESTIONNAIRE ENGINE ──────────────────────────────────────────────
# The questionnaire flow is deterministic so the demo never breaks if an AI
# provider is unavailable. AI is used for portfolio commentary, not for deciding
# which question comes next.
QUESTIONNAIRE_FLOW = [
    {"field":"first_name", "question":"What's your first name? I like to keep things personal! 🍯", "options":None},
    {"field":"last_name", "question":"And your last name?", "options":None},
    {"field":"age", "question":"How old are you? Just the number is fine!", "options":None},
    {"field":"knowledge_level", "question":"How would you describe your investing experience?", "options":["I'm completely new to investing","I have basic knowledge but no real experience","I've been learning and have some experience","I have a lot of investing experience"]},
    {"field":"primary_goal", "question":"What's your #1 financial goal right now?", "options":["Wealth accumulation / growth","Retirement planning","Education funding","Property purchase","Income generation","Capital preservation","Emergency fund building"]},
    {"field":"time_horizon", "question":"How many years before you'd need to access this money? A rough estimate is perfect.", "options":None},
    {"field":"target_amount", "question":"Do you have a specific money target in mind? For example, 'double my money', 'JMD 5 million', or 'not sure'.", "options":None},
    {"field":"withdrawal_time", "question":"Over the next 2 years, how much of this portfolio might you need to withdraw?", "options":["No withdrawals","Less than 10%","10-25%","More than 25%"]},
    {"field":"drop_reaction", "question":"If your portfolio dropped 20% in one month, what would you honestly do? 😬", "options":["Sell everything to avoid further losses","Sell some to reduce losses","Wait for recovery","Invest more at lower prices"]},
    {"field":"risk_comfort", "question":"On a scale of 1–10, how much annual drawdown could you stomach before reconsidering your strategy? 1 means very little, 10 means big swings are okay.", "options":None},
    {"field":"max_loss", "question":"What's the maximum annual loss you could handle without changing your plan?", "options":["Up to 10%","Up to 20%","Up to 40%","More than 40%"]},
    {"field":"sector_view", "question":"Do you have a strong view that any sector will outperform? You can say something like 'tech', 'local JMD assets', or 'not sure'.", "options":None},
    {"field":"income_loss_runway", "question":"If you lost your income tomorrow, how long could you live comfortably without touching investments?", "options":["Less than 3 months","3-6 months","6-12 months","1-2 years","More than 2 years"]},
    {"field":"debt_situation", "question":"How would you describe your current debt situation?", "options":["Debt-free","Minor debt","Moderate debt","Significant debt"]},
    {"field":"earn_currency", "question":"What currency do you mainly earn in?", "options":["JMD only","USD only","Mostly JMD","Mostly USD","Equal amounts of JMD and USD"]},
    {"field":"spend_currency", "question":"What currency do you mainly spend in?", "options":["JMD only","USD only","Mostly JMD","Mostly USD","Equal amounts of JMD and USD"]},
    {"field":"usd_liabilities", "question":"Do you have any USD-denominated debts or liabilities?", "options":["None","Under USD $10K","USD $10K-$50K","USD $50K-$200K","Over USD $200K"]},
    {"field":"inflation_impact", "question":"How much does JMD inflation affect your daily costs?", "options":["Not sure","Minimal","Moderate","Significant","Severe"]},
    {"field":"inflation_protection", "question":"Do you want inflation protection built into your portfolio?", "options":["Not sure","Not necessary","Somewhat","Yes - strong focus"]},
    {"field":"invest_style", "question":"What's your preferred investing style?", "options":["Fully passive","Mostly passive","Balanced","Mostly active","Fully active"]},
    {"field":"market_adjustment", "question":"If market conditions shifted, would you be open to adjusting your portfolio?", "options":["No - keep it fixed","Yes - small changes","Yes - moderate changes","Yes - fully active"]},
    {"field":"risk_relationship", "question":"Which best describes your relationship with investment risk?", "options":["I worry a lot about losing money","I'm okay with small changes, but big losses stress me","I understand ups and downs and stay calm","I'm comfortable with big risks and see drops as opportunities"]},
    {"field":"loss_vs_gain", "question":"Which outcome would upset you more?", "options":["Missing a 20% gain","Suffering a 20% loss"]},
    {"field":"performance_benchmark", "question":"When checking your portfolio, what do you mainly compare it against?", "options":["The amount I originally invested","The overall increase in value (JMD gains)","My expected return","A market index","The rate of inflation"]},
]


def _normalise_choice(value, options):
    """Return the exact option label when the user types a close/simple version."""
    if not options:
        return str(value or "").strip()
    raw = str(value or "").strip()
    raw_l = raw.lower()
    for opt in options:
        if raw_l == opt.lower():
            return opt
    for opt in options:
        # Accept partial typed answers like "mostly jmd" or "debt free".
        compact_raw = raw_l.replace("-", " ").replace("/", " ")
        compact_opt = opt.lower().replace("-", " ").replace("/", " ")
        if compact_raw and (compact_raw in compact_opt or compact_opt in compact_raw):
            return opt
    return raw


def _next_unanswered_question(answers):
    for q in QUESTIONNAIRE_FLOW:
        val = answers.get(q["field"])
        if val is None or str(val).strip() == "":
            return q
    return None


def _feedback_for_answer(field, value, answers):
    name = answers.get("first_name") or "friend"
    v = str(value)
    feedback = {
        "first_name": f"Pawsome to meet you, {name}! 🐻✨ I’ll use your name so the advice feels personal, not generic.",
        "last_name": "Got it — your report will feel more complete and professional with your full name.",
        "age": "Perfect. Age helps me think about time horizon and how much market movement may be suitable.",
        "knowledge_level": "That helps me match the explanation style to your experience level — no confusing jargon, promise.",
        "primary_goal": "That goal is important because a growth goal and a preservation goal should not get the same portfolio.",
        "time_horizon": "Great. Your time horizon tells me whether the portfolio can take short-term ups and downs or should stay steadier.",
        "target_amount": "Noted. A target gives the Monte Carlo/growth projection something practical to measure against.",
        "withdrawal_time": "Thanks. Liquidity matters because money you may need soon should not be placed in assets that swing too much.",
        "drop_reaction": "Thank you for being honest. This tells me how you may behave when the market gets stressful, which is key for suitability.",
        "risk_comfort": "Got it. That gives a more human measure of drawdown comfort beyond a simple Conservative/Moderate/Aggressive label.",
        "max_loss": "That loss limit helps set the ceiling for how much volatility your portfolio should carry.",
        "sector_view": "Nice. Your view can help shape the asset logic while still keeping the portfolio diversified.",
        "income_loss_runway": "That safety-net answer matters a lot — if your runway is short, the portfolio should protect you from being forced to sell.",
        "debt_situation": "Thank you. Debt affects how much investment risk is reasonable in real life.",
        "earn_currency": "Currency exposure matters in Jamaica because JMD and USD needs can change what assets fit best.",
        "spend_currency": "That helps me match the portfolio to the currency you actually use day to day.",
        "usd_liabilities": "Important. USD obligations may call for more USD-aware exposure so the portfolio better matches your liabilities.",
        "inflation_impact": "Inflation pressure matters because rising costs can quietly reduce purchasing power.",
        "inflation_protection": "Got it. This helps decide whether assets like real estate, commodities, or equities deserve more attention.",
        "invest_style": "That style preference helps me decide whether the portfolio should be more hands-off or more actively adjusted.",
        "market_adjustment": "Good to know. Rebalancing flexibility helps the portfolio adapt when market conditions shift.",
        "risk_relationship": "That tells me your emotional comfort with risk, not just your numerical tolerance.",
        "loss_vs_gain": "This helps detect loss aversion — many investors feel losses more strongly than gains.",
        "performance_benchmark": "That benchmark tells me how you judge success, which affects how the advice should be explained.",
    }
    return feedback.get(field, f"Got it, {name}. That answer helps me make the portfolio more personalised.")


@app.route("/chat_questionnaire", methods=["POST"])
def chat_questionnaire():
    """Deterministic Barita Bear questionnaire chatbot, one question at a time."""
    user, err = verify_token(request)
    if err:
        return jsonify({"error": err}), 401

    data = request.get_json() or {}
    user_message = str(data.get("message", "")).strip()
    answers = dict(data.get("answers", {}) or {})
    stage = data.get("stage", "intro")

    # Intro call: ask the first unanswered question, no extraction yet.
    if stage == "intro" or not user_message:
        q = _next_unanswered_question(answers)
        if not q:
            parsed = {
                "message": "🎉 Pawsome — I already have everything I need. Let’s build your personalised portfolio now!",
                "extracted_answer": {},
                "options": None,
                "stage": "complete",
                "next_field": None,
                "progress": 100,
            }
            return jsonify({"raw": json.dumps(parsed), "parsed": parsed, "provider": "deterministic"})
        parsed = {
            "message": "🐻 Pawsome to meet you! I'm Barita, your friendly investment advisor bear from Barita Investments! 🎉\n\nI’ll guide you one question at a time and give feedback after each answer. Ready? " + q["question"],
            "extracted_answer": {},
            "options": q.get("options"),
            "stage": "questionnaire",
            "next_field": q["field"],
            "progress": round(len([x for x in QUESTIONNAIRE_FLOW if answers.get(x["field"])]) / len(QUESTIONNAIRE_FLOW) * 100),
        }
        return jsonify({"raw": json.dumps(parsed), "parsed": parsed, "provider": "deterministic"})

    current_q = _next_unanswered_question(answers)
    extracted = {}

    if current_q:
        field = current_q["field"]
        value = _normalise_choice(user_message, current_q.get("options"))

        # If the user enters a full name for first name, split it nicely.
        if field == "first_name" and len(value.split()) >= 2 and not answers.get("last_name"):
            parts = value.split()
            extracted["first_name"] = parts[0]
            extracted["last_name"] = " ".join(parts[1:])
        else:
            extracted[field] = value
        answers.update(extracted)

    next_q = _next_unanswered_question(answers)
    completed_count = len([q for q in QUESTIONNAIRE_FLOW if answers.get(q["field"])])
    progress = round(completed_count / len(QUESTIONNAIRE_FLOW) * 100)

    if not next_q:
        last_field = list(extracted.keys())[0] if extracted else None
        last_value = extracted.get(last_field, user_message) if last_field else user_message
        feedback = _feedback_for_answer(last_field, last_value, answers) if last_field else "Beautiful — your profile is complete."
        parsed = {
            "message": f"{feedback}\n\n🎉 Pawsome! Your investor profile is complete. I’m ready to build your personalised Barita portfolio now.",
            "extracted_answer": extracted,
            "options": None,
            "stage": "complete",
            "next_field": None,
            "progress": 100,
        }
        return jsonify({"raw": json.dumps(parsed), "parsed": parsed, "provider": "deterministic"})

    # Build a short, personalised feedback + next question.
    last_field = list(extracted.keys())[0] if extracted else None
    last_value = extracted.get(last_field, user_message) if last_field else user_message
    feedback = _feedback_for_answer(last_field, last_value, answers) if last_field else "Got it — thanks for sharing that."
    message = f"{feedback}\n\nNext question: {next_q['question']}"

    parsed = {
        "message": message,
        "extracted_answer": extracted,
        "options": next_q.get("options"),
        "stage": "questionnaire",
        "next_field": next_q["field"],
        "progress": progress,
    }
    return jsonify({"raw": json.dumps(parsed), "parsed": parsed, "provider": "deterministic"})


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

    # Optimisation explanation
    if metrics.get("optimization_method") or metrics.get("optimizer_summary"):
        story.append(Paragraph("Optimisation Method",h2))
        opt_rows = [["Selected Method", metrics.get("optimization_method","—")],
                    ["Strategy", metrics.get("mvo_strategy","—")],
                    ["Monte Carlo", metrics.get("monte_carlo",{}).get("method_note","—")],
                    ["Goal Probability", f"{metrics.get('monte_carlo',{}).get('prob_goal','—')}%"]]
        ot=Table(opt_rows,colWidths=["30%","70%"])
        ot.setStyle(TableStyle([("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),9),("TEXTCOLOR",(0,0),(0,-1),MUTED),("ROWBACKGROUNDS",(0,0),(-1,-1),[LIGHT,colors.white]),("PADDING",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),0.5,BORD)]))
        story += [ot, Spacer(1,6)]
        story.append(Paragraph(metrics.get("optimizer_summary", metrics.get("optimization_explanation", "")), sm))
        story.append(Spacer(1,12))

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