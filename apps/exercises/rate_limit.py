"""Rate limiting helpers for expensive exercise endpoints.

The implementation is shared with the rest of the project; see
``project_core.ratelimit``.
"""

from __future__ import annotations

from project_core.ratelimit import check_rate_limit, client_ip as _client_ip

__all__ = ["check_rate_limit", "_client_ip"]
