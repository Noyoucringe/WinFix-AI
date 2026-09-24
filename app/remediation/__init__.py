"""Whitelisted remediation actions.

Every function here is a *predefined* action with structured results and
logging. None of them accept free-form commands. They are registered as
``read_only=False`` tools and therefore require explicit user approval before
the remediation engine will run them.
"""
