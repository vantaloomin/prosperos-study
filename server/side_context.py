"""Frozen read-only source archive. No story mutation operations are exposed to the collaborator."""
import math

from server.background.sources import interpretation_sources
from server.background.storage import state_id
from server.branches import path_nodes
from server.continuity import continuity_view
from server.database import decode, encode, many, one
from server.errors import DomainError, require
from server.library_formats.import_context import import_reference_sources
from server.manifests import manifest_view
from server.profiles import resolve_profile
from server.prompts import PROMPT_LABELS, prompt_snapshot
from server.stories import check_revision
from server.workflow.reviews import job_view


def document_parts(source_id, title, text):
    # Every byte of text stays available; chunking adds retrieval boundaries, not summaries.
    return [{"id": f"{source_id}:{offset // 6000 + 1}", "title": title, "text": text[offset:offset + 6000]}
            for offset in range(0, max(len(text), 1), 6000)]


def branch_sources(connection, branch):
    docs = []
    prefix = f"{branch['name']} · revision {branch['revision']}"
    nodes = path_nodes(connection, branch["head_id"])
    for index, node in enumerate(nodes):
        docs.extend(document_parts(f"{branch['id']}:message:{node['id']}", f"{prefix} · message {index + 1} · {node['role']}", node["text"]))
    for asset in manifest_view(connection, branch["manifest_id"]):
        version = asset["version"]
        docs.extend(document_parts(f"asset:{version['id']}", f"{prefix} · {version['name']} v{version['number']}",
                                   encode(asset)))
        docs.extend(import_reference_sources(connection, version['id']))
    docs.extend(review_sources(connection, branch))
    docs.extend(scene_sources(connection, branch))
    docs.extend(assessment_sources(connection, branch))
    docs.extend(interpretation_sources(connection, branch))
    docs.extend(document_parts(f"continuity:{branch['id']}", f"{prefix} · accepted continuity and provenance",
                               encode(continuity_view(connection, branch['head_id']))))
    docs.extend(mechanic_sources(connection, branch, nodes))
    background = state_id(connection, branch['id'])
    if background:
        row = one(connection, 'SELECT snapshot FROM background_states WHERE id=?', (background,))
        docs.extend(document_parts(f'background:{background}', f'{prefix} · PRIVATE background; disclose only with full-disclosure permission', row['snapshot']))
    return docs


def assessment_sources(connection, branch):
    docs = []
    runs = many(connection, 'SELECT * FROM assessment_runs WHERE branch_id=? ORDER BY rowid', (branch['id'],))
    for run in runs:
        snapshot = decode(run['snapshot'])
        for profile in snapshot['writer_profiles']:
            profile.pop('credential_ref', None)
        jobs = many(connection, 'SELECT * FROM assessment_jobs WHERE run_id=? ORDER BY rowid', (run['id'],))
        attempts = many(connection, 'SELECT a.* FROM assessment_attempts a JOIN assessment_jobs j ON j.id=a.job_id WHERE j.run_id=?', (run['id'],))
        content = {**run, 'snapshot': snapshot, 'jobs': [job_view(job) for job in jobs], 'attempts': attempts,
                   'authority': 'Assessment only; no accepted Story events. Writer drafts require explicit acceptance.'}
        docs.extend(document_parts(f"assessment:{run['id']}", f"{branch['name']} · beat assessment", encode(content)))
    return docs


def scene_sources(connection, branch):
    docs = []
    runs = many(connection, "SELECT * FROM scene_runs WHERE branch_id=? ORDER BY created_at", (branch["id"],))
    for run in runs:
        jobs = many(connection, "SELECT * FROM scene_jobs WHERE run_id=? ORDER BY rowid", (run["id"],))
        decisions = many(connection, "SELECT * FROM scene_decisions WHERE run_id=? ORDER BY revision", (run["id"],))
        attempts = many(connection, "SELECT a.* FROM scene_attempts a JOIN scene_jobs j ON a.job_id=j.id WHERE j.run_id=?", (run["id"],))
        content = {"origin": decode(run["snapshot"]), "state": decode(run["state"]), "jobs": [job_view(job) for job in jobs],
                   "decisions": decisions, "attempts": attempts,
                   "authority": "Proposals stay separate; only the explicit accepted receipt identifies committed Story prose and selected continuity."}
        docs.extend(document_parts(f"scene:{run['id']}", f"{branch['name']} · scene plan: {run['title']}", encode(content)))
    return docs


def review_sources(connection, branch):
    docs = []
    runs = many(connection, "SELECT * FROM review_runs WHERE branch_id=? ORDER BY created_at", (branch["id"],))
    for run in runs:
        jobs = many(connection, "SELECT * FROM review_jobs WHERE run_id=? ORDER BY rowid", (run["id"],))
        for job in jobs:
            attempts = many(connection, "SELECT * FROM review_attempts WHERE job_id=? ORDER BY attempt", (job["id"],))
            content = {"origin": decode(run["snapshot"]), "selections": decode(run["selections"]),
                       "report": job_view(job), "attempts": attempts, "authority": "Review only; never accepted canon."}
            title = f"{branch['name']} · {job['step']} · {job['status']} · {run['created_at']}"
            docs.extend(document_parts(f"review:{job['id']}", title, encode(content)))
    return docs


def mechanic_sources(connection, branch, nodes):
    docs, opportunity_ids = [], set()
    for node in nodes:
        state = connection.execute("SELECT state FROM node_mechanics WHERE node_id=?", (node["id"],)).fetchone()
        if state is None:
            continue
        docs.extend(document_parts(f"mechanics:{node['id']}", f"{branch['name']} · accepted mechanics after {node['id']}", state["state"]))
        opportunity_ids.add(decode(state["state"]).get("last_opportunity_id"))
    opportunity_ids.update(row["id"] for row in many(connection, "SELECT id FROM mechanic_opportunities WHERE branch_id=?", (branch["id"],)))
    for opportunity_id in sorted(opportunity_ids - {None}):
        row = one(connection, "SELECT * FROM mechanic_opportunities WHERE id=?", (opportunity_id,))
        title = f"{branch['name']} · recorded opportunity {opportunity_id} · proposed until accepted"
        docs.extend(document_parts(f"opportunity:{opportunity_id}", title, row["snapshot"]))
    return docs


def side_snapshot(connection, thread, body):
    branch = one(connection, "SELECT * FROM branches WHERE id=?", (body.branch_id,))
    require(branch["story_id"] == thread["story_id"], "Choose a branch from this story.")
    check_revision(branch, body.expected_revision)
    story = one(connection, "SELECT * FROM stories WHERE id=?", (thread["story_id"],))
    sources = document_parts(f"story:{story['id']}", "Story settings and premise", encode(story))
    for branch_id in dict.fromkeys([body.branch_id, *body.compare_branch_ids]):
        selected = one(connection, "SELECT * FROM branches WHERE id=?", (branch_id,))
        require(selected["story_id"] == thread["story_id"], "Comparison paths must belong to this story.")
        sources.extend(branch_sources(connection, selected))
    sources.extend(workspace_sources(connection, body.branch_id, story))
    history = many(connection, "SELECT t.question,t.snapshot,r.output FROM side_turns t JOIN side_replies r "
                   "ON t.selected_reply_id=r.id WHERE t.thread_id=? AND r.status='done' ORDER BY t.created_at", (thread["id"],))
    conversation = [{"question": row["question"], "answer": row["output"],
                     "branch": decode(row["snapshot"])["branch"]["name"]} for row in history]
    profiles = [resolve_profile(connection, story, "collaborator", item) for item in (body.profile_ids or [None])]
    require(len(body.profile_ids) == len(set(body.profile_ids)), "Choose each profile once.")
    return {"branch": branch, "story_revision": story["revision"], "question": body.question,
            "prompt": prompt_snapshot(connection, "collaborator", story), "conversation": conversation,
            "sources": list({doc["id"]: doc for doc in sources}.values()), "disclosure": body.disclosure,
            "max_reads": body.max_reads}, profiles


def workspace_sources(connection, branch_id, story):
    prompts = [prompt_snapshot(connection, key, story) for key in PROMPT_LABELS]
    profiles = many(connection, "SELECT v.id,v.name,v.config,v.number FROM profiles p JOIN profile_versions v "
                    "ON p.latest_version_id=v.id")
    runs = many(connection, "SELECT id,snapshot,created_at FROM generations WHERE branch_id=? ORDER BY created_at", (branch_id,))
    documents = document_parts("configuration", "Effective Story prompts and model settings (no credentials)",
                               encode({"prompts": prompts, "profiles": profiles}))
    for run in runs:
        documents.extend(document_parts(f"run:{run['id']}", f"Writer request · {run['created_at']}", run["snapshot"]))
    return documents


def estimated_tokens(prompt, content):
    return math.ceil(len((prompt + content).encode("utf-8")) / 3)


def assemble_context(snapshot, profile, source_ids):
    documents = snapshot["sources"]
    content = encode({"question": snapshot["question"], "disclosure": snapshot["disclosure"],
                      "conversation": snapshot["conversation"],
                      "source_index": [{"id": item["id"], "title": item["title"]} for item in documents],
                      "sources": [item for item in documents if item["id"] in source_ids]})
    config = profile["config"]
    capacity = config["context_tokens"] - config["max_output_tokens"]
    require(estimated_tokens(snapshot["prompt"]["template"], content) <= capacity,
            "This source selection exceeds the model's context allowance. Use a larger-context profile or a new side conversation. No source was silently truncated.", 409)
    return content


def initial_sources(snapshot, profile):
    ids = [item["id"] for item in snapshot["sources"]]
    try:
        assemble_context(snapshot, profile, ids)
        return ids
    except DomainError:
        assemble_context(snapshot, profile, [])  # Require the complete index to fit before starting a paid request.
        return []
