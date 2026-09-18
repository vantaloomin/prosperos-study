from server.database import decode
from server.scenes.actor_runner import combined_result, consume_actors
from server.scenes.output import parse_scene
from server.workflow.runner import ReviewRunner


class SceneRunner(ReviewRunner):
    prefix = "scene"
    label = "scene stage"

    def parse_result(self, output, snapshot):
        if snapshot.get('dialogue_actors'):
            return combined_result(decode(output)['actors'], snapshot)
        return parse_scene(output, snapshot)

    async def consume(self, job_id, snapshot, state):
        if snapshot.get('dialogue_actors'):
            await consume_actors(self, job_id, snapshot, state)
        else:
            await super().consume(job_id, snapshot, state)
