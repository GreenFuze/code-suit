
```markdown
# Plan: DB-backed Workspace Graph (no full in-memory graph)

> Goal: `WorkspaceGraph` is a **facade over a persistent graph store**.  
> It supports **add/update/remove/query** operations directly against the DB, and every query returns a **Subgraph** (a small, validated Pydantic object).  
> Location: `src/suitcode/core/models/`  
> State: `<workspace-root>/.suit/`

---

## 0) Decisions and invariants (lock these first)
- [ ] **Graph is DB-first**: no “load whole graph into memory” API in v0.
- [ ] **Queries return Subgraph**: a bounded set of nodes/edges/evidence.
- [ ] **Stable IDs**: deterministic, namespaced string IDs (no UUIDs in agent-facing IDs).
- [ ] **Strict validation**: Pydantic `extra="forbid"`, strong typing, fail-fast exceptions.
- [ ] **Deterministic ordering**: every query result has stable ordering (nodes and edges sorted).
- [ ] **Hard limits**: query methods require `max_nodes`, `max_edges`, and `depth` to avoid accidental explosions.
- [ ] **Provider-scoped updates**: providers write within a declared “scope” and stale graph items in that scope can be removed deterministically.
- [ ] **Compatibility bridge** (if needed): keep `src/suitcode/core/architecture/models.py` as re-export/import shim that points to the new models in `core/models/`.

---

## 1) Pydantic models (value objects only, no “whole graph” object)
**Files**
- [ ] `src/suitcode/core/models/graph_types.py`
- [ ] `src/suitcode/core/models/nodes.py`
- [ ] `src/suitcode/core/models/edges.py`
- [ ] `src/suitcode/core/models/subgraph.py`

### 1.1 Core types/enums
- [ ] Define:
  - [ ] `NodeId = str`, `EvidenceId = str`
  - [ ] `NodeKind`, `EdgeKind`
  - [ ] `BuildSystemKind`, `ProgrammingLanguage`, `ComponentKind`, `TestFramework`

### 1.2 Node models (minimal, stable)
- [ ] `GraphNode(id, kind, name, evidence_ids=())`
- [ ] Specialized nodes (keep fields small and provider-neutral):
  - [ ] `RepositoryInfo(root_path)`
  - [ ] `BuildSystemInfo(build_system, configuration_name, tool_version=None, structural_fingerprint=None)`
  - [ ] `Component(component_kind, language, source_roots=(), artifact_paths=())`
  - [ ] `Aggregator()`
  - [ ] `Runner(argv=(), cwd=None)`
  - [ ] `TestDefinition(framework, test_files=())`
  - [ ] `PackageManager(manager, lockfile_path=None)`
  - [ ] `ExternalPackage(manager_id=None, version_spec=None)`
  - [ ] `Evidence(file_path=None, line_start=None, line_end=None, tool=None, message=None, log_path=None)`

### 1.3 Edge model
- [ ] `Edge(kind, src, dst, evidence_ids=())`

### 1.4 Subgraph model (query result)
- [ ] `Subgraph(nodes: dict[NodeId, GraphNode], edges: tuple[Edge, ...], evidence: dict[EvidenceId, Evidence])`
- [ ] Add `Subgraph.validate_integrity()`:
  - [ ] edges refer to returned nodes
  - [ ] evidence_ids refer to returned evidence
  - [ ] deterministic ordering enforced

✅ Gate: unit tests for models + Subgraph integrity pass.

---

## 2) Storage: SQLite graph store (DB is the source of truth)
**Files**
- [ ] `src/suitcode/core/models/store/interfaces.py`
- [ ] `src/suitcode/core/models/store/sqlite_store.py`
- [ ] `src/suitcode/core/models/store/migrations.py`

### 2.1 DB location and setup
- [ ] DB path: `<root>/.suit/db/workspace.sqlite3`
- [ ] SQLite config:
  - [ ] WAL mode
  - [ ] busy_timeout
  - [ ] foreign_keys ON (where applicable)
- [ ] Fail-fast if schema version mismatch.

### 2.2 Tables (normalized for graph queries)
- [ ] `meta(schema_version, workspace_root, created_at, updated_at)`
- [ ] `nodes(id PRIMARY KEY, kind, name, payload_json, payload_sha, updated_at, scope)`
- [ ] `edges(src, kind, dst, payload_json, payload_sha, updated_at, scope, PRIMARY KEY(src, kind, dst))`
- [ ] `evidence(id PRIMARY KEY, payload_json, payload_sha, updated_at, scope)`
- [ ] Indexes (must-have for subgraph queries):
  - [ ] `idx_nodes_kind_name(kind, name)`
  - [ ] `idx_edges_src_kind(src, kind)`
  - [ ] `idx_edges_dst_kind(dst, kind)`
  - [ ] `idx_nodes_scope(scope)`
  - [ ] `idx_edges_scope(scope)`
- [ ] Optional run bookkeeping (recommended):
  - [ ] `runs(run_id PRIMARY KEY, provider, config_id, started_at, finished_at, status, logs_path, structural_fingerprint, scope)`

### 2.3 Store interface (strict, typed)
- [ ] Define `GraphStore` methods:
  - [ ] `initialize(...)`
  - [ ] `begin()` / `commit()` / `rollback()` (or context manager)
  - [ ] `upsert_node(node: GraphNode, scope: str) -> None`
  - [ ] `delete_node(node_id: NodeId) -> None` (fail-fast if referenced unless cascading policy is defined)
  - [ ] `upsert_edge(edge: Edge, scope: str) -> None`
  - [ ] `delete_edge(src: NodeId, kind: EdgeKind, dst: NodeId) -> None`
  - [ ] `upsert_evidence(e: Evidence, scope: str) -> None`
  - [ ] `get_node(node_id: NodeId) -> GraphNode`
  - [ ] `get_edges_from(src: NodeId, kinds: set[EdgeKind] | None, limit: int) -> tuple[Edge, ...]`
  - [ ] `get_edges_to(dst: NodeId, kinds: set[EdgeKind] | None, limit: int) -> tuple[Edge, ...]`
  - [ ] `purge_scope(scope: str) -> None` OR `purge_scope_except(scope: str, seen_ids: ...)` (see §5)

✅ Gate: store round-trip and constraint tests pass.

---

## 3) WorkspaceGraph facade (DB-backed graph API)
**Files**
- [ ] `src/suitcode/core/models/workspace_graph.py`
- [ ] `src/suitcode/core/models/queries.py`

### 3.1 WorkspaceGraph responsibilities
- [ ] Owns a `GraphStore` instance and the workspace root.
- [ ] Provides **high-level typed methods** for agents/providers:
  - [ ] `add_or_update_node(node: GraphNode, scope: str) -> None`
  - [ ] `add_or_update_edge(edge: Edge, scope: str) -> None`
  - [ ] `add_or_update_evidence(e: Evidence, scope: str) -> None`
  - [ ] `remove_node(node_id: NodeId) -> None`
  - [ ] `remove_edge(src, kind, dst) -> None`
  - [ ] `get_node(node_id: NodeId, expected_kind: NodeKind | None = None) -> GraphNode`
- [ ] All methods must be fail-fast with typed exceptions and remediation hints.

### 3.2 Query API that returns Subgraph (bounded)
Implement queries as explicit methods, not an ad-hoc SQL surface:

- [ ] `query_subgraph(seed_ids: list[NodeId], depth: int, edge_kinds: set[EdgeKind] | None, node_kinds: set[NodeKind] | None, max_nodes: int, max_edges: int) -> Subgraph`
  - [ ] deterministic traversal (BFS, stable queue ordering)
  - [ ] deterministic ordering in result (sort nodes by id, edges by (kind, src, dst))
  - [ ] hard limits enforced
- [ ] Convenience queries (all return Subgraph):
  - [ ] `query_components(max_nodes: int) -> Subgraph`
  - [ ] `query_component_by_name(name: str, max_nodes: int) -> Subgraph`
  - [ ] `query_dependents(node_id: NodeId, depth: int, max_nodes: int, max_edges: int) -> Subgraph`
  - [ ] `query_dependencies(node_id: NodeId, depth: int, max_nodes: int, max_edges: int) -> Subgraph`

✅ Gate: query tests ensure deterministic ordering and limit behavior.

---

## 4) Canonical serialization (for hashing and change detection)
**Files**
- [ ] `src/suitcode/core/models/serialization.py`

- [ ] Implement canonical JSON dumps for:
  - [ ] `GraphNode` payload JSON in DB (sorted keys)
  - [ ] `Edge` payload JSON
  - [ ] `Subgraph` output (sorted nodes, sorted edges, sorted evidence)
- [ ] Store `payload_sha` for nodes/edges/evidence to avoid unnecessary rewrites.

✅ Gate: canonical serialization stability tests pass.

---

## 5) Update protocol for frequent changes (provider “scope” + purge strategy)
**Files**
- [ ] `src/suitcode/core/models/update.py`
- [ ] `src/suitcode/core/models/provider_contract.py`

### 5.1 Provider scope model (crucial)
- [ ] Define scope string format:
  - [ ] example: `provider:npm:default`, `provider:cargo:default`, `provider:cmake:<profile>`
- [ ] All writes from a provider refresh must include the same scope.

### 5.2 Refresh transaction pattern (atomic)
- [ ] Implement `WorkspaceGraph.refresh(scope: str, writer_fn: Callable[[GraphWriter], None]) -> None`
  - [ ] begins transaction
  - [ ] creates `GraphWriter` that records “seen IDs” (nodes, edges, evidence)
  - [ ] writer upserts items with scope and records seen IDs
  - [ ] at end: purge stale items in scope that were not seen
  - [ ] commit, else rollback

### 5.3 Purge stale items deterministically
- [ ] Implement `purge_scope_not_seen(scope, seen_node_ids, seen_edge_keys, seen_evidence_ids)`:
  - [ ] delete edges not seen first
  - [ ] delete nodes not seen next (after edge cleanup)
  - [ ] delete evidence not seen last

✅ Gate: refresh tests prove stale deletion and atomicity.

---

## 6) Typed exceptions (fail-fast, actionable)
**Files**
- [ ] `src/suitcode/core/models/errors.py`

- [ ] Exceptions:
  - [ ] `GraphIntegrityError` (missing endpoints, invalid kinds)
  - [ ] `GraphStoreError` (db issues, migration mismatch)
  - [ ] `GraphQueryLimitError` (max nodes/edges exceeded)
  - [ ] `GraphNotFoundError` (node/edge missing)
  - [ ] `GraphScopeError` (scope misuse, attempted cross-scope illegal ops)
- [ ] Every exception includes:
  - [ ] message
  - [ ] remediation hint
  - [ ] relevant paths (db path, logs path)

✅ Gate: exception tests pass.

---

## 7) Unit tests (completion gates)
**Files**
- [ ] `tests/core/models/...` (use SQLite `:memory:` where possible)

### 7.1 Store tests
- [ ] schema init + migration version checks
- [ ] upsert/get node roundtrip preserves payload
- [ ] upsert/get edge roundtrip preserves payload
- [ ] indexes support query patterns (basic performance sanity)

### 7.2 WorkspaceGraph query tests
- [ ] BFS traversal deterministic
- [ ] limits enforced (nodes/edges)
- [ ] filtering by node kinds / edge kinds works
- [ ] evidence inclusion works

### 7.3 Refresh protocol tests
- [ ] refresh is atomic (rollback on failure)
- [ ] stale items are purged correctly by scope
- [ ] purging does not delete items from other scopes

✅ Gate: all unit tests pass before starting Node provider extraction.

---

## 8) Minimal “agent query surface” (define now to prevent scope creep)
- [ ] Document the exact queries the agent kernel will use first:
  - [ ] `list_components()`
  - [ ] `get_component(id)`
  - [ ] `get_component_dependencies(id, depth=1|2)`
  - [ ] `get_component_dependents(id, depth=1|2)`
  - [ ] `find_by_name(prefix|exact)`
- [ ] Ensure each maps to one `WorkspaceGraph` query method returning a bounded Subgraph.

---

## Deliverables
- [ ] Pydantic node/edge/evidence/subgraph models in `src/suitcode/core/models/`
- [ ] SQLite store with WAL + indexes + migrations
- [ ] `WorkspaceGraph` DB-backed facade (CRUD + bounded queries returning Subgraph)
- [ ] refresh protocol with scope-based purge
- [ ] deterministic serialization and hashing
- [ ] extensive unit tests gating completion
```
