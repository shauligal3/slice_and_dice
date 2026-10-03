"""slice_and_dice: an interactive shell for slicing and dicing performance data.

The shell lets an analyst *narrow* a large data set of network request logs
into ever smaller *scopes* (``in geo = US``, ``in network = LTE`` ...), then
*dice* the current scope by one or more dimensions (``group_by size
breakpoints 10000 50000``) to compare the performance of accelerated traffic
against a bypassed control group.

All heavy lifting (SQL generation, aggregation, statistics) happens on a
remote analytics server; this package is the client side: a command grammar
with tab completion, a scope stack, an HTTP API client, and tabular report
rendering.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
