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
INSERT OR IGNORE INTO preferences VALUES ('text_edit_workspace_id', lower(hex(randomblob(16))));
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
CREATE TABLE IF NOT EXISTS side_thread_curation (
    thread_id TEXT PRIMARY KEY REFERENCES side_threads(id), archived INTEGER NOT NULL CHECK(archived IN (0,1)),
    revision INTEGER NOT NULL CHECK(revision >= 1), updated_at TEXT NOT NULL
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
-- Local scheduling authority and destinations are deliberately excluded from portable archives.
CREATE TABLE IF NOT EXISTS backup_settings (
    id INTEGER PRIMARY KEY CHECK(id=1), workspace_id TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 0,
    interval_minutes INTEGER NOT NULL DEFAULT 1440, keep_count INTEGER NOT NULL DEFAULT 10,
    destination TEXT NOT NULL DEFAULT '', include_sidebar INTEGER NOT NULL DEFAULT 0,
    next_run_at TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backup_runs (
    id TEXT PRIMARY KEY, operation_id TEXT UNIQUE, trigger TEXT NOT NULL,
    status TEXT NOT NULL, settings TEXT NOT NULL, directory TEXT NOT NULL,
    started_at TEXT NOT NULL, finished_at TEXT, error TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '', byte_count INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '{}', archive_id TEXT REFERENCES archive_files(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_running_backup ON backup_runs(status) WHERE status='running';
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

CREATE TABLE IF NOT EXISTS branch_cleanup_settings (
    branch_id TEXT PRIMARY KEY REFERENCES branches(id),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), version INTEGER NOT NULL CHECK(version>=1)
);
CREATE TABLE IF NOT EXISTS candidate_cleanups (
    id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id),
    attempt INTEGER NOT NULL, branch_id TEXT NOT NULL REFERENCES branches(id), snapshot TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','done','skipped','error','cancelled','interrupted','stale')),
    output TEXT NOT NULL DEFAULT '', cleaned TEXT NOT NULL DEFAULT '', edits TEXT NOT NULL DEFAULT '[]',
    usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
    selected TEXT NOT NULL DEFAULT 'original' CHECK(selected IN ('original','cleaned')),
    updated_at TEXT NOT NULL, UNIQUE(candidate_id,attempt)
);
CREATE TABLE IF NOT EXISTS branch_cleanup_timing (
    branch_id TEXT PRIMARY KEY REFERENCES branches(id),
    timing TEXT NOT NULL CHECK(timing IN ('before_ready','reading'))
);
CREATE INDEX IF NOT EXISTS candidate_cleanups_branch ON candidate_cleanups(branch_id,status);
CREATE TRIGGER IF NOT EXISTS immutable_cleanup_inputs BEFORE UPDATE OF candidate_id,attempt,branch_id,snapshot ON candidate_cleanups
BEGIN SELECT RAISE(ABORT,'Cleanup inputs are immutable'); END;

-- Model-derived relationship aids have receipts but no accepted-state projection.
CREATE TABLE IF NOT EXISTS relationship_jobs (
    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branches(id), request_key TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('manual','automatic')), snapshot TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('queued','running','done','error','cancelled','interrupted')),
    output TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT 'null', usage TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS relationship_jobs_branch ON relationship_jobs(branch_id);
CREATE INDEX IF NOT EXISTS relationship_jobs_request ON relationship_jobs(request_key);
CREATE TRIGGER IF NOT EXISTS immutable_relationship_inputs BEFORE UPDATE OF branch_id,request_key,mode,snapshot ON relationship_jobs
BEGIN SELECT RAISE(ABORT,'Relationship inputs are immutable'); END;
CREATE TABLE IF NOT EXISTS relationship_attempts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES relationship_jobs(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL, result TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,attempt)
);
CREATE TABLE IF NOT EXISTS side_drafts (
    thread_id TEXT PRIMARY KEY REFERENCES side_threads(id),
    text TEXT NOT NULL CHECK(length(text)<=30000), revision INTEGER NOT NULL CHECK(revision>=1), updated_at TEXT NOT NULL
);

-- Writing preferences have immutable versions but never enter narrative manifests.
CREATE TABLE IF NOT EXISTS writing_assets (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('style','recipe')),
    latest_version_id TEXT REFERENCES writing_versions(id),
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS writing_versions (
    id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES writing_assets(id),
    number INTEGER NOT NULL CHECK(number > 0), name TEXT NOT NULL, description TEXT NOT NULL,
    content TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(asset_id,number)
);
CREATE TRIGGER IF NOT EXISTS immutable_writing_versions BEFORE UPDATE ON writing_versions
BEGIN SELECT RAISE(ABORT,'Writing resource versions are immutable'); END;
CREATE TABLE IF NOT EXISTS writing_pins (
    story_id TEXT PRIMARY KEY REFERENCES stories(id),
    style_version_id TEXT REFERENCES writing_versions(id),
    recipe_version_id TEXT REFERENCES writing_versions(id), updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS writing_extras (
    version_id TEXT PRIMARY KEY REFERENCES writing_versions(id), content TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_writing_extras BEFORE UPDATE ON writing_extras
BEGIN SELECT RAISE(ABORT,'Unsupported writing settings are immutable version metadata'); END;
CREATE TABLE IF NOT EXISTS branch_curation (
    branch_id TEXT PRIMARY KEY REFERENCES branches(id),
    favorite INTEGER NOT NULL CHECK(favorite IN (0,1)), archived INTEGER NOT NULL CHECK(archived IN (0,1)),
    revision INTEGER NOT NULL CHECK(revision >= 0), updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS text_documents (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id), branch_id TEXT NOT NULL REFERENCES branches(id),
    purpose TEXT NOT NULL CHECK(purpose IN ('composer','author-note','scene-goal')), text TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision>=1), updated_at TEXT NOT NULL, UNIQUE(branch_id,purpose)
);
CREATE TABLE IF NOT EXISTS text_edit_proposals (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id), target TEXT NOT NULL, selection TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('add','insert-before','insert-after','replace','update')),
    replacement TEXT NOT NULL, explanation TEXT NOT NULL, origin TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','conflict','applied','dismissed')), revision INTEGER NOT NULL CHECK(revision>=0),
    undo_of TEXT REFERENCES text_edit_receipts(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS text_edit_receipts (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id), proposal_id TEXT NOT NULL UNIQUE REFERENCES text_edit_proposals(id),
    before_target TEXT NOT NULL, after_target TEXT NOT NULL, selection TEXT NOT NULL, action TEXT NOT NULL,
    replacement TEXT NOT NULL, explanation TEXT NOT NULL, origin TEXT NOT NULL, result TEXT NOT NULL,
    undo_of TEXT UNIQUE REFERENCES text_edit_receipts(id), created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS text_edits_story ON text_edit_proposals(story_id,created_at);
CREATE TRIGGER IF NOT EXISTS immutable_text_edit_target BEFORE UPDATE OF story_id,target,selection,action,origin,undo_of ON text_edit_proposals
BEGIN SELECT RAISE(ABORT,'An edit target and its source remain fixed; rebasing creates another proposal'); END;
CREATE TRIGGER IF NOT EXISTS decided_text_edit BEFORE UPDATE ON text_edit_proposals WHEN OLD.status IN ('applied','dismissed')
BEGIN SELECT RAISE(ABORT,'A decided proposal is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_text_edit_receipt BEFORE UPDATE ON text_edit_receipts
BEGIN SELECT RAISE(ABORT,'Applied text changes have immutable receipts'); END;
CREATE TABLE IF NOT EXISTS candidate_text_heads (
    id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id), attempt INTEGER NOT NULL CHECK(attempt>=1),
    revision INTEGER NOT NULL CHECK(revision>=1), text TEXT NOT NULL CHECK(length(text)<=100000),
    receipt_id TEXT NOT NULL REFERENCES text_edit_receipts(id) DEFERRABLE INITIALLY DEFERRED,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(candidate_id,attempt)
);
CREATE TRIGGER IF NOT EXISTS immutable_candidate_text_source BEFORE UPDATE OF candidate_id,attempt ON candidate_text_heads
BEGIN SELECT RAISE(ABORT,'An author revision remains bound to its original candidate attempt'); END;
CREATE TABLE IF NOT EXISTS branch_comparisons (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id),
    left_branch_id TEXT NOT NULL REFERENCES branches(id), right_branch_id TEXT NOT NULL REFERENCES branches(id),
    left_head_id TEXT REFERENCES nodes(id), right_head_id TEXT REFERENCES nodes(id),
    left_revision INTEGER NOT NULL CHECK(left_revision >= 0), right_revision INTEGER NOT NULL CHECK(right_revision >= 0),
    labels TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS branch_comparisons_story ON branch_comparisons(story_id);
CREATE TRIGGER IF NOT EXISTS immutable_branch_comparisons BEFORE UPDATE ON branch_comparisons
BEGIN SELECT RAISE(ABORT,'Comparison sources are immutable'); END;
CREATE TABLE IF NOT EXISTS side_contexts (
    id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES side_threads(id),
    story_id TEXT NOT NULL REFERENCES stories(id), snapshot TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_side_contexts BEFORE UPDATE ON side_contexts
BEGIN SELECT RAISE(ABORT,'Companion source selections are immutable'); END;
CREATE TABLE IF NOT EXISTS side_context_heads (
    thread_id TEXT PRIMARY KEY REFERENCES side_threads(id), context_id TEXT REFERENCES side_contexts(id),
    revision INTEGER NOT NULL CHECK(revision>=1)
);

CREATE TABLE IF NOT EXISTS companion_edit_origins (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id),
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_companion_edit_origins BEFORE UPDATE ON companion_edit_origins
BEGIN SELECT RAISE(ABORT, 'Companion edit origins are immutable'); END;
CREATE TABLE IF NOT EXISTS side_edit_results (
    reply_id TEXT PRIMARY KEY REFERENCES side_replies(id),
    origin_id TEXT NOT NULL UNIQUE REFERENCES companion_edit_origins(id),
    proposal_id TEXT NOT NULL UNIQUE REFERENCES text_edit_proposals(id),
    error TEXT NOT NULL DEFAULT ''
);
CREATE TRIGGER IF NOT EXISTS immutable_side_edit_results BEFORE UPDATE ON side_edit_results
BEGIN SELECT RAISE(ABORT, 'Companion edit results are immutable'); END;
CREATE TABLE IF NOT EXISTS style_analysis_jobs (
    id TEXT PRIMARY KEY, source_version_id TEXT REFERENCES writing_versions(id), draft_id TEXT NOT NULL, step TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'null', usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS style_analysis_attempts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES style_analysis_jobs(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL, result TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,attempt)
);
CREATE INDEX IF NOT EXISTS style_analysis_source ON style_analysis_jobs(source_version_id,draft_id);
CREATE TRIGGER IF NOT EXISTS immutable_style_analysis BEFORE UPDATE OF source_version_id,draft_id,step,snapshot ON style_analysis_jobs
BEGIN SELECT RAISE(ABORT,'Style analysis inputs are immutable'); END;
CREATE TABLE IF NOT EXISTS recipe_runs (
    id TEXT PRIMARY KEY, story_id TEXT NOT NULL REFERENCES stories(id), branch_id TEXT NOT NULL REFERENCES branches(id),
    snapshot TEXT NOT NULL, bindings TEXT NOT NULL, target TEXT NOT NULL, chance TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipe_jobs (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES recipe_runs(id), stage INTEGER NOT NULL CHECK(stage>=0 AND stage<3),
    step TEXT NOT NULL, snapshot TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'null', usage TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, UNIQUE(run_id,stage,step)
);
CREATE TABLE IF NOT EXISTS recipe_attempts (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES recipe_jobs(id), attempt INTEGER NOT NULL,
    status TEXT NOT NULL, output TEXT NOT NULL, result TEXT NOT NULL, usage TEXT NOT NULL,
    error TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,attempt)
);
CREATE TABLE IF NOT EXISTS recipe_results (
    run_id TEXT PRIMARY KEY REFERENCES recipe_runs(id), job_id TEXT NOT NULL REFERENCES recipe_jobs(id),
    proposal_id TEXT NOT NULL UNIQUE REFERENCES text_edit_proposals(id)
);
CREATE INDEX IF NOT EXISTS recipe_runs_branch ON recipe_runs(branch_id,created_at);
CREATE TRIGGER IF NOT EXISTS immutable_recipe_run BEFORE UPDATE OF story_id,branch_id,snapshot,bindings,target,chance ON recipe_runs
BEGIN SELECT RAISE(ABORT,'Recipe inputs and chance results are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_recipe_job BEFORE UPDATE OF run_id,stage,step,snapshot ON recipe_jobs
BEGIN SELECT RAISE(ABORT,'Recipe step inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_recipe_result BEFORE UPDATE ON recipe_results
BEGIN SELECT RAISE(ABORT,'Recipe results retain their original proposal'); END;

CREATE TABLE IF NOT EXISTS migration_sources (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, source_base64 TEXT NOT NULL,
    source_sha256 TEXT NOT NULL, content_sha256 TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('transcript')), conversion TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS migration_source_hash ON migration_sources(source_sha256);
CREATE INDEX IF NOT EXISTS migration_content_hash ON migration_sources(content_sha256);
CREATE TRIGGER IF NOT EXISTS immutable_migration_sources BEFORE UPDATE ON migration_sources
BEGIN SELECT RAISE(ABORT,'Migration sources and conversion reports are immutable'); END;
CREATE TABLE IF NOT EXISTS story_imports (
    id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES migration_sources(id),
    story_id TEXT NOT NULL UNIQUE REFERENCES stories(id), branch_id TEXT NOT NULL REFERENCES branches(id),
    receipt TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_story_imports BEFORE UPDATE ON story_imports
BEGIN SELECT RAISE(ABORT,'Story import mappings and selected variants are immutable'); END;

CREATE TABLE IF NOT EXISTS preset_imports (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, source_base64 TEXT NOT NULL,
    source_sha256 TEXT NOT NULL, content_sha256 TEXT NOT NULL, conversion TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS preset_source_hash ON preset_imports(source_sha256);
CREATE INDEX IF NOT EXISTS preset_content_hash ON preset_imports(content_sha256);
CREATE TRIGGER IF NOT EXISTS immutable_preset_imports BEFORE UPDATE ON preset_imports
BEGIN SELECT RAISE(ABORT,'Preset source bytes and conversion reports are immutable'); END;
CREATE TABLE IF NOT EXISTS preset_origins (
    version_id TEXT PRIMARY KEY REFERENCES writing_versions(id), import_id TEXT NOT NULL REFERENCES preset_imports(id),
    profile_id TEXT REFERENCES profiles(id), profile_version_id TEXT REFERENCES profile_versions(id),
    base_profile_id TEXT REFERENCES profiles(id), base_profile_version_id TEXT REFERENCES profile_versions(id),
    receipt TEXT NOT NULL, configuration TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_preset_origins BEFORE UPDATE ON preset_origins
BEGIN SELECT RAISE(ABORT,'Reviewed preset mappings and saved configuration proposals are immutable'); END;

-- Installation-local migration work queues. Published source provenance belongs
-- to the versioned import tables above; unfinished queues never activate on restore.
CREATE TABLE IF NOT EXISTS migration_batches (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS migration_batch_items (
    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES migration_batches(id), position INTEGER NOT NULL,
    filename TEXT NOT NULL, source_base64 TEXT NOT NULL, source_sha256 TEXT NOT NULL,
    candidates TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '', import_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('choose','preparing','preparation-error','review','publishing','complete','omitted','rejected')),
    revision INTEGER NOT NULL DEFAULT 0, publication TEXT NOT NULL DEFAULT 'null', result TEXT NOT NULL DEFAULT 'null',
    error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, UNIQUE(batch_id,position)
);
CREATE INDEX IF NOT EXISTS migration_batch_item_status ON migration_batch_items(batch_id,status);
CREATE INDEX IF NOT EXISTS migration_batch_item_source ON migration_batch_items(source_sha256);
CREATE TRIGGER IF NOT EXISTS immutable_batch_source BEFORE UPDATE OF batch_id,position,filename,source_base64,source_sha256,candidates ON migration_batch_items
BEGIN SELECT RAISE(ABORT,'Batch original sources and detection reports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_completed_batch_item BEFORE UPDATE ON migration_batch_items WHEN OLD.status='complete'
BEGIN SELECT RAISE(ABORT,'Completed migration results are immutable'); END;
CREATE TRIGGER IF NOT EXISTS frozen_batch_publication BEFORE UPDATE OF publication,kind,import_id ON migration_batch_items
WHEN OLD.status='publishing' AND NEW.status!='review'
BEGIN SELECT RAISE(ABORT,'An interrupted publication keeps its frozen choices'); END;

CREATE TABLE IF NOT EXISTS inspiration_decks (
    id TEXT PRIMARY KEY, latest_version_id TEXT REFERENCES inspiration_versions(id),
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)), revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inspiration_versions (
    id TEXT PRIMARY KEY, deck_id TEXT NOT NULL REFERENCES inspiration_decks(id), number INTEGER NOT NULL CHECK(number>0),
    name TEXT NOT NULL, description TEXT NOT NULL, content TEXT NOT NULL, unsupported TEXT NOT NULL,
    note TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(deck_id,number)
);
CREATE TRIGGER IF NOT EXISTS immutable_inspiration_versions BEFORE UPDATE ON inspiration_versions
BEGIN SELECT RAISE(ABORT,'Published deck versions are immutable'); END;
CREATE TABLE IF NOT EXISTS inspiration_draws (
    id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES inspiration_versions(id),
    branch_id TEXT REFERENCES branches(id), head_id TEXT REFERENCES nodes(id),
    selection TEXT NOT NULL, ticket INTEGER NOT NULL CHECK(ticket>=0), card_id TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS inspiration_draw_branch ON inspiration_draws(branch_id,created_at);
CREATE TRIGGER IF NOT EXISTS immutable_inspiration_draws BEFORE UPDATE ON inspiration_draws
BEGIN SELECT RAISE(ABORT,'Recorded inspiration draws are immutable'); END;
CREATE TABLE IF NOT EXISTS inspiration_pack_sources (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, source_base64 TEXT NOT NULL, source_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_inspiration_pack_sources BEFORE UPDATE ON inspiration_pack_sources
BEGIN SELECT RAISE(ABORT,'Original inspiration packs are immutable'); END;
CREATE TABLE IF NOT EXISTS inspiration_pack_origins (
    version_id TEXT PRIMARY KEY REFERENCES inspiration_versions(id), import_id TEXT NOT NULL REFERENCES inspiration_pack_sources(id),
    item_key TEXT NOT NULL, content_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS inspiration_pack_content ON inspiration_pack_origins(content_sha256);
CREATE TRIGGER IF NOT EXISTS immutable_inspiration_pack_origins BEFORE UPDATE ON inspiration_pack_origins
BEGIN SELECT RAISE(ABORT,'Inspiration pack origins are immutable'); END;
