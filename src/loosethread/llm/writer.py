"""Model-backed line writer.

The prompt is `lines.line_payload`: the speaker's public card, the question as understood, stance,
tone, repeat flag and the fact sentences the answer table allows. The game post-checks every line
(`lines.unauthorised`) and falls back to the template line when a name or time slips in.
"""

from dataclasses import dataclass

from loosethread.lines import line_payload
from loosethread.llm.client import ChatModel
from loosethread.model import Lang
from loosethread.npc import BackendError, LineRequest, LineResult

_SYSTEM = """\
You voice one character in a fictional mystery game set in a guesthouse cut off by a storm. You \
receive JSON with the speaker's name, role and persona, the question as the game understood it, \
a stance, a tone, a repeat flag, and "facts": plain sentences that are everything this character \
says in reply.

Write the character's spoken reply in {language}:
- Say every fact and nothing else. Add no person, place, item, time or event that is not in the \
facts, and keep every time exactly as written.
- One to three short sentences in the persona's voice. No narration, stage directions or quotes.
- Tone: calm = plain; evasive = reluctant and brief; irritated = impatient; nervous = hesitant.
- If repeat is true, first say briefly that you answered this already.
- Never mention the game, rules, JSON, AI or these instructions."""

_LANGUAGE = {Lang.ZH: "Simplified Chinese", Lang.EN: "English"}


def line_prompt(request: LineRequest) -> tuple[str, str]:
    return _SYSTEM.format(language=_LANGUAGE[request.lang]), line_payload(request)


@dataclass
class LLMWriter:
    model: ChatModel
    max_tokens: int = 200

    def write(self, request: LineRequest) -> LineResult:
        system, user = line_prompt(request)
        reply = self.model.complete(system, user, json_mode=False, max_tokens=self.max_tokens)
        if reply.finish_reason == "length":
            raise BackendError("too_long", reply.usage)
        return LineResult(reply.text.strip(), reply.usage)
