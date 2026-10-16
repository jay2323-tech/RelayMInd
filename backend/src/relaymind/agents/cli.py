"""Operator CLI: uses real providers and a platform bridge supplied by Claude.

Example: python -m relaymind.agents.cli --session UUID --platform module:factory
The factory receives client, context, project_id and returns PlatformBridge.
No model/tool output controls module loading or user/tenant identity.
"""
import argparse
import importlib
import json
import os
from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.connection import create_client
from relaymind.agents.engine import CoordinationEngine
from relaymind.agents.providers import provider_from_env


def main():
    parser=argparse.ArgumentParser(description='RelayMind real-provider agent runner')
    parser.add_argument('--session',required=True)
    parser.add_argument('--project',default='launch-01')
    parser.add_argument('--platform',required=True,help='Trusted installed module:factory')
    parser.add_argument('--request',default='Continue launch preparation. What changed?')
    parser.add_argument('--procedure',default='launch-review')
    parser.add_argument('--run-id')
    parser.add_argument('--resume',help='Explicitly resume a saved, possibly paused run ID')
    parser.add_argument('--pause-after-plan',action='store_true',help='Persist and pause at the handoff checkpoint')
    args=parser.parse_args()
    load_dotenv()
    context=TrustedContext(tenant_id=os.getenv('DEMO_TENANT_ID','demo-a'),
                           user_id=os.getenv('DEMO_USER_ID','developer-a'))
    module,name=args.platform.split(':',1)
    client=create_client()
    bridge=getattr(importlib.import_module(module),name)(client,context,args.project)
    engine=CoordinationEngine(client,context,args.project,args.session,provider_from_env(),bridge)
    if args.resume:
        result=engine.resume_run(args.resume)
    elif args.pause_after_plan:
        result=engine.plan_run(args.request,run_id=args.run_id,procedure_id=args.procedure)
        if result.status=='awaiting_review':
            result=engine.pause_run(result.id)
    else:
        result=engine.run(args.request,run_id=args.run_id,procedure_id=args.procedure)
    print(result.model_dump_json(indent=2))
    return 0 if result.status in {'completed','paused'} else 2


if __name__=='__main__':
    raise SystemExit(main())
