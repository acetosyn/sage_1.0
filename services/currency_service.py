# ==========================================================
# SAGE CURRENCY DISPLAY ENGINE
# Keeps accounting/base currency immutable while allowing owners to view the same ledger in a converted display currency.
# Live FX uses a no-key public endpoint with a short timeout + in-process cache; safe reference rates are used only when live FX is unavailable.
# ==========================================================

import json
import os
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen


SUPPORTED_CURRENCIES = [
    {"code":"NGN","symbol":"₦","name":"Nigerian Naira","region":"Nigeria","featured":True},
    {"code":"USD","symbol":"$","name":"US Dollar","region":"International"},
    {"code":"GBP","symbol":"£","name":"Pound Sterling","region":"United Kingdom"},
    {"code":"EUR","symbol":"€","name":"Euro","region":"European Union"},
    {"code":"GHS","symbol":"GH₵","name":"Ghanaian Cedi","region":"Ghana"},
    {"code":"ZAR","symbol":"R","name":"South African Rand","region":"South Africa"},
    {"code":"KES","symbol":"KSh","name":"Kenyan Shilling","region":"Kenya"},
    {"code":"UGX","symbol":"USh","name":"Ugandan Shilling","region":"Uganda"},
    {"code":"TZS","symbol":"TSh","name":"Tanzanian Shilling","region":"Tanzania"},
    {"code":"RWF","symbol":"FRw","name":"Rwandan Franc","region":"Rwanda"},
    {"code":"XOF","symbol":"CFA","name":"West African CFA Franc","region":"West Africa"},
    {"code":"XAF","symbol":"FCFA","name":"Central African CFA Franc","region":"Central Africa"},
    {"code":"EGP","symbol":"E£","name":"Egyptian Pound","region":"Egypt"},
    {"code":"MAD","symbol":"MAD","name":"Moroccan Dirham","region":"Morocco"},
    {"code":"BWP","symbol":"P","name":"Botswana Pula","region":"Botswana"},
    {"code":"CAD","symbol":"C$","name":"Canadian Dollar","region":"Canada"},
    {"code":"AUD","symbol":"A$","name":"Australian Dollar","region":"Australia"},
    {"code":"CHF","symbol":"CHF","name":"Swiss Franc","region":"Switzerland"},
]
CURRENCY_MAP = {row["code"]: row for row in SUPPORTED_CURRENCIES}

# Reference units per 1 USD. These values are a continuity fallback only; SAGE labels them as reference/fallback when used.
# Production display prefers the live provider below and caches successful results.
_FALLBACK_PER_USD = {"USD":1.0,"NGN":1500.0,"GBP":0.79,"EUR":0.92,"GHS":15.2,"ZAR":18.2,"KES":129.0,"UGX":3700.0,"TZS":2600.0,"RWF":1375.0,"XOF":604.0,"XAF":604.0,"EGP":49.5,"MAD":10.0,"BWP":13.7,"CAD":1.38,"AUD":1.52,"CHF":0.88}
_RATE_CACHE = {}
_CACHE_SECONDS = max(900, int(os.getenv("SAGE_FX_CACHE_SECONDS", "21600")))
_RATE_URL = os.getenv("SAGE_FX_URL", "https://open.er-api.com/v6/latest/{base}").strip()


def normalize_currency(code, default="NGN"):
    code = str(code or "").strip().upper(); return code if code in CURRENCY_MAP else default


def currency_meta(code): return CURRENCY_MAP[normalize_currency(code)]
def currency_symbol(code): return currency_meta(code)["symbol"]


def _fallback_rate(base, target):
    base, target = normalize_currency(base), normalize_currency(target)
    if base == target: return 1.0
    return _FALLBACK_PER_USD[target] / _FALLBACK_PER_USD[base]


def rate_snapshot(base, target):
    """Return {rate, live, provider, updated_at}; amount_in_target = amount_in_base * rate."""
    base, target = normalize_currency(base), normalize_currency(target)
    now = time.time(); key = (base, target)
    if base == target: return {"base":base,"target":target,"rate":1.0,"live":True,"provider":"Native","updated_at":datetime.now(timezone.utc).isoformat()}
    cached = _RATE_CACHE.get(key)
    if cached and now - cached["cached_at"] < _CACHE_SECONDS: return {k:v for k,v in cached.items() if k != "cached_at"}
    try:
        req = Request(_RATE_URL.format(base=base), headers={"User-Agent":"SAGE-Business-OS/1.0","Accept":"application/json"})
        with urlopen(req, timeout=2.8) as response: payload = json.loads(response.read().decode("utf-8"))
        rate = float((payload.get("rates") or {}).get(target) or 0)
        if rate <= 0: raise ValueError("Target currency unavailable from FX provider")
        result = {"base":base,"target":target,"rate":rate,"live":True,"provider":"Live FX","updated_at":payload.get("time_last_update_utc") or datetime.now(timezone.utc).isoformat()}
    except Exception:
        result = {"base":base,"target":target,"rate":_fallback_rate(base,target),"live":False,"provider":"Reference fallback","updated_at":datetime.now(timezone.utc).isoformat()}
    _RATE_CACHE[key] = {**result,"cached_at":now}; return result


def convert_amount(value, source_currency, target_currency):
    try: amount = float(value or 0)
    except (TypeError, ValueError): amount = 0.0
    source, target = normalize_currency(source_currency), normalize_currency(target_currency)
    return amount if source == target else amount * float(rate_snapshot(source, target)["rate"])


def _decimals(value, requested=None):
    if requested is not None:
        try: return max(0, min(4, int(requested)))
        except (TypeError, ValueError): pass
    absolute = abs(float(value or 0)); return 2 if absolute and absolute < 100 else 0


def format_money(value, source_currency="NGN", target_currency=None, decimals=None):
    source = normalize_currency(source_currency); target = normalize_currency(target_currency or source, source); converted = convert_amount(value, source, target); digits = _decimals(converted, decimals); symbol = currency_symbol(target)
    number = f"{abs(converted):,.{digits}f}"; sign = "−" if converted < 0 else ""; joiner = " " if symbol in {"GH₵","KSh","USh","TSh","FRw","CFA","FCFA","MAD","CHF"} else ""
    return f"{sign}{symbol}{joiner}{number}"


def display_context(organization):
    base = normalize_currency(getattr(organization, "currency", None) or "NGN"); display = normalize_currency(getattr(organization, "display_currency", None) or base, base); snapshot = rate_snapshot(base, display)
    return {"base":base,"base_symbol":currency_symbol(base),"display":display,"display_symbol":currency_symbol(display),"rate":snapshot["rate"],"live":snapshot["live"],"provider":snapshot["provider"],"updated_at":snapshot["updated_at"],"changed":base != display}
