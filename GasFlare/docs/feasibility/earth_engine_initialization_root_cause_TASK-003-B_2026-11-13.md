# TASK-003-B: Earth Engine Initialization Failure

Date: 2026-11-13.

## Scope

Compared `scripts/gee/fetch_landsat_night_scene_metadata_2025.py` and
`scripts/gee/landsat_night_pixel_diagnostic_2025.py`, the retained run reports,
and the designated local Python environment. No credentials or credential
files were read. No authentication, project, endpoint, proxy, or package
settings were changed. No asset or pixel request and no diagnostic rerun were
made.

## Actual execution-path differences

| Item | Metadata fetch | Pixel diagnostic |
| --- | --- | --- |
| Project | Same explicit project argument in `ee.Initialize(project=...)`; identifier omitted here. | Same explicit project argument. |
| Credentials | No explicit credentials argument; standard Earth Engine client credential discovery is used. | Same. |
| Initialization call | `ee.Initialize(project=PROJECT)` in `main()`, with the project constant defined in the script. | `ee.Initialize(project=...)` in `main()` only when `--live` is selected. |
| CLI | No CLI mode; running the script enters metadata retrieval. | Requires exactly one of `--offline-plan` or `--live`; the failed run is recorded as `--live`. Offline mode makes no Earth Engine request. |
| Calls after successful initialization | Searches the saved Landsat collection records, then requests metadata and footprint geometries. | Inspects the two selected image assets, then would request a bounded pixel window. The recorded failure occurred before asset inspection. |
| Run evidence | Retained completion record says 90 matched rows, 90 footprint features, and no initialization error. | Retained report records HTTP 403 during initialization/discovery and zero asset or pixel requests. |

No difference in project argument or credential-passing method is evident in
the source. Exact shell command, environment variables, proxy/endpoint override
presence for either historical run, and any process-level environment
differences are unknown. The live diagnostic is not an equivalent request to
the metadata script's later collection/geometry operations: initialization is
the common boundary, and those later calls were not reached by the failed run.

## Environment and retained failure evidence

- Successful metadata-run Python version and Earth Engine client version: **unknown**. Its completion record does not record runtime or dependency versions; do not infer or transfer versions from a later process.
- Diagnostic environment is documented as Python `3.14.7`, `earthengine-api` `1.7.43`, and NumPy `2.5.3`.
- Retained authenticated diagnostic evidence: `ee.Initialize` failed with `HttpError`, HTTP 403. The diagnostic's cleaned message says `HTTP 403; response body suppressed`. It records no host, path, response content type, or structured service reason/message. Thus that retained error alone cannot establish whether the response was HTML or JSON, nor its exact request URL.
- The standard Earth Engine discovery API endpoint is `https://earthengine.googleapis.com/$discovery/rest`. In the same designated Python environment, exactly one unauthenticated GET was sent to this public discovery URL. It returned HTTP 403 with content type `text/html`; the response body was suppressed and not saved. This demonstrates that this unauthenticated request from this environment received an HTML 403. It does not establish the precise response body or that the authenticated client's failed request had identical policy/routing.
- Failure stage for the diagnostic is initialization/discovery, before any collection, image, or pixel API call. No evidence identifies a downstream API failure.
- No clean error message identifies a project, permission, account, or network-blocking cause. The anonymous HTTP 403 is compatible with network/content filtering, but by itself does not prove the filter's source or explain the authenticated response. Project/access rejection also remains possible for the authenticated initialization call, but is not established by the available message.

## Endpoint and proxy settings

Neither script passes an endpoint override to `ee.Initialize`; both use the
client's default endpoint. No proxy or endpoint override values were printed or
inspected. Whether relevant proxy or override environment variables were
present during either historical run is **unknown**. The single anonymous
request used Python's standard URL opener and inherited its normal environment
proxy handling; no override was added. Its result is not an authenticated
Earth Engine access test.

## Assessment and minimum corrective action

There is no source-level difference in explicit project or credentials
handling that explains why the metadata run succeeded and the later diagnostic
initialization failed. The strongest new observation is an unauthenticated
HTTP 403 HTML response from the public discovery URL in the diagnostic
environment, suggesting an access-path restriction as a hypothesis. It does
not prove that hypothesis is the root cause of the earlier authenticated 403;
the exact diagnostic failure host/path and authenticated response type remain
unrecorded.

Smallest safe next step: an authorized environment/network administrator
should review existing outbound proxy/firewall/security-filter logs for the
single diagnostic initialization time, destination host
`earthengine.googleapis.com`, and path `/$discovery/rest`, and determine
whether anonymous and authenticated HTTPS requests are being rejected by
policy. Separately, if network logs show the request reached Google, the
account/project administrator can verify the already-configured identity's
Earth Engine eligibility and project access using the local unredacted
configuration. Do not change credentials, project, endpoint, proxy, VPN, or
packages as a diagnostic guess. Any remediation that requires such a change
needs owner/admin authorization; no retry is authorized by this task.

## Unknowns and limits

- Successful metadata-run Python and package versions, exact invocation,
  environment identity, and proxy/endpoint override presence.
- Exact host, path, and response content type for the authenticated failed
  initialization request.
- Whether the anonymous 403 and authenticated 403 share a cause.
- Whether the rejection originated in local network policy, an intermediary,
  Google service policy, or account/project authorization.
- Whether the configured identity/project would succeed after any remediation.

No asset metadata, image permission, or pixel-access conclusion follows from
these initialization/network observations.
