# Lupamundo MCP server

[![MCP Badge](https://lobehub.com/badge/mcp/lupamundo-lupamundo-mcp)](https://lobehub.com/mcp/lupamundo-lupamundo-mcp)

Spanish buying guides for Mexico and Latin America, for AI assistants: official prices in pesos, English exams
(IELTS, TOEFL, CELPIP), work and study abroad, online courses, eSIM and travel insurance, VPN and cloud storage,
evidence-based wellness. Every answer comes from a published, dated and sourced page on [lupamundo.com](https://lupamundo.com).

**Remote endpoint (Streamable HTTP, no auth):** `https://lupamundo.com/mcp`

## Tools
| Tool | What it does |
|---|---|
| `search_guides` | Finds the guides that answer a question, by country edition (MX, ES, CO, CL, AR, PE, US) |
| `get_guide` | Returns a guide as Markdown: the answer, dated prices, picks, sources |
| `recommend` | Lupamundo's picks for a need (e.g. "app to learn English", "eSIM for Japan"), with links and the commission disclosure |

Read-only, stateless, JSON responses. Supports the 2026-07-28 protocol (stateless, `server/discover`) and legacy
versions back to 2024-11-05.

## Add it
Claude, ChatGPT, Cursor or any MCP client that supports remote servers:
```json
{ "mcpServers": { "lupamundo": { "type": "http", "url": "https://lupamundo.com/mcp" } } }
```
Registry: `com.lupamundo/lupamundo` in the official MCP Registry.

## Funding and disclosure
Lupamundo is free and funded by affiliate commissions: some links pay us a commission if you buy, at no extra cost
to you. Links are returned with that disclosure. Details: <https://lupamundo.com/es-mx/divulgacion/>.

---

# Servidor MCP de Lupamundo (español)
Guías de compra en español para México y Latinoamérica para asistentes de IA: precios oficiales en pesos, exámenes de
inglés, trabajar o estudiar en el extranjero, cursos en línea, eSIM y seguros de viaje, VPN y almacenamiento.
Endpoint: `https://lupamundo.com/mcp`. Cada respuesta sale de una guía publicada, fechada y con fuentes.

© Pine Solutions Inc. Code under the MIT License.
