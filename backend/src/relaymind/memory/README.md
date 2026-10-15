# Shared memory area

A owns conversations.py, episodes.py, procedures.py, and handoffs.py.
B owns decisions.py and semantic.py. Agree on shared contracts before adding them.
All operations receive trusted context and enforce session/project authorization.
Use UTC epoch milliseconds, stable operation IDs, sourced records, and parameterized
queries. A proposed memory is not automatically an approved fact.
