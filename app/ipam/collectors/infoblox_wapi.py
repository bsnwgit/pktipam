"""
app/ipam/collectors/infoblox_wapi.py
----------------------------------------
Shared Infoblox NIOS WAPI (REST API) session + paging helper, used by both
the DHCP (dhcp/infoblox.py) and DNS (dns/infoblox.py) collectors — same
auth mechanism and paging cursor behavior, just different object types.

Auth: HTTP Basic on every request (httpx.AsyncClient keeps the underlying
TCP/TLS connection alive across requests in the same client instance, so
this doesn't cost a new handshake per call — NIOS also supports session-
cookie reuse via the `ibapauth` cookie, but plain Basic auth per request is
simpler and just as correct for a poll-cycle-scoped client).

Paging: WAPI pages results when `_paging=1` + `_return_as_object=1` +
`_max_results` are set on a GET — response becomes
`{"result": [...], "next_page_id": "<opaque>"}`; pass `_page_id` back on
the next request until `next_page_id` is absent. This avoids ever silently
truncating results at whatever the first page's `_max_results` happens to
be, which a naive single-request implementation would do.
"""
from __future__ import annotations

import httpx

_DEFAULT_MAX_RESULTS = 1000


class WapiClient:
    def __init__(self, config: dict):
        self.base_url = (config.get("base_url") or "").rstrip("/")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.wapi_version = config.get("wapi_version") or "2.12"
        self.verify_tls = config.get("verify_tls", True)

        if not self.base_url:
            raise ValueError("Infoblox collector requires 'base_url'")
        if not self.username or not self.password:
            raise ValueError("Infoblox collector requires 'username' and 'password'")

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(auth=(self.username, self.password), verify=self.verify_tls, timeout=30)

    async def get_all(self, client: httpx.AsyncClient, object_type: str, return_fields: list[str],
                       max_results: int = _DEFAULT_MAX_RESULTS) -> list[dict]:
        """Page through every object of `object_type` (e.g. 'lease', 'record:a')."""
        url = f"{self.base_url}/wapi/v{self.wapi_version}/{object_type}"
        base_params = {
            "_return_fields": ",".join(return_fields),
            "_max_results": max_results,
            "_paging": "1",
            "_return_as_object": "1",
        }

        results: list[dict] = []
        page_id: str | None = None
        while True:
            params = dict(base_params)
            if page_id:
                params["_page_id"] = page_id
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()
            results.extend(body.get("result", []))
            page_id = body.get("next_page_id")
            if not page_id:
                break
        return results
