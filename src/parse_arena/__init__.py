"""parse-arena: a neutral benchmark harness for document parsers.

The package evaluates document parsers against manifest-defined datasets,
scores them with transparent metrics (CER/WER, simplified TEDS, reading-order
Kendall tau, Japanese vertical-order accuracy, receipt field recall), and
renders a static leaderboard site plus a parser-router config.
"""

__version__ = "0.1.0"
