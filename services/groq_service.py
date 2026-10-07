# SERVICE: SAGE Groq Provider (Reserved)
# Prepared for later receipt/document analysis. Key selection intentionally tries GROQ_API_KEY5 -> 4 -> 3 and leaves keys 1/2 unused.

import os
from groq import Groq


GROQ_KEY_ORDER = ("GROQ_API_KEY5", "GROQ_API_KEY4", "GROQ_API_KEY3")


def get_groq_client():
    for key_name in GROQ_KEY_ORDER:
        value = (os.getenv(key_name) or "").strip()
        if value and "xxxx" not in value.lower():
            return Groq(api_key=value), key_name
    raise RuntimeError("No configured Groq key is available in the permitted priority order 5 -> 4 -> 3.")
