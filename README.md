# ff-secrets-server
Server-side resolver for **ff-secrets**: it turns an opaque alias into a secret value, reading from a backend (today the [1Password Connect Server](https://developer.1password.com/docs/connect/)) and exposing a small read-only HTTP API on the LAN. It owns the alias registry and the backend credential (the bearer); the [`ff-secrets-cli`](https://github.com/magobaol/ff-secrets-cli) client is a thin layer on top of this API.

## How it fits together
ff-secrets is split in two code tools (plus the no-code surfaces that call the API):
- **ff-secrets-server** (this repo): resolver, registry, backend driver and bearer. Runs where the backend lives; exposes the HTTP API.
- **ff-secrets-cli**: the `ff-secrets` command (`read`/`list`/`inject`/`run`) built on the HTTP API. Holds no registry, no bearer, no driver, and cannot reach the backend directly.

A single resolver, registry and bearer live here, so there is nothing to duplicate and no secret material on the clients.

## Aliases and the registry
The registry is a flat `alias: reference` map and is the single source of truth. The consumer asks for an alias and gets the value; it never sees the backend reference. The **last segment of the alias is always the field name** (slug form): the alias is the logical name, the reference carries the real field as the backend stores it.
```
acme.api.credential: op://Vault/ACME API/credential
widget.token:        op://Vault/Widget/token
widget.secret-key:   op://Vault/Widget/secret key
```
A multi-field secret is several aliases under the same prefix.

## HTTP API (read-only)
- `GET /v1/secret/<alias>` returns the value as `text/plain` (200); `404` if the alias is unknown or unreadable; `500` on an unexpected error.
- `GET /v1/aliases?prefix=<p>` returns the alias names, one per line.

Auth is network-level (the deployment binds and firewalls the port); there is no application token, and the API never writes.

## Commands
The same entrypoint runs the API and the admin commands; inside a container, `python bin/ff-secrets <command>`.
### serve
Run the HTTP API.
```
ff-secrets serve --host 0.0.0.0 --port 8666
```
### registry add
Add or update a single alias.
```
ff-secrets registry add <alias> "op://Vault/Item/field"
```
### registry sync
Reconcile the registry with the backend vault: propose aliases for newly discovered secrets and prune aliases whose item or field is gone, with a preview and a confirmation before writing. The prefix of an item already in the registry is inherited; only brand-new items prompt. `--dry-run` previews, `--yes` skips the confirmation.
```
ff-secrets registry sync
```
### read / list
Resolve or list locally on the server, for administration and debugging.

## Configuration
Three runtime files, none committed:
- `config.yaml`: flat `key: value` with `driver`, `backend-endpoint`, `registry`, `bearer-path` (see `config.example.yaml`).
- `registry.yaml`: the alias map. The server re-reads it on every request, so edits take effect without a restart.
- the bearer file: the backend credential, with strict permissions. The only secret material the server holds.

## Deployment
The image is published to GHCR by CI on every push to `main`; the host pulls it and never builds from source.
```
docker compose pull
docker compose up -d
```
A minimal compose, with the three runtime files mounted at `/app/data`:
```yaml
services:
  ff-secrets-server:
    image: ghcr.io/magobaol/ff-secrets-server:latest
    ports:
      - "8666:8666"
    volumes:
      - "./data:/app/data:rw"
    restart: always
```
`data/` is mounted read-write because the `registry` admin commands write `registry.yaml` in place.

> Note: the backend is swappable. The current backend is the 1Password Connect Server, which 1Password now treats as legacy (no official EOL). It is isolated behind the driver interface (`drivers/`), so moving to another backend (a 1Password Service Account, or a different vendor) means writing a new driver, without touching the core, registry, client or consumers.

## Development
```
pip install -r requirements.txt -r requirements-dev.txt
pytest
```
The core, registry and reconciliation logic are pure and covered by an offline suite (the backend SDK is faked). CI runs the suite as a gate before publishing the image.
