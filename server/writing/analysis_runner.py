import time
from contextlib import aclosing

from server.errors import require
from server.providers.completion import StreamCompletion
from server.workflow.runner import ReviewRunner
from server.writing.analysis_context import parse_analysis


class StyleAnalysisRunner(ReviewRunner):
    prefix = 'style_analysis'
    label = 'style analysis'

    def parse_result(self, output, snapshot):
        return parse_analysis(output, snapshot)

    async def consume(self, job_id, snapshot, state):
        completion, saved = StreamCompletion(), time.monotonic()
        async with aclosing(self.provider.generate(snapshot['profile'], snapshot['instructions'], snapshot['content'])) as stream:
            async for event in stream:
                completion.observe(event)
                state['output'] += event.text
                state['usage'].update(event.usage)
                if event.model:
                    state['usage']['actual_model'] = event.model
                require(len(state['output']) <= 200000, 'The analysis exceeded its response limit. No suggestions were applied.', 502)
                if time.monotonic() - saved > 0.15:
                    self.save(job_id, state)
                    saved = time.monotonic()
        completion.validate(snapshot['profile']['config'])
