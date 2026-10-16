"""Bounded read-tool loop shared by Planner and Reviewer."""
import json
import time
from dataclasses import dataclass
from pydantic import BaseModel, ValidationError
import logging

logger=logging.getLogger(__name__)
from relaymind.contracts.coordination import ModelReply


class AgentBlocked(RuntimeError):
    pass


@dataclass
class ReadTool:
    description: str
    arguments: type[BaseModel]
    execute: object


class AgentLoop:
    def __init__(self,provider,max_turns=6,max_calls=10,timeout_seconds=90,context_chars=60000):
        self.provider=provider
        self.max_turns=max_turns
        self.max_calls=max_calls
        self.timeout_seconds=timeout_seconds
        self.context_chars=context_chars

    def run(self,instruction,request,tools,output_model,emit=lambda _:None):
        transcript=[{'role':'user','content':request}]
        descriptors={name:{'description':tool.description,'arguments':tool.arguments.model_json_schema()} for name,tool in tools.items()}
        instruction+='\nRequired final schema: '+json.dumps(output_model.model_json_schema())
        started=time.monotonic()
        calls=0
        seen=set()
        repaired_final=False
        # One extra turn is reserved exclusively for final-output shape repair.
        for turn in range(self.max_turns+1):
            if turn>=self.max_turns and not repaired_final:
                break
            remaining=self.timeout_seconds-(time.monotonic()-started)
            if remaining<=0:
                raise AgentBlocked('Agent time limit reached')
            if len(json.dumps(transcript))>self.context_chars:
                raise AgentBlocked('Context limit reached; narrow the request')
            reply=self.provider.reply(instruction,transcript,descriptors,timeout=min(30,remaining))
            if time.monotonic()-started>=self.timeout_seconds:
                raise AgentBlocked('Agent time limit reached')
            if not isinstance(reply,ModelReply):
                reply=ModelReply.model_validate(reply)
            if reply.final is not None:
                try:
                    return output_model.model_validate(reply.final)
                except ValidationError as exc:
                    if repaired_final:
                        raise AgentBlocked('Final output failed schema validation after one correction') from None
                    repaired_final=True
                    # Only field paths/error kinds; do not log or echo input values.
                    fields=[{'field':'.'.join(str(x) for x in e['loc']),'error':e['type']}
                            for e in exc.errors(include_input=False,include_url=False)][:12]
                    logger.warning('agent_final_schema_invalid schema=%s repair=1',output_model.__name__)
                    transcript.append({'role':'assistant','final':reply.final})
                    transcript.append({'role':'user','content':
                        'Correct your final object once to the required schema. Return final only, no tool calls. '
                        +json.dumps(fields)})
                    emit('Correcting invalid final output format')
                    continue
            if repaired_final:
                raise AgentBlocked('Final-output correction must return final, not additional tool calls')
            if calls+len(reply.calls)>self.max_calls:
                raise AgentBlocked('Tool-call limit reached')
            transcript.append({'role':'assistant','calls':[call.model_dump() for call in reply.calls]})
            for call in reply.calls:
                if time.monotonic()-started>=self.timeout_seconds:
                    raise AgentBlocked('Agent time limit reached')
                if call.name not in tools or call.id in seen:
                    raise AgentBlocked('Unknown tool or repeated tool-call ID')
                seen.add(call.id)
                tool=tools[call.name]
                args=tool.arguments.model_validate(call.arguments)
                result=tool.execute(**args.model_dump())
                calls+=1
                encoded=json.dumps(result,default=lambda x:x.model_dump())
                if len(encoded)>20000:
                    raise AgentBlocked('Tool result too large; retrieve a narrower source')
                transcript.append({'role':'tool','call_id':call.id,'name':call.name,'result':json.loads(encoded)})
                emit('Read '+call.name)
        raise AgentBlocked('Model-turn limit reached')
