CREATE TABLE IF NOT EXISTS manuscripts (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL UNIQUE REFERENCES stories(id),
    revision INTEGER NOT NULL DEFAULT 0, document TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prepared_publications (
    id TEXT PRIMARY KEY, manuscript_id TEXT NOT NULL REFERENCES manuscripts(id), document TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_publications BEFORE UPDATE ON prepared_publications
BEGIN SELECT RAISE(ABORT, 'Prepared publications are immutable'); END;
CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, premise TEXT NOT NULL,
    settings TEXT NOT NULL, manifest_id TEXT, revision INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('character','lorebook','persona')),
    latest_version_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asset_versions (
    id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id),
    number INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL,
    note TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(asset_id,number)
);
CREATE TABLE IF NOT EXISTS asset_sources (
    version_id TEXT PRIMARY KEY REFERENCES asset_versions(id),
    format TEXT NOT NULL, markdown TEXT NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS library_imports (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, source_base64 TEXT NOT NULL,
    source_sha256 TEXT NOT NULL, conversion TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asset_import_origins (
    version_id TEXT NOT NULL REFERENCES asset_versions(id),
    import_id TEXT NOT NULL REFERENCES library_imports(id), part TEXT NOT NULL,
    PRIMARY KEY (version_id,import_id,part)
);
CREATE TRIGGER IF NOT EXISTS immutable_library_imports BEFORE UPDATE ON library_imports
BEGIN SELECT RAISE(ABORT, 'Imported sources are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_import_origins BEFORE UPDATE ON asset_import_origins
BEGIN SELECT RAISE(ABORT, 'Import provenance is immutable'); END;
CREATE TABLE IF NOT EXISTS manifests (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id),
    attachments TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS branches (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id),
    name TEXT NOT NULL, head_id TEXT, manifest_id TEXT NOT NULL REFERENCES manifests(id),
    forked_from TEXT REFERENCES branches(id), fork_node_id TEXT,
    revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id),
    parent_id TEXT REFERENCES nodes(id), role TEXT NOT NULL,
    text TEXT NOT NULL, manifest_id TEXT NOT NULL REFERENCES manifests(id),
    metadata TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS nodes_parent ON nodes(parent_id);
CREATE INDEX IF NOT EXISTS branches_story ON branches(story_id);
CREATE TABLE IF NOT EXISTS path_revisions (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id),
    source_branch_id TEXT NOT NULL REFERENCES branches(id),
    source_node_id TEXT NOT NULL REFERENCES nodes(id),
    replacement_node_id TEXT NOT NULL REFERENCES nodes(id),
    action TEXT NOT NULL CHECK(action IN ('remove','restore')), created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_path_revisions BEFORE UPDATE ON path_revisions
BEGIN SELECT RAISE(ABORT, 'Path revisions are immutable'); END;
CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, fingerprint TEXT NOT NULL,
    result TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS adoptions (
    id TEXT PRIMARY KEY, operation_id TEXT NOT NULL, story_id TEXT NOT NULL REFERENCES stories(id),
    old_manifest_id TEXT NOT NULL REFERENCES manifests(id),
    new_manifest_id TEXT NOT NULL REFERENCES manifests(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY, latest_version_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_versions (
    id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id),
    number INTEGER NOT NULL, name TEXT NOT NULL, config TEXT NOT NULL,
    credential_ref TEXT, created_at TEXT NOT NULL, UNIQUE(profile_id,number)
);
CREATE TRIGGER IF NOT EXISTS immutable_profile_versions BEFORE UPDATE ON profile_versions
BEGIN SELECT RAISE(ABORT,'Profile snapshots are immutable'); END;
CREATE TABLE IF NOT EXISTS prompt_versions (
    id TEXT PRIMARY KEY, key TEXT NOT NULL, number INTEGER NOT NULL,
    template TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(key,number)
);
CREATE TABLE IF NOT EXISTS prompt_heads (key TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES prompt_versions(id));
CREATE TABLE IF NOT EXISTS generations (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id),
    snapshot TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY, generation_id TEXT NOT NULL REFERENCES generations(id),
    profile TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
    usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', attempt INTEGER NOT NULL DEFAULT 0,
    accepted_branch_id TEXT REFERENCES branches(id), accepted_node_id TEXT REFERENCES nodes(id),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS generation_attempts (
    id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id),
    attempt INTEGER NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidate_activity (
    candidate_id TEXT NOT NULL REFERENCES candidates(id), attempt INTEGER NOT NULL CHECK(attempt >= 1),
    started_at TEXT NOT NULL, first_text_at TEXT, last_event_at TEXT, finished_at TEXT,
    error_kind TEXT NOT NULL DEFAULT '', PRIMARY KEY(candidate_id, attempt)
);
CREATE TRIGGER IF NOT EXISTS immutable_prompts BEFORE UPDATE ON prompt_versions
BEGIN SELECT RAISE(ABORT,'Prompt history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_generations BEFORE UPDATE ON generations
BEGIN SELECT RAISE(ABORT,'Generation input is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_nodes BEFORE UPDATE ON nodes
BEGIN SELECT RAISE(ABORT,'Message history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_asset_versions BEFORE UPDATE ON asset_versions
BEGIN SELECT RAISE(ABORT,'Published versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_manifests BEFORE UPDATE ON manifests
BEGIN SELECT RAISE(ABORT,'Attachment snapshots are immutable'); END;
CREATE TABLE IF NOT EXISTS side_threads (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id), name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS side_turns (
    id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES side_threads(id), question TEXT NOT NULL,
    snapshot TEXT NOT NULL, selected_reply_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS side_replies (
    id TEXT PRIMARY KEY, turn_id TEXT NOT NULL REFERENCES side_turns(id), profile TEXT NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
    usage TEXT NOT NULL DEFAULT '[]', coverage TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_side_inputs BEFORE UPDATE OF snapshot,question,thread_id ON side_turns
BEGIN SELECT RAISE(ABORT,'Collaborator inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_side_profile BEFORE UPDATE OF profile,turn_id ON side_replies
BEGIN SELECT RAISE(ABORT,'Collaborator model snapshots are immutable'); END;
CREATE TABLE IF NOT EXISTS roll_tables (id TEXT PRIMARY KEY, version_id TEXT);
CREATE TABLE IF NOT EXISTS roll_table_versions (
    id TEXT PRIMARY KEY, table_id TEXT NOT NULL REFERENCES roll_tables(id), number INTEGER NOT NULL,
    definition TEXT NOT NULL, hash TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(table_id,number)
);
CREATE TABLE IF NOT EXISTS mechanic_opportunities (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id),
    branch_id TEXT NOT NULL REFERENCES branches(id), head_key TEXT NOT NULL,
    snapshot TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(branch_id,head_key)
);
CREATE TABLE IF NOT EXISTS background_states (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id),
    branch_id TEXT NOT NULL REFERENCES branches(id),
    head_id TEXT REFERENCES nodes(id),
    previous_id TEXT REFERENCES background_states(id),
    snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS background_story ON background_states(story_id);
CREATE INDEX IF NOT EXISTS background_branch ON background_states(branch_id);
CREATE TABLE IF NOT EXISTS branch_background (
    branch_id TEXT PRIMARY KEY REFERENCES branches(id),
    background_state_id TEXT NOT NULL REFERENCES background_states(id)
);
CREATE TABLE IF NOT EXISTS node_background (
    node_id TEXT PRIMARY KEY REFERENCES nodes(id),
    background_state_id TEXT NOT NULL REFERENCES background_states(id)
);
CREATE TABLE IF NOT EXISTS node_mechanics (
    node_id TEXT PRIMARY KEY REFERENCES nodes(id), state TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_roll_tables BEFORE UPDATE ON roll_table_versions
BEGIN SELECT RAISE(ABORT,'Table versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_opportunities BEFORE UPDATE ON mechanic_opportunities
BEGIN SELECT RAISE(ABORT,'Recorded rolls are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_node_mechanics BEFORE UPDATE ON node_mechanics
BEGIN SELECT RAISE(ABORT,'Accepted mechanical state is immutable'); END;
CREATE TABLE IF NOT EXISTS review_runs (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id),
    snapshot TEXT NOT NULL, selections TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_jobs (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES review_runs(id), step TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'null', usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_attempts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES review_jobs(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL, result TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,attempt)
);
CREATE INDEX IF NOT EXISTS review_runs_branch ON review_runs(branch_id);
CREATE INDEX IF NOT EXISTS review_jobs_run ON review_jobs(run_id);
CREATE TRIGGER IF NOT EXISTS immutable_review_inputs BEFORE UPDATE OF snapshot,branch_id ON review_runs
BEGIN SELECT RAISE(ABORT,'Review run inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_review_job BEFORE UPDATE OF snapshot,run_id,step ON review_jobs
BEGIN SELECT RAISE(ABORT,'Review job inputs are immutable'); END;
CREATE TABLE IF NOT EXISTS archive_files (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, filename TEXT NOT NULL,
    sha256 TEXT NOT NULL, summary TEXT NOT NULL, byte_count INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS archive_restores (
    id TEXT PRIMARY KEY, archive_id TEXT NOT NULL REFERENCES archive_files(id),
    identity_map TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS archive_origins (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL,
    receipt_id TEXT NOT NULL REFERENCES archive_restores(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prepared_transcripts (
    id TEXT PRIMARY KEY, checksum TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
    content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scene_runs (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id), title TEXT NOT NULL,
    snapshot TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scene_jobs (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES scene_runs(id), step TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'null', usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scene_attempts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES scene_jobs(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL, result TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,attempt)
);
CREATE TABLE IF NOT EXISTS scene_decisions (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES scene_runs(id), revision INTEGER NOT NULL,
    kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id,revision)
);
CREATE INDEX IF NOT EXISTS scene_runs_branch ON scene_runs(branch_id);
CREATE INDEX IF NOT EXISTS scene_jobs_run ON scene_jobs(run_id);
CREATE INDEX IF NOT EXISTS scene_decisions_run ON scene_decisions(run_id);
CREATE TRIGGER IF NOT EXISTS immutable_scene_inputs BEFORE UPDATE OF snapshot,branch_id,title ON scene_runs
BEGIN SELECT RAISE(ABORT,'Scene inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_scene_job BEFORE UPDATE OF snapshot,run_id,step ON scene_jobs
BEGIN SELECT RAISE(ABORT,'Scene job inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_scene_decision BEFORE UPDATE ON scene_decisions
BEGIN SELECT RAISE(ABORT,'Director decisions are immutable'); END;
CREATE TABLE IF NOT EXISTS continuity_commits (
    id TEXT PRIMARY KEY, origin_id TEXT NOT NULL,
    node_id TEXT NOT NULL UNIQUE REFERENCES nodes(id),
    scene_id TEXT NOT NULL UNIQUE REFERENCES scene_runs(id),
    proposal_job_id TEXT NOT NULL REFERENCES scene_jobs(id),
    branch_id TEXT NOT NULL REFERENCES branches(id),
    summary TEXT NOT NULL, changes TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS continuity_node ON continuity_commits(node_id);
CREATE TRIGGER IF NOT EXISTS immutable_continuity_commit BEFORE UPDATE ON continuity_commits
BEGIN SELECT RAISE(ABORT,'Accepted continuity is immutable'); END;
CREATE TABLE IF NOT EXISTS assessment_runs (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id), head_key TEXT NOT NULL,
    snapshot TEXT NOT NULL, selected_job_id TEXT, opportunity_id TEXT REFERENCES mechanic_opportunities(id),
    generation_id TEXT REFERENCES generations(id), stopped INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, UNIQUE(branch_id,head_key)
);
CREATE TABLE IF NOT EXISTS assessment_jobs (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES assessment_runs(id), step TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'null', usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assessment_attempts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES assessment_jobs(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL, result TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,attempt)
);
CREATE INDEX IF NOT EXISTS assessment_jobs_run ON assessment_jobs(run_id);
CREATE TRIGGER IF NOT EXISTS immutable_assessment_inputs BEFORE UPDATE OF snapshot,branch_id,head_key ON assessment_runs
BEGIN SELECT RAISE(ABORT,'Beat assessment inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_assessment_job BEFORE UPDATE OF snapshot,run_id,step ON assessment_jobs
BEGIN SELECT RAISE(ABORT,'Beat assessment job inputs are immutable'); END;
CREATE TABLE IF NOT EXISTS background_runs (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id),
    snapshot TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS background_jobs (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES background_runs(id), step TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'null', usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
    selected_state_id TEXT REFERENCES background_states(id)
);
CREATE TABLE IF NOT EXISTS background_attempts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES background_jobs(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL, result TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,attempt)
);
CREATE INDEX IF NOT EXISTS background_runs_branch ON background_runs(branch_id);
CREATE INDEX IF NOT EXISTS background_jobs_run ON background_jobs(run_id);
CREATE TRIGGER IF NOT EXISTS immutable_background_run BEFORE UPDATE ON background_runs
BEGIN SELECT RAISE(ABORT,'Private interpretation inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_background_job BEFORE UPDATE OF snapshot,run_id,step ON background_jobs
BEGIN SELECT RAISE(ABORT,'Private interpretation job inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_background_state BEFORE UPDATE ON background_states
BEGIN SELECT RAISE(ABORT,'Private setup versions are immutable'); END;
CREATE TABLE IF NOT EXISTS authoring_runs (
    id TEXT PRIMARY KEY, asset_id TEXT REFERENCES assets(id), source_version_id TEXT REFERENCES asset_versions(id),
    snapshot TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS authoring_jobs (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES authoring_runs(id), step TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'null', usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS authoring_attempts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES authoring_jobs(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL, result TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,attempt)
);
CREATE INDEX IF NOT EXISTS authoring_jobs_run ON authoring_jobs(run_id);
CREATE INDEX IF NOT EXISTS authoring_runs_asset ON authoring_runs(asset_id);
CREATE TRIGGER IF NOT EXISTS immutable_authoring_run BEFORE UPDATE ON authoring_runs
BEGIN SELECT RAISE(ABORT,'Library assistance inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_authoring_job BEFORE UPDATE OF snapshot,run_id,step ON authoring_jobs
BEGIN SELECT RAISE(ABORT,'Library assistance job inputs are immutable'); END;
CREATE TABLE IF NOT EXISTS library_media (
  sha256 TEXT PRIMARY KEY,
  source_base64 TEXT NOT NULL,
  display_base64 TEXT NOT NULL,
  thumbnail_base64 TEXT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS summary_runs (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id), request_key TEXT NOT NULL,
    snapshot TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(branch_id,request_key)
);
CREATE TABLE IF NOT EXISTS summary_jobs (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES summary_runs(id), step TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'null', usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summary_attempts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES summary_jobs(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL, result TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,attempt)
);
CREATE TABLE IF NOT EXISTS summary_versions (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES summary_runs(id),
    job_id TEXT NOT NULL REFERENCES summary_jobs(id), parent_id TEXT REFERENCES summary_versions(id),
    branch_id TEXT NOT NULL REFERENCES branches(id), node_id TEXT NOT NULL REFERENCES nodes(id),
    result TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    origin TEXT NOT NULL CHECK(origin IN ('reviewed','generated')), created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS summary_runs_branch ON summary_runs(branch_id);
CREATE INDEX IF NOT EXISTS summary_jobs_run ON summary_jobs(run_id);
CREATE INDEX IF NOT EXISTS summary_versions_boundary ON summary_versions(node_id);
CREATE TRIGGER IF NOT EXISTS immutable_summary_run BEFORE UPDATE ON summary_runs
BEGIN SELECT RAISE(ABORT,'Summary inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_summary_job BEFORE UPDATE OF snapshot,run_id,step ON summary_jobs
BEGIN SELECT RAISE(ABORT,'Summary job inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_summary_version BEFORE UPDATE ON summary_versions
BEGIN SELECT RAISE(ABORT,'Memory versions are immutable'); END;

CREATE TABLE IF NOT EXISTS summary_pending (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id),
    node_id TEXT NOT NULL REFERENCES nodes(id), created_at TEXT NOT NULL, UNIQUE(branch_id,node_id)
);
CREATE TABLE IF NOT EXISTS summary_wakeups (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL UNIQUE REFERENCES branches(id),
    revision INTEGER NOT NULL, allowance INTEGER NOT NULL CHECK(allowance BETWEEN 0 AND 4),
    status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summary_batches (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id),
    kind TEXT NOT NULL CHECK(kind IN ('automatic','backfill')), snapshot TEXT NOT NULL,
    status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summary_batch_runs (
    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES summary_batches(id),
    run_id TEXT NOT NULL UNIQUE REFERENCES summary_runs(id), ordinal INTEGER NOT NULL,
    UNIQUE(batch_id,ordinal)
);
CREATE INDEX IF NOT EXISTS summary_batch_queue ON summary_batches(status,created_at);
CREATE INDEX IF NOT EXISTS summary_wakeups_status ON summary_wakeups(status,updated_at);
CREATE TRIGGER IF NOT EXISTS immutable_summary_batch BEFORE UPDATE OF branch_id,kind,snapshot ON summary_batches
BEGIN SELECT RAISE(ABORT,'Summary batch inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_summary_batch_run BEFORE UPDATE ON summary_batch_runs
BEGIN SELECT RAISE(ABORT,'Summary batch links are immutable'); END;

CREATE TABLE IF NOT EXISTS memory_control_versions (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id),
    branch_id TEXT NOT NULL REFERENCES branches(id), node_id TEXT NOT NULL REFERENCES nodes(id),
    parent_id TEXT REFERENCES memory_control_versions(id), payload TEXT NOT NULL,
    created_at TEXT NOT NULL, origin TEXT NOT NULL CHECK(origin='author')
);
CREATE TABLE IF NOT EXISTS branch_memory_controls (
    branch_id TEXT PRIMARY KEY REFERENCES branches(id), version_id TEXT NOT NULL REFERENCES memory_control_versions(id)
);
CREATE INDEX IF NOT EXISTS memory_controls_story ON memory_control_versions(story_id);
CREATE TRIGGER IF NOT EXISTS immutable_memory_controls BEFORE UPDATE ON memory_control_versions
BEGIN SELECT RAISE(ABORT,'Author memory decisions are immutable'); END;

CREATE TABLE IF NOT EXISTS archive_identities (
    record_id TEXT NOT NULL, source_id TEXT NOT NULL, record_kind TEXT NOT NULL,
    source_story_id TEXT NOT NULL,
    PRIMARY KEY (record_id, source_id, source_story_id)
);
CREATE INDEX IF NOT EXISTS archive_identities_source ON archive_identities(source_id);

-- Author corrections share the continuity projection; they do not insert manuscript nodes.
CREATE TABLE IF NOT EXISTS continuity_edits (
    id TEXT PRIMARY KEY, origin_id TEXT NOT NULL, branch_id TEXT NOT NULL REFERENCES branches(id),
    node_id TEXT NOT NULL REFERENCES nodes(id), parent_id TEXT REFERENCES continuity_edits(id),
    changes TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS branch_continuity_edits (
    branch_id TEXT PRIMARY KEY REFERENCES branches(id), version_id TEXT NOT NULL REFERENCES continuity_edits(id)
);
CREATE TRIGGER IF NOT EXISTS continuity_edits_immutable BEFORE UPDATE ON continuity_edits
BEGIN SELECT RAISE(ABORT,'Continuity edits are immutable'); END;
