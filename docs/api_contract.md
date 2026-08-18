# Contrato de API (API Contract Specification v1.3.0)

**API de Verificación de Correos Desechables de Alto Rendimiento**  
**Especificación de Contrato Técnico de Interfaz REST & Model Context Protocol (MCP)**

---

## 1. Información General del Contrato

* **Versión del Contrato:** `v1.3.0`
* **Especificación Base:** OpenAPI 3.0.3 / RFC 7807 Problem Details
* **Arquitectura de Privacidad:** *Privacy-by-Design* (Zero PII Retention)
* **Protocolos de Transporte:** HTTP/1.1, HTTP/2, Stdio JSON-RPC 2.0 (MCP)
* **Formatos de Ingesta/Salida:** `application/json`, `application/x-msgpack`
* **Algoritmos de Compresión:** `zstd` (Zstandard), `gzip`
* **Codificación de Cadenas:** UTF-8 / IDNA Punycode (`xn--`)

---

## 2. Autenticación, Rate Limiting y Encabezados de Auditoría

### 2.1 Esquema de Autenticación
Por defecto, la API permite acceso abierto en desarrollo (`REQUIRE_API_KEY=false`). Cuando la autenticación es requerida en producción (`REQUIRE_API_KEY=true`), el cliente debe incluir la clave de API en las peticiones mediante el encabezado HTTP:

```http
X-API-Key: secret-api-key-change-me-in-production
```

### 2.2 Control de Tasa (Rate Limiting)
El sistema aplica un algoritmo de ventana deslizante (*Sliding Window*) por dirección IP y por clave de API:

| Tipo de Cliente | Límite Predeterminado | Ventana de Tiempo | Encabezados HTTP Retornados |
| :--- | :---: | :---: | :--- |
| **Cliente Anónimo (por IP)** | 100 peticiones | 60 segundos | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` |
| **Cliente Autenticado (API Key)** | 1,000 peticiones | 60 segundos | `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` |

### 2.3 Encabezados HTTP Estándar de Respuesta

```http
X-Request-ID: 5332ee84-afd7-497c-8f55-56c92fc645b6
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Referrer-Policy: no-referrer
Content-Encoding: zstd
ETag: W/"a1b2c3d4e5f67890"
```

---

## 3. Especificación Detallada de Endpoints REST

### 3.1 `POST /v1/verify-email` — Verificación de Correo Individual

Evalúa una dirección de correo electrónico individual aplicando la cascada de 4 niveles (Caché L1, Cuckoo Filter RAM, Caché L2 Redis, DNS MX Pasivo y Motor Heurístico/RapidFuzz C++).

#### Encabezados de la Petición
* `Content-Type`: `application/json` o `application/x-msgpack`
* `Accept`: `application/json` o `application/x-msgpack`

#### Cuerpo de la Petición (Request Body)
```json
{
  "email": "usuario@mailinator.com"
}
```

#### Esquema de Entrada (JSON Schema)
* `email` *(string, requerido)*: Dirección de correo electrónico a verificar (Max 254 caracteres).

---

#### Respuesta Exitosa (`HTTP 200 OK`)
```json
{
  "disposable": true,
  "confidence": "high",
  "reason": "known_provider",
  "risk_score": 100,
  "mx_provider": "Disposable Domain List",
  "did_you_mean": null,
  "request_id": "5332ee84-afd7-497c-8f55-56c92fc645b6"
}
```

#### Especificación de Campos de la Respuesta
| Campo | Tipo | Valores Posibles | Descripción |
| :--- | :---: | :--- | :--- |
| `disposable` | `boolean` | `true`, `false` | `true` si el correo pertenece a un proveedor desechable o sospechoso. |
| `confidence` | `string` | `"high"`, `"medium"`, `"low"` | Nivel de certeza estadística del diagnóstico. |
| `reason` | `string` | `"known_provider"`, `"heuristic"`, `"heuristic_dga"`, `"no_mx"`, `"clean"` | Motivo técnico del diagnóstico. |
| `risk_score` | `integer` | `0` a `100` | Puntaje numérico graduado de riesgo antifraude. |
| `mx_provider` | `string \| null` | Texto o `null` | Nombre del proveedor de infraestructura MX identificado. |
| `did_you_mean` | `string \| null` | Texto o `null` | Sugerencia de corrección tipográfica (ej: `"gmail.com"` para `"gmai.com"`). |
| `request_id` | `string` | UUIDv4 | Identificador único de trazabilidad de la petición. |

---

### 3.2 `POST /v1/verify-batch` — Verificación en Lote Concurrente

Procesa múltiples direcciones de correo de manera concurrente (máximo 100 correos por lote).

#### Cuerpo de la Petición (Request Body)
```json
{
  "emails": [
    "user1@mailinator.com",
    "user2@gmail.com",
    "user3@gmai.com",
    "user4@temp-mail.org"
  ]
}
```

#### Respuesta Exitosa (`HTTP 200 OK`)
```json
{
  "total_processed": 4,
  "results": [
    {
      "email_hash": "a8f5c...12",
      "disposable": true,
      "confidence": "high",
      "reason": "known_provider",
      "risk_score": 100,
      "mx_provider": "Disposable Domain List",
      "did_you_mean": null,
      "request_id": "5332ee84-afd7-497c-8f55-56c92fc645b6"
    },
    {
      "email_hash": "b9e1d...89",
      "disposable": false,
      "confidence": "high",
      "reason": "clean",
      "risk_score": 0,
      "mx_provider": "Whitelisted Domain",
      "did_you_mean": null,
      "request_id": "5332ee84-afd7-497c-8f55-56c92fc645b6"
    }
  ],
  "request_id": "5332ee84-afd7-497c-8f55-56c92fc645b6"
}
```

---

### 3.3 `GET /healthz` — Liveness Probe (Monitoreo de Vida)

Utilizado por Docker y Kubernetes para verificar que el proceso web está activo.

#### Respuesta Exitosa (`HTTP 200 OK`)
```json
{
  "status": "ok"
}
```

---

### 3.4 `GET /readyz` — Readiness Probe (Monitoreo de Disponibilidad)

Verifica que el Cuckoo Filter y la conexión con Redis estén listos para recibir tráfico.

#### Respuesta Exitosa (`HTTP 200 OK`)
```json
{
  "status": "ready",
  "redis_connected": true,
  "bloom_filter_loaded": true
}
```

---

### 3.5 `GET /internal/dataset-info` — Telemetría de Fuentes y Dataset

Expone el estado de sincronización y las fuentes de datos abiertos.

#### Respuesta Exitosa (`HTTP 200 OK`)
```json
{
  "capacity": 500000,
  "target_error_rate": 0.001,
  "engine": "cuckoo",
  "domain_parser": "c_extension",
  "items_count": 127026,
  "dataset_version": "v1.3.0-synced",
  "dataset_hash": "850b8b1244fcaa3fdc94ff07baf509b547f70a4b6176a19a53e5c9d7773117a7",
  "last_sync_timestamp": "2026-08-18T16:10:00.000000+00:00",
  "sources_status": [
    {
      "url": "Internal Seed Dataset",
      "status": "success",
      "domains_count": 19
    },
    {
      "url": "https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/main/disposable_email_blocklist.conf",
      "status": "success",
      "domains_count": 8260
    },
    {
      "url": "https://raw.githubusercontent.com/ivolo/disposable-email-domains/master/index.json",
      "status": "success",
      "domains_count": 121569
    }
  ]
}
```

---

### 3.6 `GET /metrics` — Métricas Prometheus (OpenTelemetry)

Entrega métricas en formato estándar de Prometheus para scraping desde Grafana / Prometheus Server.

---

## 4. Contrato de Herramientas MCP (Model Context Protocol)

Para integración con Agentes de Inteligencia Artificial (Gemini, Claude, OpenAI, Antigravity) vía transporte Stdio o HTTP JSON-RPC 2.0:

### 4.1 Herramienta `verify_email_tool`
* **Parámetros:** `email: str`
* **Retorno:** Objeto JSON minificado optimizado para bajo consumo de tokens.

### 4.2 Herramienta `verify_email_batch_tool`
* **Parámetros:** `emails: list[str]`
* **Retorno:** Resumen de diagnóstico en lote con reducción del 88.6% en consumo de tokens LLM.

### 4.3 Herramienta `get_telemetry_status_tool`
* **Parámetros:** Ninguno
* **Retorno:** Estado del motor Cuckoo y sincronización de fuentes.

---

## 5. Códigos de Estado HTTP y Formato de Errores (RFC 7807)

Los errores de la API cumplen con el estándar **RFC 7807 (Problem Details for HTTP APIs)**:

```json
{
  "type": "https://api.emailverifier.domain/errors/unprocessable-content",
  "title": "Unprocessable Content",
  "status": 422,
  "detail": "Formato de correo electrónico inválido o dominio sintácticamente incorrecto.",
  "instance": "/v1/verify-email"
}
```

| Código HTTP | Significado | Causa |
| :---: | :--- | :--- |
| **`200 OK`** | Petición Procesada Exitosamente | Diagnóstico completado. |
| **`304 Not Modified`** | Sin Cambios en Contenido | Respuesta servida desde caché de cliente vía ETag sin transferencia de payload. |
| **`400 Bad Request`** | Estructura JSON Malformada | Error de sintaxis en cuerpo JSON de la petición. |
| **`401 Unauthorized`** | Clave de API Inválida o Ausente | Encabezado `X-API-Key` incorrecto o faltante cuando la autenticación está activa. |
| **`413 Payload Too Large`** | Lote Excedido | Se enviaron más de 100 correos en `POST /v1/verify-batch`. |
| **`422 Unprocessable Content`** | Error de Validación de Formato | El parámetro `email` no cumple con el formato estándar. |
| **`429 Too Many Requests`** | Límite de Tasa Excedido | El cliente superó la cuota de peticiones por minuto. |
| **`500 Internal Server Error`** | Error Interno de Servidor | Fallo no controlado en la aplicación. |
| **`503 Service Unavailable`** | Servicio No Disponible | Redis o motores probabilísticos en inicialización. |

---

## 6. Ejemplos de Integración Multilenguaje

### 6.1 cURL (CLI)
```bash
curl -X POST http://localhost:8000/v1/verify-email \
  -H "Content-Type: application/json" \
  -d '{"email":"usuario@mailinator.com"}'
```

### 6.2 Python (`httpx`)
```python
import httpx

response = httpx.post(
    "http://localhost:8000/v1/verify-email",
    json={"email": "usuario@mailinator.com"},
    headers={"Accept-Encoding": "zstd"}
)
print(response.json())
```

### 6.3 JavaScript (Browser Fetch / Node.js)
```javascript
const response = await fetch('http://localhost:8000/v1/verify-email', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'usuario@mailinator.com' })
});
const data = await response.json();
console.log(data);
```
