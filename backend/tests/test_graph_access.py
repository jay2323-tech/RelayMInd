from unittest.mock import Mock
import pytest
from relaymind.contracts.models import TrustedContext
from relaymind.graph.access import AccessDenied, authorized_graph, require_session


def test_graph_names_are_server_owned_and_isolated():
    client = Mock()
    for tenant, user, graph in [("demo-a", "developer-a", "relaymind_demo_a"),
                                 ("demo-b", "developer-b", "relaymind_demo_b")]:
        authorized_graph(client, TrustedContext(tenant_id=tenant, user_id=user), "launch-01")
        client.select_graph.assert_called_with(graph)


@pytest.mark.parametrize("tenant,user,project", [
    ("demo-a", "developer-b", "launch-01"),
    ("arbitrary-graph", "developer-a", "launch-01"),
    ("demo-a", "developer-a", "other-project"),
])
def test_denied_access_never_selects_a_graph(tenant, user, project):
    client = Mock()
    with pytest.raises(AccessDenied):
        authorized_graph(client, TrustedContext(tenant_id=tenant, user_id=user), project)
    client.select_graph.assert_not_called()


def test_session_access_requires_owner_and_project():
    graph = Mock()
    graph.ro_query.return_value.result_set = []
    context = TrustedContext(tenant_id="demo-a", user_id="developer-a")
    with pytest.raises(AccessDenied):
        require_session(graph, context, "launch-01", "session-01")
    assert graph.ro_query.call_args.kwargs["params"]["owner_id"] == "developer-a"
