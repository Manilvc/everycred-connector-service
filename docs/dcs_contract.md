# DCS contract

> Last updated: 2026-10-28

What every DCS instance (EveryCRED backend deployment) must provide for
the connector to route to it. Items 1 and 3 do **not exist in the DCS
yet**; they are the DCS-side work needed before a source can go live.

| # | Direction        | What                                   | Exists in DCS today |
|---|------------------|----------------------------------------|---------------------|
| 1 | DCS → connector  | Signed event webhooks                  | No                  |
| 2 | connector → DCS  | `GET /v1/user/credential/{uuid}`       | Yes (public)        |
| 3 | connector → DCS  | Internal holder API under `/v1/internal/holder` | No         |

## 1. Event webhooks (DCS → connector)

When a credential is issued or revoked, or a credential request is
created or changes state, the DCS posts an event to
`POST {CONNECTOR}/v1/sources/{source_code}/events`.

Headers:

```
Content-Type: application/json
X-EveryCRED-Event: credential.issued
X-EveryCRED-Delivery: <unique id per event; reuse it on retries>
X-EveryCRED-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256>
```

The HMAC is computed over `"<t>.<raw body>"` with the source's webhook
secret (`whsec_...`, returned when the source is registered). This is
the same scheme the integration service uses; its `sign()` helper in
`app/core/signatures.py` can be copied as-is.

Body:

```json
{
  "id": "6f37b4e671f344f99e4a0736491737ea",
  "event": "credential.issued",
  "created_at": "2026-10-21T10:00:00+00:00",
  "data": {
    "credential_id": "00000000-0000-0000-0000-000000000000",
    "request_id": null,
    "holder_email": "holder@example.com",
    "status": "issued"
  }
}
```

| `event`              | Required in `data`  | Effect in the connector                    |
|----------------------|---------------------|--------------------------------------------|
| `credential.issued`  | `credential_id`     | Route the credential to this source        |
| `credential.revoked` | `credential_id`     | Mark the route revoked                     |
| `request.created`    | `request_id`        | Link the holder to this source             |
| `request.updated`    | `request_id`        | Link the holder to this source             |
| `holder.invited`     | `holder_email`      | Link the holder to this source; the holder service shows the invite |

`holder.invited` is sent when an issuer invites a holder by email. Its
`data` carries `holder_email` and an optional `inviter_name` (the
inviting organisation, up to 200 characters) and no ids.

`holder_email` is optional but needed for the holder to see the
credential or request in the wallet. `credential_id` must be the
credential's **`credential_unique_id`**: the id the public view
`GET /v1/user/credential/{uuid}` matches on
(`VerifierMethod.get_credential_by_uuid` filters on
`credential_unique_id`, despite the parameter name), and the id wallets
and verifiers hold. A re-issued credential keeps its
`credential_unique_id`, so it keeps its route. Identifiers must match
`^[A-Za-z0-9._:-]{1,128}$`.

Answers: `202` (applied, or `"duplicate": true` for a repeated delivery
id), `401 invalid_signature`, `404 source_not_found`,
`409 credential_source_conflict`, `422 invalid_event`. Retry on network
errors and 5xx with backoff, keeping the same delivery id.

Where to hook it in the DCS: the places that already call
`notify_credentials_issued()` / `notify_holders()` (issuance in
`certificate_batch_service.py`, revocation in `revocation_service.py`,
re-issue in `tasks/reissue_credential.py`) and the request notifiers
(`notify_holder_requests`). Send from a Celery task after commit, not
inside the request transaction.

## 2. Credential view (connector → DCS)

The connector also forwards verification records to the existing public
`POST {base_url}/v1/credential/verification/analytics?uuid={credential_id}`
(see `POST /v1/credentials/{credential_id}/verification-analytics`). No
change is needed for that either.

The `everycred_dcs` normalizer fetches
`GET {base_url}/v1/user/credential/{credential_id}` and maps the
`{"status", "data", "message"}` answer built by
`VerifierService.view_credentials_service`. No change is needed. The
connector also sends `X-API-Key` (the key given when the source was
registered); the DCS ignores it today.

## 3. Internal holder API (connector → DCS)

The holder service owns holder accounts, so the DCS can no longer
authenticate holders itself for wallet actions. Instead the connector
calls an internal API on the holder's behalf:

```
X-API-Key: <the source API key registered in the connector>
X-Holder-Email: holder@example.com
X-Request-ID: <forwarded request id>
X-Tenant-ID: <the source's tenant_id, when set>
```

When several tenants share one DCS backend, each tenant is its own
source and `X-Tenant-ID` names the tenant, so the DCS uses that tenant's
database and checks the key against that tenant's own
`connector_source_api_key`. The DCS reads the header on the internal
holder API only.

The DCS must check the API key in constant time, resolve the holder by
`X-Holder-Email` in the tenant, and scope every query to that holder,
exactly as the current wallet routes do with the holder from the JWT.
Answers use the existing `{"status", "data", "message"}` envelope; the
connector passes `data` and `message` through with the HTTP status.

| Operation (`app/features/operations/catalog.py`) | Method | Path below `/v1/internal/holder` | Today's wallet route it replaces |
|---|---|---|---|
| `requests.list`        | GET  | `/requests` | `GET /v1/holder/subject/requests` |
| `requests.get`         | GET  | `/requests/{request_id}` | `GET /v1/holder/request/{request_id}` |
| `requests.find`        | GET  | `/requests/{request_id}` (every linked source) | same; used when the wallet sends no source |
| `requests.fields`      | GET  | `/requests/{request_id}/fields` | `GET /v1/wallet/holder/subject/request/fields` |
| `requests.submit`      | POST | `/requests/{request_id}/submission` | `POST /v1/holder/request/submission` |
| `requests.decline`     | POST | `/requests/{request_id}/decline` | `POST /v1/wallet/holder/subject/request/defuse` |
| `kyc.detail`           | GET  | `/kyc-detail` | `GET /v1/wallet/holder/request/kyc-detail` |
| `workflow.list`        | GET  | `/workflow-requests` | `GET /v1/workflow-engine/holder/requests` |
| `workflow.get`         | GET  | `/workflow-requests/{request_uuid}` | `GET .../requests/{request_uuid}` |
| `workflow.consent`     | POST | `/workflow-requests/{request_uuid}/consent` | `POST .../{request_uuid}/consent` |
| `workflow.node_submit` | POST | `/workflow-requests/{request_uuid}/nodes/{node_key}/submit` | `POST .../nodes/{node_key}/submit` |
| `workflow.node_accept` | POST | `/workflow-requests/{request_uuid}/nodes/{node_key}/accept` | `POST .../nodes/{node_key}/accept` |
| `workflow.node_decline`| POST | `/workflow-requests/{request_uuid}/nodes/{node_key}/decline` | `POST .../nodes/{node_key}/decline` |
| `integrations.list`    | GET  | `/requests/{request_id}/integration` | `GET /v1/holder/request/{request_id}/integration` |
| `integrations.start`   | POST | `/requests/{request_id}/integration/{integration_type}/{tool_code}/{flow}/start` | same path under `/v1/holder/...` |
| `integrations.inputs`  | POST | `.../{flow}/inputs` | same |
| `integrations.cancel`  | POST | `.../{flow}/cancel` | same |
| `digilocker.initialize`| POST | `/digilocker/initialize` | `POST /v1/sure-pass/digilocker/initialize` |
| `digilocker.complete`  | GET  | `/digilocker/complete-flow/{client_id}` | `GET /v1/sure-pass/complete-flow/{client_id}` |
| `credentials.stats`    | GET  | `/credentials/{credential_id}/stats` | `GET /v1/holder/stats` |
| `holder.registered`    | PUT  | `/registered` (one source, or every linked source) | none; the holder signed up in the holder service |
| `holder.profile_updated` | PUT | `/profile` (one source, or every linked source) | none; the holder changed their profile in the holder service |

`holder.registered` carries no body. The DCS marks the holder from
`X-Holder-Email` as registered and accepts that holder's open invites.
It must be idempotent, and answer 404 for an email it has no holder
for; the holder service treats that as nothing to update.

`holder.profile_updated` carries the holder's current profile,
`{"name": "<full name>", "mobile": "<number or null>"}`. The DCS stores
it on the holder from `X-Holder-Email`, so issuer screens show the
holder's own details. The same rules apply: idempotent, and 404 for an
unknown email.

Path parameters are URL-encoded by the connector and limited to
`^[A-Za-z0-9._:-]{1,128}$`. Bodies are the JSON the wallet sends today,
up to 256 KiB.

The simplest DCS implementation is a new router that reuses the existing
wallet services, with a dependency that replaces `get_current_holder`
(JWT) by an API-key check plus a holder lookup by email.
