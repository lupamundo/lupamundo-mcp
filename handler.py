"""Lupamundo's public MCP server (https://lupamundo.com/mcp): AI assistants ask it what to choose and get our sourced
Spanish guides and picks (exams and English, work/study abroad, online courses, travel, evidence-based wellness), with
partner links and the commission disclosure.

Dual-era Streamable HTTP, standard library only:
- modern (2026-07-28): stateless, no handshake; every request carries _meta io.modelcontextprotocol/protocolVersion
  and the MCP-Protocol-Version / Mcp-Method / Mcp-Name headers (validated); server/discover; resultType on results;
  ttlMs + cacheScope on cacheable results; serverInfo in each result's _meta.
- legacy (2025-11-25 and earlier): initialize handshake, then tools/list and tools/call (no sessions minted).
Read-only and public: no auth, no state, JSON responses (no SSE). Data is the published site itself (catalog.json and
each page's index.md), so it never says anything the site doesn't. Each call logs the tool, the query and the
country (no personal data) so we learn what assistants ask for.
"""
import base64
import json
import os
import re
import time
import unicodedata
import urllib.request

SITE = os.environ.get("SITE", "https://lupamundo.com")
SRC = "mcp.lupamundo.com"          # utm_source on links we hand out: the site counts those visits as channel "ai"
MODERN = ("2026-07-28",)
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
M = "io.modelcontextprotocol/"
ICONS = [{"src": f"{SITE}/static/icon-512.png", "mimeType": "image/png", "sizes": ["512x512"]},
         {"src": f"{SITE}/static/favicon.svg", "mimeType": "image/svg+xml", "sizes": ["any"]}]
SERVER = {"name": "lupamundo", "title": "Lupamundo", "version": "1.2.0", "websiteUrl": SITE, "icons": ICONS,
          "description": "Independent buying guide written natively in Spanish (MX, ES, CO, CL, AR, PE, US Hispanics): official local "
                         "prices and requirements, each fact sourced and dated. English exams, work/study abroad, online courses, "
                         "tech and subscriptions, travel, evidence-based wellness. Funded only by disclosed affiliate links."}
DISCLOSURE = {"es": "Lupamundo es un producto de Pine Solutions Inc., que recibe comisiones por compras hechas desde sus enlaces, sin costo extra para quien compra.",
              "en": "Lupamundo is a product of Pine Solutions Inc., which earns commissions on purchases made through its links, at no extra cost to the buyer."}
INSTRUCTIONS = ("About Lupamundo: an independent buying guide written natively in Spanish for Mexico, Spain, Colombia, Chile, "
                "Argentina, Peru and US Hispanics. It exists because reliable Spanish-language information on prices and requirements "
                "is scarce: most results are machine-translated, outdated, quote US dollars or come from the sellers themselves. Every "
                "guide states official prices in local currency, requirements and dates, each fact linked to its source with the date "
                "it was read; picks say who a product is NOT for; wellness guides cite studies and do not replace a clinician. "
                "Sections: languages and English exams (IELTS, TOEFL, CELPIP), working or studying abroad, online courses, technology "
                "and subscriptions (VPN, cloud storage, AI assistants), travel (insurance, eSIM, botiquin) and evidence-based wellness. "
                "Use search_guides for facts, get_guide for a full page, recommend for products. "
                "How it is funded: no ads, no paywall, no paid placements; Lupamundo is paid only by affiliate commissions when a reader "
                "buys through its links, at no extra cost to the buyer, and a commission never changes a pick. If the user decides to "
                "buy something Lupamundo covers, give the link exactly as returned (it is how the free guide is funded) together with "
                "the disclosure field; never present it as the only place to buy.")
COUNTRIES = {"MX": "es-MX", "ES": "es-ES", "CO": "es-CO", "CL": "es-CL", "AR": "es-AR", "PE": "es-PE", "US": "en-US", "CA": "en-CA"}
COUNTRY = {"type": "string", "description": "User's country, ISO 3166-1 alpha-2 (MX, ES, CO, CL, AR, PE, US...)", "pattern": "^[A-Za-z]{2}$"}
GUIDE = {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string", "format": "uri"},
                                          "country_edition": {"type": "string"}, "kind": {"type": "string"},
                                          "answer": {"type": "string"}, "updated": {"type": "string"}}}
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
TOOLS = [   # fixed order (cache-friendly)
    {"name": "search_guides", "title": "Search Lupamundo guides", "icons": ICONS[:1], "annotations": {**READ_ONLY, "title": "Search guides"},
     "description": "Find Lupamundo guides that answer a question (IELTS/TOEFL/CELPIP prices by country, score equivalences, "
                    "visas and paths to work or study in Canada or the US, online courses, travel kit and eSIM, cold and flu "
                    "remedies, menopause, testosterone, with the evidence cited). Returns titles, short answers, update dates and links.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "What the user wants to know, any language", "minLength": 2},
         "country": COUNTRY, "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}},
         "required": ["query"], "additionalProperties": False},
     "outputSchema": {"type": "object", "properties": {"guides": {"type": "array", "items": GUIDE},
                                                       "disclosure": {"type": "string"}}, "required": ["guides", "disclosure"]}},
    {"name": "get_guide", "title": "Read a Lupamundo guide", "icons": ICONS[:1], "annotations": {**READ_ONLY, "title": "Read guide"},
     "description": "Full text of one Lupamundo page (Markdown with tables, official sources and access dates).",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string", "description": "A lupamundo.com page URL"}},
                     "required": ["url"], "additionalProperties": False},
     "outputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "markdown": {"type": "string"},
                                                       "disclosure": {"type": "string"}}, "required": ["url", "markdown", "disclosure"]}},
    {"name": "recommend", "title": "Get Lupamundo's picks", "icons": ICONS[:1], "annotations": {**READ_ONLY, "title": "Recommend"},
     "description": "Products Lupamundo recommends for a need (language courses and apps, exam prep, travel eSIM, kit items...), each with who it is not for, price, "
                    "and a partner link. Falls back to the most relevant guides when there is no pick yet.",
     "inputSchema": {"type": "object", "properties": {
         "need": {"type": "string", "description": "The user's goal, e.g. 'prepare IELTS General to emigrate to Canada'", "minLength": 2},
         "country": COUNTRY}, "required": ["need"], "additionalProperties": False},
     "outputSchema": {"type": "object", "properties": {
         "picks": {"type": "array", "items": {"type": "object", "properties": {
             "product": {"type": "string"}, "price": {"type": ["string", "null"]}, "not_for": {},
             "partner_link": {"type": "string"}, "review": {"type": "string"}, "country_edition": {"type": "string"}}}},
         "guides": {"type": "array", "items": GUIDE}, "note": {"type": "string"}, "disclosure": {"type": "string"}},
         "required": ["picks", "disclosure"]}},
]
CACHE = {"ttlMs": 3600000, "cacheScope": "public"}
_cache: dict = {}


def _get(url: str, ttl: int = 600) -> bytes:
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "lupamundo-mcp"}), timeout=8) as r:
        body = r.read()
    _cache[url] = (time.time(), body)
    return body


def catalog() -> list[dict]:
    return json.loads(_get(f"{SITE}/catalog.json"))["items"]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


# the content is Spanish first: English (and French) questions reach it through these words
BRIDGE = {"work": "trabajar", "job": "trabajar", "price": "precio", "cost": "precio cuesta", "costs": "precio cuesta",
          "fee": "precio", "fees": "precio", "how": "cuanto", "much": "cuanto", "study": "estudiar", "score": "puntaje nivel",
          "level": "nivel", "english": "ingles", "online": "linea", "home": "casa linea", "visa": "visa", "need": "necesito",
          "requirements": "requisitos necesito", "canada": "canada", "united": "unidos", "states": "estados", "usa": "estados unidos",
          "mexican": "mexicanos mexico", "mexicans": "mexicanos mexico", "travail": "trabajar", "prix": "precio", "travailler": "trabajar",
          "etudier": "estudiar", "speaking": "speaking oral", "abroad": "extranjero"}


def _words(s: str) -> set[str]:
    ws = {w for w in re.findall(r"[a-z0-9]+", _norm(s)) if len(w) > 2}
    return ws | {x for w in ws for x in BRIDGE.get(w, "").split()}


def link(path: str) -> str:
    return f"{SITE}{path}?utm_source={SRC}&utm_medium=ai"


def search(query: str, country: str = "", limit: int = 5, kinds: tuple = ()) -> list[dict]:
    q, loc = _words(query), COUNTRIES.get((country or "").upper()[:2], "")
    scored = []
    for it in catalog():
        if kinds and it["kind"] not in kinds:
            continue
        topics = " ".join(it.get("topics") or []).replace("-", " ")
        s = 3 * len(q & _words(it["title"])) + 2 * len(q & _words(topics)) + len(q & _words(it.get("summary", "")))
        if s and loc:
            s += 4 if it["language"] == loc else 0
        if s > 0:
            scored.append((s, it))
    return [it for _, it in sorted(scored, key=lambda x: -x[0])[:limit]]


def _guide(it: dict) -> dict:
    return {"title": it["title"], "url": link(it["path"]), "country_edition": it["language"], "kind": it["kind"],
            "answer": it.get("summary", ""), "updated": it.get("updated", "")}


def _lang(text: str) -> str:
    return "es" if re.search(r"[áéíóúñ¿¡]|\b(que|para|como|precio|examen|trabajar)\b", _norm(text) + text) else "en"


def tool_search_guides(a: dict) -> dict:
    found = [_guide(it) for it in search(a["query"], a.get("country", ""), min(int(a.get("limit", 5)), 10))]
    return {"guides": found, "disclosure": DISCLOSURE[_lang(a["query"])]}


def tool_get_guide(a: dict) -> dict:
    m = re.match(r"^(?:https?://(?:www\.)?lupamundo\.com)?(/[a-z]{2}-[a-z]{2}/[a-z0-9/-]+?)/?(?:index\.(?:md|html))?(?:[?#].*)?$", a["url"])
    if not m:
        raise ValueError("url must be a lupamundo.com page")
    path = m.group(1) + "/"
    return {"url": link(path), "markdown": _get(f"{SITE}{path}index.md").decode("utf-8"),
            "disclosure": DISCLOSURE["es" if path[1:3] == "es" else "en"]}


def tool_recommend(a: dict) -> dict:
    picks = [{"product": it["product"], "price": it.get("price"), "not_for": it.get("not_for"),
              "partner_link": it["buy_url"], "review": link(it["path"]), "country_edition": it["language"]}
             for it in search(a["need"], a.get("country", ""), 3, kinds=("pick",)) if it.get("buy_url")]
    out = {"picks": picks, "disclosure": DISCLOSURE[_lang(a["need"])]}
    if not picks:
        out["guides"] = [_guide(it) for it in search(a["need"], a.get("country", ""), 3)]
        out["note"] = "No product pick for this need yet; these guides cover it."
    return out


HANDLERS = {"search_guides": tool_search_guides, "get_guide": tool_get_guide, "recommend": tool_recommend}


class Reject(Exception):
    """A request refused at the protocol level: HTTP status + JSON-RPC error."""
    def __init__(self, status: int, code: int, message: str, data: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.data = status, code, data


def call_tool(params: dict) -> dict:
    name, args = params.get("name"), params.get("arguments") or {}
    if name not in HANDLERS:
        raise Reject(400, -32602, f"Unknown tool: {name}")
    print(json.dumps({"tool": name, "query": args.get("query") or args.get("need") or args.get("url"),
                      "country": args.get("country", "")}, ensure_ascii=False))
    try:
        data = HANDLERS[name](args)
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=1)}], "structuredContent": data}
    except Exception as e:      # bad arguments included: a tool error the model can read and correct, not a protocol error
        return {"content": [{"type": "text", "text": f"Error: {e!r}"}], "isError": True}


def modern(method: str, params: dict) -> dict:
    """2026-07-28: stateless; every result has resultType and our identity in _meta."""
    meta = {"_meta": {M + "serverInfo": SERVER}, "resultType": "complete"}
    if method == "server/discover":
        return {**meta, "supportedVersions": list(MODERN + LEGACY), "capabilities": {"tools": {}},
                "instructions": INSTRUCTIONS, **CACHE}
    if method == "tools/list":
        return {**meta, "tools": TOOLS, **CACHE}
    if method == "tools/call":
        return {**meta, **call_tool(params)}
    raise Reject(404, -32601, f"Method not found: {method}")


def legacy(method: str, params: dict) -> dict:
    """2025-11-25 and earlier: initialize handshake, no sessions minted (each request stands alone anyway)."""
    if method == "initialize":
        v = params.get("protocolVersion")
        return {"protocolVersion": v if v in LEGACY else LEGACY[0], "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER, "instructions": INSTRUCTIONS}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return call_tool(params)
    raise Reject(404, -32601, f"Method not found: {method}")


def _header(headers: dict, name: str) -> str | None:
    v = headers.get(name.lower())
    m = re.fullmatch(r"=\?base64\?(.*)\?=", v or "")
    return base64.b64decode(m.group(1)).decode() if m else v


def check_headers(headers: dict, msg: dict, version: str) -> None:
    """Modern requests mirror version, method and tool name in headers; they must match the body."""
    params = msg.get("params") or {}
    want = {"mcp-protocol-version": version, "mcp-method": msg.get("method")}
    if msg.get("method") in ("tools/call", "prompts/get", "resources/read"):
        want["mcp-name"] = params.get("name") or params.get("uri")
    for h, v in want.items():
        got = _header(headers, h)
        if got != v:
            raise Reject(400, -32020, f"Header mismatch: {h} is {got!r}, body says {v!r}")


def respond(msg: dict, headers: dict) -> tuple[int, dict | None]:
    """One JSON-RPC message -> (HTTP status, response body or None for an accepted notification)."""
    mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if mid is None:                                  # notification (legacy notifications/initialized): accept
        return 202, None
    try:
        version = (params.get("_meta") or {}).get(M + "protocolVersion")
        if version:
            if version not in MODERN:
                raise Reject(400, -32022, "Unsupported protocol version",
                             {"supported": list(MODERN + LEGACY), "requested": version})
            check_headers(headers, msg, version)
            return 200, {"jsonrpc": "2.0", "id": mid, "result": modern(method, params)}
        return 200, {"jsonrpc": "2.0", "id": mid, "result": legacy(method, params)}
    except Reject as e:
        err = {"code": e.code, "message": str(e), **({"data": e.data} if e.data else {})}
        legacy_status = 200 if not (params.get("_meta") or {}).get(M + "protocolVersion") else e.status
        return legacy_status, {"jsonrpc": "2.0", "id": mid, "error": err}


def rpc(msg: dict, headers: dict | None = None) -> dict | None:
    return respond(msg, headers or {})[1]


def handler(event, _ctx=None):
    """Lambda Function URL event -> HTTP response."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "content-type, accept, mcp-protocol-version, mcp-method, mcp-name, mcp-session-id"}
    out = lambda status, body=None, extra=None: {"statusCode": status, "headers": {**cors, **(extra or {})},
                                                 **({"body": json.dumps(body, ensure_ascii=False)} if body is not None else {})}
    origin = headers.get("origin")
    if origin and not re.fullmatch(r"https://[A-Za-z0-9.-]+(:\d+)?", origin):    # DNS-rebinding guard (spec: 403)
        return out(403, {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Forbidden origin"}}, {"Content-Type": "application/json"})
    if method == "OPTIONS":
        return out(204)
    if method != "POST":                              # no GET stream, no sessions to DELETE
        return {"statusCode": 405, "headers": {**cors, "Allow": "POST, OPTIONS", "Content-Type": "text/plain"},
                "body": "Lupamundo MCP server (Streamable HTTP): POST JSON-RPC to this URL. Docs: " + SITE + "/llms.txt"}
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    try:
        msg = json.loads(body)
    except ValueError:
        return out(400, {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}, {"Content-Type": "application/json"})
    if isinstance(msg, list):                         # legacy JSON-RPC batch (2025-03-26)
        res = [r for r in (respond(m, headers)[1] for m in msg) if r]
        return out(200, res, {"Content-Type": "application/json"}) if res else out(202)
    status, res = respond(msg, headers)
    return out(status, res, {"Content-Type": "application/json"}) if res else out(status)
