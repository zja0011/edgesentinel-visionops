"""Fail-closed policy decisions for Agent Harness tool calls."""


RISK_LEVELS = ("L0", "L1", "L2", "L3")


class PolicyRule(object):
    def __init__(
        self,
        risk,
        enabled=True,
        auto_execute=False,
        require_confirmation=False,
    ):
        risk = str(risk)
        if risk not in RISK_LEVELS:
            raise ValueError("unsupported risk level: {0}".format(risk))
        self.risk = risk
        self.enabled = bool(enabled)
        self.auto_execute = bool(auto_execute)
        self.require_confirmation = bool(require_confirmation)

    def to_dict(self):
        return {
            "risk": self.risk,
            "enabled": self.enabled,
            "auto_execute": self.auto_execute,
            "require_confirmation": self.require_confirmation,
        }


class PolicyDecision(object):
    def __init__(self, allowed, reason, rule=None):
        self.allowed = bool(allowed)
        self.reason = str(reason)
        self.rule = rule

    def to_dict(self):
        payload = {
            "allowed": self.allowed,
            "reason": self.reason,
        }
        if self.rule is not None:
            payload.update(self.rule.to_dict())
        else:
            payload.update(
                {
                    "risk": None,
                    "enabled": False,
                    "auto_execute": False,
                    "require_confirmation": False,
                }
            )
        return payload


class PolicyEngine(object):
    """Evaluate exact tool names against an explicit allowlist."""

    def __init__(self, rules):
        self._rules = {}
        for tool_name, rule in dict(rules).items():
            if not isinstance(rule, PolicyRule):
                raise TypeError("policy rule must be PolicyRule")
            self._rules[str(tool_name)] = rule

    def evaluate(self, tool_name, confirmation_granted=False):
        rule = self._rules.get(str(tool_name))
        if rule is None:
            return PolicyDecision(
                False,
                "TOOL_NOT_ALLOWLISTED",
            )
        if not rule.enabled:
            return PolicyDecision(False, "TOOL_DISABLED", rule)
        if rule.require_confirmation and not confirmation_granted:
            return PolicyDecision(
                False,
                "CONFIRMATION_REQUIRED",
                rule,
            )
        if not rule.auto_execute and not confirmation_granted:
            return PolicyDecision(
                False,
                "AUTO_EXECUTE_DISABLED",
                rule,
            )
        return PolicyDecision(True, "ALLOWED", rule)

    def describe(self, tool_name):
        rule = self._rules.get(str(tool_name))
        return rule.to_dict() if rule is not None else None
