from server.database import decode, encode, many
from server.workflow.reviews import job_view


def interpretation_sources(connection, branch):
    documents = []
    for run in many(connection, 'SELECT * FROM background_runs WHERE branch_id=? ORDER BY rowid', (branch['id'],)):
        jobs = many(connection, 'SELECT * FROM background_jobs WHERE run_id=? ORDER BY rowid', (run['id'],))
        attempts = many(connection, 'SELECT a.* FROM background_attempts a JOIN background_jobs j ON j.id=a.job_id WHERE j.run_id=?', (run['id'],))
        text = encode({'origin': decode(run['snapshot']), 'jobs': [job_view(job) for job in jobs], 'attempts': attempts,
                       'authority': 'PRIVATE planning only; selected_state_id identifies a chosen private version, never accepted Story events. Disclose only with full-disclosure permission.'})
        documents.extend({'id': f"private-interpretation:{run['id']}:{index // 6000 + 1}",
                          'title': f"{branch['name']} · PRIVATE background interpretation", 'text': text[index:index + 6000]}
                         for index in range(0, len(text), 6000))
    return documents
