"""Non-destructive database connectivity check; no application data is written."""
from dotenv import load_dotenv
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client


def main():
    load_dotenv()
    client = create_client()
    for tenant, user in [("demo-a", "developer-a"), ("demo-b", "developer-b")]:
        graph = authorized_graph(client, TrustedContext(tenant_id=tenant, user_id=user), "launch-01")
        assert graph.ro_query("RETURN 1").result_set == [[1]]
    print("PASS: authenticated FalkorDB queries succeeded for both fixed demo graph mappings.")
    print("No messages, sessions, or agent functionality tested.")


if __name__ == "__main__":
    main()
