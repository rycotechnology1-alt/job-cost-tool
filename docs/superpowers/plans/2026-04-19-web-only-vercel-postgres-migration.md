# Web-Only Vercel/Postgres Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the desktop product surface, promote hosted runtime defaults, and make the repository deployable on Vercel with Neon Postgres and blob-backed file storage.

**Architecture:** Keep `core/` and `services/` as the shared product engine, remove `app/` and desktop-only product concepts, and make the hosted API/browser path the only supported delivery model. Use root-level Vercel configuration, a Python ASGI entrypoint for the API, Neon Postgres for lineage, Vercel Blob for artifacts, and a browser-to-blob upload flow so large PDFs do not hit Vercel function body limits.

**Tech Stack:** Python, FastAPI, React, Vite, TypeScript, Neon Postgres via `psycopg`, Vercel Blob, Vercel Functions, pytest, unittest

---

## File Structure Map

### Deployment and runtime foundation

- Create: `.python-version`
  - Pin the Python runtime Vercel should use.
- Create: `api/index.py`
  - Expose the top-level ASGI `app` at a Vercel-friendly entrypoint.
- Create: `vercel.json`
  - Declare install/build/output behavior, Python bundle exclusions, and SPA routing.
- Modify: `requirements.txt`
  - Keep only Python runtime dependencies needed by the hosted API.
- Modify: `.env.example`
  - Document hosted defaults and `/tmp` runtime paths for Vercel.
- Modify: `api/settings.py`
  - Default hosted runtime settings to Postgres + blob + `/tmp` paths.
- Modify: `tests/api_settings_tests.py`
  - Lock the new hosted default behavior in tests.

### Desktop surface removal

- Delete: `app/`
  - Remove the entire PySide6 desktop shell.
- Delete: `services/settings_workflow_service.py`
  - Remove filesystem profile-editing orchestration that only existed for the desktop shell.
- Delete: `tests/settings_workflow_service_tests.py`
  - Remove desktop-settings workflow coverage.
- Modify: `tests/profile_config_tests.py`
  - Keep only profile/config behavior that still matters after desktop removal.
- Create: `tests/repo_shape_tests.py`
  - Prevent desktop package and desktop-only service reintroduction.

### Desktop-sync feature removal

- Modify: `core/models/lineage.py`
  - Remove `TrustedProfileSyncExport`.
- Modify: `infrastructure/persistence/lineage_store.py`
  - Remove trusted-profile sync export persistence methods.
- Modify: `infrastructure/persistence/sqlite_lineage_store.py`
  - Delete trusted-profile sync export persistence paths.
- Modify: `infrastructure/persistence/postgres_lineage_store.py`
  - Delete trusted-profile sync export persistence paths.
- Modify: `infrastructure/storage/runtime_storage.py`
  - Remove profile-sync artifact methods from the runtime storage protocol.
- Modify: `infrastructure/storage/local_runtime_file_store.py`
  - Remove local profile-sync artifact behavior.
- Modify: `infrastructure/storage/vercel_blob_runtime_storage.py`
  - Remove blob-backed profile-sync artifact behavior.
- Modify: `services/trusted_profile_authoring_repository.py`
  - Remove trusted-profile sync export repository methods.
- Modify: `services/profile_authoring_service.py`
  - Remove profile-sync export result types and orchestration.
- Modify: `api/schemas/profile_authoring.py`
  - Remove `ProfileSyncExportResponse`.
- Modify: `api/serializers.py`
  - Remove profile-sync serialization helpers.
- Modify: `api/routes/profiles.py`
  - Remove desktop-sync routes and router registrations.
- Modify: `web/src/api/contracts.ts`
  - Remove profile-sync response contracts.
- Modify: `web/src/api/client.ts`
  - Remove profile-sync client helpers.
- Modify: `web/src/App.tsx`
  - Remove desktop-sync actions, messages, and state transitions.
- Modify: `web/src/__tests__/profileSettingsWorkspace.test.tsx`
  - Replace desktop-sync assertions with hosted-only profile settings assertions.
- Modify: `tests/api_tests.py`
  - Remove desktop-sync endpoint coverage and add negative route checks.
- Modify: `tests/profile_authoring_service_tests.py`
  - Remove desktop-sync authoring/export coverage.
- Modify: `tests/trusted_profile_authoring_repository_tests.py`
  - Remove desktop-sync repository coverage.

### Hosted profile/config simplification

- Delete: `config/app_settings.json`
  - Remove desktop active-profile state.
- Modify: `core/config/path_utils.py`
  - Remove app-settings path helpers.
- Modify: `core/config/profile_manager.py`
  - Reduce the manager to profile discovery/metadata utilities only.
- Modify: `core/config/config_loader.py`
  - Stop resolving configs through active desktop profile settings.
- Modify: `services/trusted_profile_provisioning_service.py`
  - Stop using local request context to bootstrap/resolve active filesystem profiles.
- Modify: `services/profile_execution_compatibility_adapter.py`
  - Always materialize temporary execution bundles without shared desktop legacy fallbacks.
- Modify: `services/profile_authoring_service.py`
  - Remove remaining reads of the desktop active profile directory.
- Modify: `tests/profile_config_tests.py`
  - Assert default/bundled profile behavior without app settings.
- Modify: `tests/processing_run_service_tests.py`
  - Update profile-resolution expectations for the hosted-only model.
- Modify: `tests/review_workflow_service_tests.py`
  - Update config-loader setup helpers to explicit/default profile resolution.

### Hosted upload path for Vercel limits

- Create: `api/blob-upload.ts`
  - Node-based Vercel function that issues client upload tokens with `@vercel/blob/client`.
- Modify: `web/package.json`
  - Add `@vercel/blob` for browser uploads.
- Modify: `web/src/api/contracts.ts`
  - Add blob-upload registration request/response shapes if needed.
- Modify: `web/src/api/client.ts`
  - Upload PDFs directly to Blob when hosted uploads are enabled, then register the blob upload with the Python API.
- Modify: `web/src/App.tsx`
  - Use the hosted blob upload path for staged PDFs.
- Modify: `api/schemas/uploads.py`
  - Add a blob-upload registration contract.
- Modify: `api/routes/uploads.py`
  - Add a route that registers a completed blob upload and returns `SourceUploadResponse`.
- Modify: `infrastructure/storage/runtime_storage.py`
  - Add a method for registering an already-uploaded blob-backed source document.
- Modify: `infrastructure/storage/vercel_blob_runtime_storage.py`
  - Persist metadata for client-uploaded source documents without re-uploading bytes.
- Modify: `tests/api_tests.py`
  - Cover blob-upload registration and subsequent processing.
- Modify: `web/src/__tests__/browserWorkflow.test.tsx`
  - Cover hosted blob uploads without hitting `/api/source-documents/uploads`.

### Docs and verification

- Modify: `README.md`
  - Describe the repo as a hosted web/API product.
- Modify: `AGENTS.md`
  - Remove desktop-fallback guidance and promote hosted-only expectations.
- Modify: repo guidance docs that mention desktop fallback
  - Align all active guidance with the new product stance.

## Task 1: Trim Runtime Dependencies And Declare Vercel Entry Points

**Files:**
- Create: `.python-version`
- Create: `api/index.py`
- Create: `vercel.json`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `api/settings.py`
- Test: `tests/api_settings_tests.py`

- [ ] **Step 1: Write the failing hosted-default settings test**

```python
def test_hosted_defaults_use_postgres_blob_and_tmp_paths(self) -> None:
    settings = ApiSettings.from_env({})

    self.assertEqual(settings.database_provider, "postgres")
    self.assertEqual(settings.storage_provider, "vercel_blob")
    self.assertEqual(settings.database_path, "/tmp/job-cost-api/lineage.db")
    self.assertEqual(settings.upload_root, Path("/tmp/job-cost-api/uploads"))
    self.assertEqual(settings.export_root, Path("/tmp/job-cost-api/exports"))
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api_settings_tests.py -k hosted_defaults_use_postgres_blob_and_tmp_paths -q`

Expected: `FAIL` because `ApiSettings.from_env()` still defaults to SQLite and local runtime paths under `runtime/api`.

- [ ] **Step 3: Write the minimal hosted-runtime implementation**

```python
# api/settings.py
runtime_root = Path(environ.get("JOB_COST_API_RUNTIME_ROOT", "/tmp/job-cost-api")).expanduser()
database_provider = str(environ.get("JOB_COST_API_DATABASE_PROVIDER", "postgres")).strip().lower() or "postgres"
database_path = environ.get("JOB_COST_API_DATABASE_PATH") or str(runtime_root / "lineage.db")
storage_provider = str(environ.get("JOB_COST_API_STORAGE_PROVIDER", "vercel_blob")).strip().lower() or "vercel_blob"
upload_root = Path(environ.get("JOB_COST_API_UPLOAD_ROOT", str(runtime_root / "uploads"))).expanduser()
export_root = Path(environ.get("JOB_COST_API_EXPORT_ROOT", str(runtime_root / "exports"))).expanduser()
```

```text
# requirements.txt
pdfplumber
openpyxl
fastapi
httpx
python-multipart
uvicorn
psycopg[binary]
vercel
```

```python
# api/index.py
from api.asgi import app
```

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "installCommand": "npm --prefix web ci",
  "buildCommand": "npm --prefix web run build",
  "outputDirectory": "web/dist",
  "functions": {
    "api/**/*.py": {
      "excludeFiles": "{app/**,tests/**,docs/**,runtime/**,tools/**,.venv/**,web/**,__pycache__/**,tests/_*/**}"
    }
  },
  "rewrites": [
    { "source": "/((?!api/).*)", "destination": "/index.html" }
  ]
}
```

```text
# .python-version
3.12
```

```dotenv
# .env.example
JOB_COST_API_DATABASE_PROVIDER=postgres
JOB_COST_API_POSTGRES_ADMIN_URL=
JOB_COST_API_POSTGRES_POOLED_URL=
JOB_COST_API_POSTGRES_SCHEMA=public
JOB_COST_API_AUTH_MODE=local
JOB_COST_API_AUTH_SECRET=
JOB_COST_API_STORAGE_PROVIDER=vercel_blob
BLOB_READ_WRITE_TOKEN=
JOB_COST_API_RUNTIME_ROOT=/tmp/job-cost-api
JOB_COST_API_UPLOAD_ROOT=/tmp/job-cost-api/uploads
JOB_COST_API_EXPORT_ROOT=/tmp/job-cost-api/exports
```

- [ ] **Step 4: Run the focused verification**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api_settings_tests.py -q`

Expected: `PASS`

Run: `.\.venv\Scripts\python.exe -c "from api.index import app; print(app.title)"`

Expected: `Job Cost Tool API`

Run: `npm --prefix web run build`

Expected: `vite ... built in ...`

- [ ] **Step 5: Commit**

```bash
git add .python-version api/index.py vercel.json requirements.txt .env.example api/settings.py tests/api_settings_tests.py
git commit -m "chore: declare hosted runtime defaults and vercel entrypoints"
```

## Task 2: Remove The Desktop Shell And Desktop-Only Services

**Files:**
- Delete: `app/`
- Delete: `services/settings_workflow_service.py`
- Delete: `tests/settings_workflow_service_tests.py`
- Modify: `tests/profile_config_tests.py`
- Create: `tests/repo_shape_tests.py`

- [ ] **Step 1: Write the failing repo-shape regression test**

```python
from pathlib import Path
import unittest


class RepoShapeTests(unittest.TestCase):
    def test_repository_no_longer_contains_desktop_surface(self) -> None:
        self.assertFalse(Path("app").exists())
        self.assertFalse(Path("services/settings_workflow_service.py").exists())
        self.assertNotIn(
            "PySide6",
            {line.strip() for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines()},
        )
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/repo_shape_tests.py -q`

Expected: `FAIL` because `app/` and `services/settings_workflow_service.py` still exist.

- [ ] **Step 3: Delete the desktop shell and trim the remaining config tests**

```text
Delete these paths:
- app/
- services/settings_workflow_service.py
- tests/settings_workflow_service_tests.py
```

```python
# tests/profile_config_tests.py
# Keep only config/profile tests that exercise:
# - ProfileManager profile discovery and metadata
# - ConfigLoader required/optional file loading
# - slot/rates/template metadata normalization
#
# Remove tests that instantiate:
# - ReviewViewModel
# - SettingsViewModel
# - any desktop-only workflow state
```

- [ ] **Step 4: Run the focused verification**

Run: `.\.venv\Scripts\python.exe -m pytest tests/repo_shape_tests.py tests/profile_config_tests.py -q`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/repo_shape_tests.py tests/profile_config_tests.py requirements.txt
git rm -r app services/settings_workflow_service.py tests/settings_workflow_service_tests.py
git commit -m "refactor: remove desktop shell and desktop-only services"
```

## Task 3: Remove Desktop-Sync From Domain, API, Storage, And Web

**Files:**
- Modify: `core/models/lineage.py`
- Modify: `infrastructure/persistence/lineage_store.py`
- Modify: `infrastructure/persistence/sqlite_lineage_store.py`
- Modify: `infrastructure/persistence/postgres_lineage_store.py`
- Modify: `infrastructure/storage/runtime_storage.py`
- Modify: `infrastructure/storage/local_runtime_file_store.py`
- Modify: `infrastructure/storage/vercel_blob_runtime_storage.py`
- Modify: `services/trusted_profile_authoring_repository.py`
- Modify: `services/profile_authoring_service.py`
- Modify: `api/schemas/profile_authoring.py`
- Modify: `api/serializers.py`
- Modify: `api/routes/profiles.py`
- Modify: `web/src/api/contracts.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/__tests__/profileSettingsWorkspace.test.tsx`
- Modify: `tests/api_tests.py`
- Modify: `tests/profile_authoring_service_tests.py`
- Modify: `tests/trusted_profile_authoring_repository_tests.py`

- [ ] **Step 1: Write the failing hosted-only regression tests**

```python
def test_profile_sync_endpoint_is_not_registered(self) -> None:
    version_id = "trusted-profile-version:org-default:default:v1"

    response = self.client.post(f"/api/profile-versions/{version_id}/desktop-sync-export")

    self.assertEqual(response.status_code, 404)
```

```tsx
it("does not offer any desktop sync action in the hosted profile settings flow", async () => {
  render(<App />);

  expect(screen.queryByRole("button", { name: /desktop sync/i })).not.toBeInTheDocument();
  expect(screen.queryByText(/manual desktop sync/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api_tests.py -k profile_sync_endpoint_is_not_registered -q`

Expected: `FAIL` because the route still exists.

Run: `npm --prefix web test -- --run profileSettingsWorkspace`

Expected: `FAIL` because the current app/web client still contains desktop-sync imports and actions.

- [ ] **Step 3: Remove the desktop-sync feature end to end**

```python
# core/models/lineage.py
# Delete TrustedProfileSyncExport entirely.
```

```python
# infrastructure/storage/runtime_storage.py
class RuntimeStorage(Protocol):
    def save_upload(...): ...
    def get_upload(...): ...
    def cleanup_expired_uploads(...): ...
    def save_export_artifact(...): ...
    def get_export_artifact(...): ...
    def delete_export_artifact(...): ...
```

```python
# api/routes/profiles.py
profiles_router = APIRouter(prefix="/api/profiles", tags=["profiles"])
profile_drafts_router = APIRouter(prefix="/api/profile-drafts", tags=["profile-drafts"])

# Remove:
# - profile_versions_router
# - profile_sync_exports_router
# - create_profile_sync_export()
# - download_profile_sync_export()
```

```ts
// web/src/api/client.ts
// Remove createProfileSyncExport() entirely.
```

```tsx
// web/src/App.tsx
// Remove:
// - createProfileSyncExport import
// - ProfileSyncExportResponse import
// - desktop sync button/action
// - manual desktop sync success messaging
```

- [ ] **Step 4: Run the focused verification**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api_tests.py tests/profile_authoring_service_tests.py tests/trusted_profile_authoring_repository_tests.py -k "profile_sync or desktop_sync" -q`

Expected: `0 selected` or `PASS` after removing/rewriting desktop-sync coverage.

Run: `npm --prefix web test -- --run profileSettingsWorkspace`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add core/models/lineage.py infrastructure/persistence/lineage_store.py infrastructure/persistence/sqlite_lineage_store.py infrastructure/persistence/postgres_lineage_store.py infrastructure/storage/runtime_storage.py infrastructure/storage/local_runtime_file_store.py infrastructure/storage/vercel_blob_runtime_storage.py services/trusted_profile_authoring_repository.py services/profile_authoring_service.py api/schemas/profile_authoring.py api/serializers.py api/routes/profiles.py web/src/api/contracts.ts web/src/api/client.ts web/src/App.tsx web/src/__tests__/profileSettingsWorkspace.test.tsx tests/api_tests.py tests/profile_authoring_service_tests.py tests/trusted_profile_authoring_repository_tests.py
git commit -m "refactor: remove desktop sync feature surface"
```

## Task 4: Remove Active-Profile Desktop State And Narrow Filesystem Compatibility

**Files:**
- Delete: `config/app_settings.json`
- Modify: `core/config/path_utils.py`
- Modify: `core/config/profile_manager.py`
- Modify: `core/config/config_loader.py`
- Modify: `services/trusted_profile_provisioning_service.py`
- Modify: `services/profile_execution_compatibility_adapter.py`
- Modify: `services/profile_authoring_service.py`
- Modify: `tests/profile_config_tests.py`
- Modify: `tests/processing_run_service_tests.py`
- Modify: `tests/review_workflow_service_tests.py`

- [ ] **Step 1: Write the failing hosted-profile resolution regression test**

```python
def test_resolve_current_published_profile_ignores_desktop_active_profile_settings(self) -> None:
    (TEST_ROOT / "config" / "app_settings.json").write_text('{"active_profile":"alternate"}', encoding="utf-8")

    self.provisioning_service.ensure_organization_default_profile(organization_id="org-default")

    resolved = self.provisioning_service.resolve_current_published_profile(
        profile_name=None,
        request_context=LOCAL_REQUEST_CONTEXT,
    )

    self.assertEqual(resolved.trusted_profile.profile_name, "default")
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/processing_run_service_tests.py -k ignores_desktop_active_profile_settings -q`

Expected: `FAIL` because the provisioning service still resolves the local active profile through `ProfileManager`.

- [ ] **Step 3: Write the minimal hosted-only config/provisioning implementation**

```python
# core/config/path_utils.py
def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]

def get_profiles_root() -> Path:
    return get_project_root() / "profiles"

def get_legacy_config_root() -> Path:
    return get_project_root() / "config"
```

```python
# core/config/profile_manager.py
class ProfileManager:
    def __init__(self, profiles_root: Path | None = None, legacy_config_root: Path | None = None) -> None:
        self._profiles_root = (profiles_root or get_profiles_root()).resolve()
        self._legacy_config_root = (legacy_config_root or get_legacy_config_root()).resolve()

    def list_profiles(self) -> list[dict[str, Any]]: ...
    def get_profile_dir(self, profile_name: str) -> Path | None: ...
    def get_profile_metadata(self, profile_name: str) -> dict[str, Any]: ...
```

```python
# core/config/config_loader.py
if config_dir is not None:
    self._config_dir = config_dir.resolve()
elif context_override is not None:
    self._config_dir = context_override[0]
else:
    default_profile_dir = ProfileManager().get_profile_dir("default")
    if default_profile_dir is None:
        raise FileNotFoundError("Bundled default profile is missing.")
    self._config_dir = default_profile_dir
```

```python
# services/trusted_profile_provisioning_service.py
def _ensure_profiles_available(self, *, organization: Organization, request_context: RequestContext | None) -> None:
    self.ensure_organization_default_profile(organization_id=organization.organization_id)

def _resolve_selected_profile_name(self, profile_name: str | None) -> str:
    return str(profile_name or "").strip() or "default"
```

```python
# services/profile_execution_compatibility_adapter.py
@contextmanager
def _temporary_legacy_config_dir(self) -> Iterator[Path]:
    with TemporaryDirectory(prefix="job-cost-materialized-legacy-") as legacy_tmp:
        legacy_config_dir = Path(legacy_tmp).resolve()
        (legacy_config_dir / "phase_catalog.json").write_text('{"phases":[]}', encoding="utf-8")
        yield legacy_config_dir

# Remove _get_shared_legacy_config_dir() and all calls to it.
```

- [ ] **Step 4: Run the focused verification**

Run: `.\.venv\Scripts\python.exe -m pytest tests/profile_config_tests.py tests/processing_run_service_tests.py tests/review_workflow_service_tests.py -q`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add core/config/path_utils.py core/config/profile_manager.py core/config/config_loader.py services/trusted_profile_provisioning_service.py services/profile_execution_compatibility_adapter.py services/profile_authoring_service.py tests/profile_config_tests.py tests/processing_run_service_tests.py tests/review_workflow_service_tests.py
git rm config/app_settings.json
git commit -m "refactor: remove desktop active-profile compatibility"
```

## Task 5: Add A Hosted Blob Upload Path For Vercel Function Limits

**Files:**
- Create: `api/blob-upload.ts`
- Modify: `web/package.json`
- Modify: `web/src/api/contracts.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/App.tsx`
- Modify: `api/schemas/uploads.py`
- Modify: `api/routes/uploads.py`
- Modify: `infrastructure/storage/runtime_storage.py`
- Modify: `infrastructure/storage/vercel_blob_runtime_storage.py`
- Modify: `tests/api_tests.py`
- Modify: `web/src/__tests__/browserWorkflow.test.tsx`

- [ ] **Step 1: Write the failing API and browser regression tests**

```python
def test_registered_blob_upload_can_be_processed(self) -> None:
    response = self.client.post(
        "/api/source-documents/blob-uploads",
        json={
            "storage_ref": "uploads/upload-1/report.pdf",
            "original_filename": "report.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 7340032,
        },
    )

    self.assertEqual(response.status_code, 201)
    upload_id = response.json()["upload_id"]

    run_response = self.client.post(
        "/api/runs",
        json={"upload_id": upload_id, "trusted_profile_name": "default"},
    )

    self.assertEqual(run_response.status_code, 201)
```

```tsx
it("uploads staged PDFs through Vercel Blob instead of the Python upload route when hosted uploads are enabled", async () => {
  vi.stubEnv("VITE_ENABLE_BLOB_CLIENT_UPLOADS", "true");

  const user = userEvent.setup();
  render(<App />);

  await user.upload(
    screen.getByLabelText(/source report pdf/i),
    new File(["pdf-bytes"], "report.pdf", { type: "application/pdf" }),
  );

  await user.click(screen.getByRole("button", { name: /process source pdf/i }));

  expect(uploadMock).toHaveBeenCalled();
  expect(fetchCalls.some(([url]) => url === "/api/source-documents/uploads")).toBe(false);
  expect(fetchCalls.some(([url]) => url === "/api/source-documents/blob-uploads")).toBe(true);
});
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api_tests.py -k registered_blob_upload_can_be_processed -q`

Expected: `FAIL` because the blob-registration route does not exist.

Run: `npm --prefix web test -- --run browserWorkflow`

Expected: `FAIL` because the browser client still posts files to `/api/source-documents/uploads`.

- [ ] **Step 3: Implement the direct-to-blob upload flow**

```ts
// api/blob-upload.ts
import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";

export default async function handler(request: Request): Promise<Response> {
  const body = (await request.json()) as HandleUploadBody;

  const jsonResponse = await handleUpload({
    body,
    request,
    onBeforeGenerateToken: async () => ({
      allowedContentTypes: ["application/pdf"],
      addRandomSuffix: false,
    }),
    onUploadCompleted: async () => {},
  });

  return Response.json(jsonResponse);
}
```

```python
# api/schemas/uploads.py
class BlobUploadRegistrationRequest(ApiModel):
    storage_ref: str
    original_filename: str
    content_type: str
    file_size_bytes: int
```

```python
# infrastructure/storage/runtime_storage.py
class RuntimeStorage(Protocol):
    def register_blob_upload(
        self,
        *,
        storage_ref: str,
        original_filename: str,
        content_type: str,
        file_size_bytes: int,
    ) -> StoredUpload: ...
```

```python
# infrastructure/storage/vercel_blob_runtime_storage.py
def register_blob_upload(
    self,
    *,
    storage_ref: str,
    original_filename: str,
    content_type: str,
    file_size_bytes: int,
) -> StoredUpload:
    upload_id = self._normalize_storage_ref(storage_ref, expected_prefix="uploads/").split("/")[1]
    created_at = self._normalize_timestamp(self._now_provider())
    metadata = {
        "upload_id": upload_id,
        "original_filename": self._normalize_filename(original_filename),
        "content_type": content_type or "application/octet-stream",
        "file_size_bytes": file_size_bytes,
        "storage_ref": storage_ref,
        "filename": self._normalize_filename(original_filename),
        "created_at": created_at.isoformat(),
        "expires_at": self._expires_at(created_at).isoformat() if self._upload_retention_hours > 0 else None,
    }
    self._write_metadata_blob(pathname=self._metadata_path_for_upload(upload_id), metadata=metadata)
    return StoredUpload(
        upload_id=upload_id,
        original_filename=metadata["original_filename"],
        content_type=metadata["content_type"],
        file_size_bytes=file_size_bytes,
        storage_ref=storage_ref,
        file_path=self._upload_root / Path(storage_ref),
        created_at=created_at,
    )
```

```python
# api/routes/uploads.py
@router.post("/blob-uploads", response_model=SourceUploadResponse, status_code=status.HTTP_201_CREATED)
def register_blob_upload(
    request: BlobUploadRegistrationRequest,
    runtime: ApiRuntime = Depends(get_runtime),
) -> SourceUploadResponse:
    upload = runtime.file_store.register_blob_upload(
        storage_ref=request.storage_ref,
        original_filename=request.original_filename,
        content_type=request.content_type,
        file_size_bytes=request.file_size_bytes,
    )
    return to_upload_response(upload)
```

```ts
// web/src/api/client.ts
import { upload } from "@vercel/blob/client";

export async function uploadSourceDocument(file: File): Promise<SourceUploadResponse> {
  if (import.meta.env.VITE_ENABLE_BLOB_CLIENT_UPLOADS === "true") {
    const pathname = `uploads/${crypto.randomUUID()}/${file.name}`;
    const blob = await upload(pathname, file, {
      access: "private",
      handleUploadUrl: "/api/blob-upload",
    });
    return apiJson<SourceUploadResponse>(
      "/api/source-documents/blob-uploads",
      buildJsonRequest({
        storage_ref: blob.pathname,
        original_filename: file.name,
        content_type: file.type || "application/pdf",
        file_size_bytes: file.size,
      }),
    );
  }

  const formData = new FormData();
  formData.append("file", file);
  return apiJson<SourceUploadResponse>("/api/source-documents/uploads", { method: "POST", body: formData });
}
```

- [ ] **Step 4: Run the focused verification**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api_tests.py -k registered_blob_upload_can_be_processed -q`

Expected: `PASS`

Run: `npm --prefix web test -- --run browserWorkflow`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add api/blob-upload.ts web/package.json web/src/api/contracts.ts web/src/api/client.ts web/src/App.tsx api/schemas/uploads.py api/routes/uploads.py infrastructure/storage/runtime_storage.py infrastructure/storage/vercel_blob_runtime_storage.py tests/api_tests.py web/src/__tests__/browserWorkflow.test.tsx
git commit -m "feat: add hosted blob upload flow for source PDFs"
```

## Task 6: Update Docs And Run Full Hosted-Only Verification

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/specs/2026-04-19-web-only-vercel-postgres-design.md` only if wording drifted during implementation
- Test: `tests/repo_shape_tests.py`
- Test: `tests/api_tests.py`
- Test: `tests/processing_run_service_tests.py`
- Test: `tests/review_session_service_tests.py`
- Test: `tests/profile_authoring_service_tests.py`
- Test: `tests/trusted_profile_authoring_repository_tests.py`
- Test: `tests/postgres_lineage_store_tests.py`
- Test: `tests/runtime_storage_tests.py`
- Test: `tests/profile_config_tests.py`

- [ ] **Step 1: Write the failing doc-alignment regression test**

```python
def test_active_guidance_no_longer_describes_desktop_fallback(self) -> None:
    for path in [Path("README.md"), Path("AGENTS.md")]:
        text = path.read_text(encoding="utf-8").casefold()
        self.assertNotIn("desktop fallback", text)
        self.assertNotIn("pyside6", text)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/repo_shape_tests.py -k active_guidance_no_longer_describes_desktop_fallback -q`

Expected: `FAIL` because both docs still describe the desktop shell as active.

- [ ] **Step 3: Rewrite the active docs to the hosted-only stance**

```markdown
# README.md
- describe `api/` + `web/` as the only supported delivery surfaces
- describe Neon Postgres + Vercel Blob as the hosted deployment model
- remove any references to PySide6, desktop fallback, desktop sync, or desktop correctness reference paths
```

```markdown
# AGENTS.md
- remove "desktop fallback" and "desktop still matters" guidance
- keep shared-engine/service separation rules
- describe the repo as web/API hosted delivery over shared core/services/infrastructure seams
```

- [ ] **Step 4: Run the full verification sweep**

Run: `.\.venv\Scripts\python.exe -m pytest tests/repo_shape_tests.py tests/api_tests.py tests/processing_run_service_tests.py tests/review_session_service_tests.py tests/profile_authoring_service_tests.py tests/trusted_profile_authoring_repository_tests.py tests/postgres_lineage_store_tests.py tests/runtime_storage_tests.py tests/profile_config_tests.py -q`

Expected: `all targeted Python suites pass`

Run: `npm --prefix web test`

Expected: `all browser tests pass`

Run: `npm --prefix web run build`

Expected: `vite ... built in ...`

Run: `vercel build`

Expected: `build completes without bundle-size failure and emits a deployable output`

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md docs/superpowers/specs/2026-04-19-web-only-vercel-postgres-design.md tests/repo_shape_tests.py tests/api_tests.py tests/processing_run_service_tests.py tests/review_session_service_tests.py tests/profile_authoring_service_tests.py tests/trusted_profile_authoring_repository_tests.py tests/postgres_lineage_store_tests.py tests/runtime_storage_tests.py tests/profile_config_tests.py web/package.json web/src/__tests__/browserWorkflow.test.tsx web/src/__tests__/profileSettingsWorkspace.test.tsx
git commit -m "docs: finalize hosted-only web deployment guidance"
```

## Self-Review

### Spec coverage

- Desktop surface removal: covered by Tasks 1-2.
- Desktop-sync feature removal: covered by Task 3.
- Hosted-only profile/config simplification: covered by Task 4.
- Vercel + Neon + blob-backed runtime posture: covered by Tasks 1, 4, and 5.
- Vercel body-size-safe upload flow: covered by Task 5.
- Docs and verification: covered by Task 6.

### Placeholder scan

- No `TODO`, `TBD`, or "similar to above" placeholders remain.
- Every task names exact files, exact commands, and concrete code/test snippets.
- The only intentionally broad step is doc rewriting, but it still names the required content changes explicitly.

### Type consistency

- Hosted runtime settings consistently use `database_provider="postgres"` and `storage_provider="vercel_blob"`.
- The new hosted upload registration contract consistently uses `BlobUploadRegistrationRequest` and `register_blob_upload(...)`.
- Desktop-sync terms are removed consistently from model, persistence, storage, service, API, and web layers.
