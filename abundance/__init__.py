"""Abundance engine — deterministic swing-recommendation system.

Standalone: pure Python 3.10+ stdlib. No LLM, no broker write calls, ever.
The ONLY external network calls are read-only NSE bhavcopy downloads and the
optional Telegram notification.
"""

# Bump ONLY via the manual approval procedure in abundance/README.md.
# Every journal entry records the version that produced it (Hard Rule 6).
RULESET_VERSION = "1.0.0"
