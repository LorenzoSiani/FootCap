"""
Provider adapters (Architecture Baseline section 12: "Provider calls
remain behind one adapter owning HTTP, timeouts, retries, rate limits,
error mapping, and request/response logging").

This package intentionally holds no shared re-exports of its own --
each provider subpackage (e.g. api_football/) is its own thin public
boundary, the same role runs/__init__.py and temporal/__init__.py play
for their respective modules.
"""
