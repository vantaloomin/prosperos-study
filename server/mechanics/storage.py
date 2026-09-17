from server.database import decode, one
from server.errors import require
from server.mechanics.config import read_settings
from server.mechanics.state import node_state


def opportunity_view(row):
    return {**row, "snapshot": decode(row["snapshot"])}


def pending_opportunity(connection, branch, story=None):
    row = connection.execute("SELECT * FROM mechanic_opportunities WHERE branch_id=? AND head_key=?",
                             (branch["id"], branch["head_id"] or "")).fetchone()
    if row is None:
        return None
    result = opportunity_view(dict(row))
    story = story or one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
    explicit = result["snapshot"]["manual"] or result["snapshot"].get("reroll_of")
    if not read_settings(story).enabled and not explicit:
        return None
    return result


def mechanics_brief(connection, branch):
    story = one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
    settings = read_settings(story)
    pending = pending_opportunity(connection, branch, story)
    assessment = connection.execute('SELECT id,generation_id FROM assessment_runs WHERE branch_id=? AND head_key=?',
                                     (branch['id'], branch['head_id'] or '')).fetchone()
    return {"enabled": settings.enabled, "state": node_state(connection, branch["head_id"]),
            'automatic_assessment': settings.enabled and settings.automatic_assessment,
            'assessment': dict(assessment) if assessment else None,
            "pending": {"id": pending["id"], "label": pending["snapshot"]["beat"]["label"],
                        "manual": pending["snapshot"]["manual"],
                        "stale": opportunity_stale(pending, branch, story)} if pending else None}


def opportunity_stale(opportunity, branch, story):
    snapshot = opportunity["snapshot"]
    return snapshot["branch"]["revision"] != branch["revision"] or snapshot["story_revision"] != story["revision"]


def accepted_state(connection, branch, opportunity_id, allow_fork=False):
    if opportunity_id is None:
        return None
    opportunity = opportunity_view(one(connection, "SELECT * FROM mechanic_opportunities WHERE id=?", (opportunity_id,)))
    require(opportunity["story_id"] == branch["story_id"], "The prepared beat belongs to another story.", 409)
    require(opportunity["head_key"] == (branch["head_id"] or ""), "This prepared beat belongs to a different point.", 409)
    if not allow_fork:
        require(opportunity["branch_id"] == branch["id"], "This beat belongs to another branch.", 409)
        story = one(connection, "SELECT * FROM stories WHERE id=?", (branch["story_id"],))
        require(not opportunity_stale(opportunity, branch, story), "This prepared beat is stale. Reroll on a new branch.", 409)
    return {**opportunity["snapshot"]["after"], "last_opportunity_id": opportunity_id}
