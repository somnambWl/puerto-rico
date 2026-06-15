"""Training package: self-play config, reward modes, opponent pool, evaluation.

Currently exposes :mod:`reward_config` (reward-mode selection + dense-shaping
schedule). Kept dependent only on :mod:`puerto_rico.engine` so the env can import
it without an import cycle (env -> training -> engine, never env -> training ->
env).
"""
