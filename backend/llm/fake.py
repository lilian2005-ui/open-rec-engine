"""A fake LLM for tests: no network, no API key, the same result every time."""
import json


class FakeLLM:
    """Use it in place of call_llm:  generate(prompt, Model, call=FakeLLM(...))

    Give it the answers to return, in order. Each answer can be:
    - a dict       -> returned as JSON text (a normal answer)
    - a str        -> returned as is (use it for broken JSON)
    - an Exception -> raised (use it for timeouts and API errors)
    """

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []          # every prompt it received, so tests can check them

    def __call__(self, prompt, response_schema):
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError("FakeLLM was called more times than it has answers")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer)

    @property
    def calls(self):
        return len(self.prompts)