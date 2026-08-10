"""Versioned, validated, fail-closed Agent Skill registry."""

import hashlib
import json
import os
import re

from packages.harness.policy import RISK_LEVELS
from packages.harness.registry import TOOL_NAME_PATTERN


SKILL_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)
SEMVER_PATTERN = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)$"
)
MAX_MANIFEST_BYTES = 32 * 1024
MAX_INSTRUCTIONS_BYTES = 16 * 1024
MANIFEST_FIELDS = {
    "schema_version",
    "name",
    "version",
    "description",
    "triggers",
    "required_tools",
    "allowed_risks",
    "max_steps",
    "priority",
    "instructions_file",
    "instructions_sha256",
}


class SkillValidationError(ValueError):
    pass


class SkillDefinition(object):
    def __init__(
        self,
        name,
        version,
        description,
        triggers,
        required_tools,
        allowed_risks,
        max_steps,
        priority,
        instructions,
        instructions_sha256,
    ):
        if not SKILL_NAME_PATTERN.match(str(name)):
            raise SkillValidationError("skill name is invalid")
        if not SEMVER_PATTERN.match(str(version)):
            raise SkillValidationError("skill version is invalid")
        description = str(description).strip()
        if not description or len(description) > 500:
            raise SkillValidationError(
                "skill description is invalid"
            )
        triggers = tuple(
            self._bounded_text_list(
                triggers,
                "trigger",
                maximum_items=32,
                maximum_length=100,
            )
        )
        required_tools = tuple(
            self._bounded_text_list(
                required_tools,
                "required tool",
                maximum_items=16,
                maximum_length=128,
            )
        )
        if not required_tools:
            raise SkillValidationError(
                "skill must require at least one tool"
            )
        if any(
            not TOOL_NAME_PATTERN.match(tool_name)
            for tool_name in required_tools
        ):
            raise SkillValidationError(
                "skill required tool name is invalid"
            )
        allowed_risks = tuple(
            self._bounded_text_list(
                allowed_risks,
                "allowed risk",
                maximum_items=len(RISK_LEVELS),
                maximum_length=2,
            )
        )
        if (
            not allowed_risks
            or any(risk not in RISK_LEVELS for risk in allowed_risks)
        ):
            raise SkillValidationError(
                "skill allowed risks are invalid"
            )
        max_steps = int(max_steps)
        if max_steps < 1 or max_steps > 10:
            raise SkillValidationError(
                "skill max_steps must be between 1 and 10"
            )
        priority = int(priority)
        if priority < 0 or priority > 1000:
            raise SkillValidationError(
                "skill priority must be between 0 and 1000"
            )
        instructions = str(instructions).strip()
        if not instructions or len(instructions) > 12000:
            raise SkillValidationError(
                "skill instructions are invalid"
            )
        digest = hashlib.sha256(
            instructions.encode("utf-8")
        ).hexdigest()
        if digest != str(instructions_sha256):
            raise SkillValidationError(
                "skill instructions integrity mismatch"
            )
        self.name = str(name)
        self.version = str(version)
        self.description = description
        self.triggers = triggers
        self.required_tools = required_tools
        self.allowed_risks = allowed_risks
        self.max_steps = max_steps
        self.priority = priority
        self.instructions = instructions
        self.instructions_sha256 = digest

    def matches(self, user_message):
        message = str(user_message or "").strip().lower()
        return bool(
            message
            and any(trigger.lower() in message for trigger in self.triggers)
        )

    def to_public(self):
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "required_tools": list(self.required_tools),
            "allowed_risks": list(self.allowed_risks),
            "max_steps": self.max_steps,
            "instructions_sha256": self.instructions_sha256,
        }

    def to_context(self):
        payload = self.to_public()
        payload["instructions"] = self.instructions
        return payload

    @staticmethod
    def _bounded_text_list(
        values,
        label,
        maximum_items,
        maximum_length,
    ):
        if not isinstance(values, list):
            raise SkillValidationError(
                "skill {0}s must be a list".format(label)
            )
        if not values or len(values) > maximum_items:
            raise SkillValidationError(
                "skill {0} count is invalid".format(label)
            )
        result = []
        for value in values:
            if not isinstance(value, str):
                raise SkillValidationError(
                    "skill {0} must be text".format(label)
                )
            value = value.strip()
            if not value or len(value) > maximum_length:
                raise SkillValidationError(
                    "skill {0} is invalid".format(label)
                )
            if value in result:
                raise SkillValidationError(
                    "skill {0} is duplicated".format(label)
                )
            result.append(value)
        return result


class SkillRegistry(object):
    def __init__(self, definitions):
        self._skills = {}
        for definition in definitions:
            if not isinstance(definition, SkillDefinition):
                raise TypeError(
                    "skill definition must be SkillDefinition"
                )
            if definition.name in self._skills:
                raise SkillValidationError(
                    "skill is already registered"
                )
            self._skills[definition.name] = definition

    @classmethod
    def load(cls, root):
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            return cls([])
        if os.path.islink(root):
            raise SkillValidationError(
                "skill root must not be a symbolic link"
            )
        names = sorted(os.listdir(root))
        if len(names) > 32:
            raise SkillValidationError(
                "skill directory count exceeds limit"
            )
        definitions = []
        for name in names:
            directory = os.path.join(root, name)
            if not os.path.isdir(directory):
                continue
            if os.path.islink(directory):
                raise SkillValidationError(
                    "skill directory must not be a symbolic link"
                )
            definitions.append(cls._load_one(directory))
        return cls(definitions)

    @staticmethod
    def _load_one(directory):
        manifest_path = os.path.join(directory, "skill.json")
        if (
            os.path.islink(manifest_path)
            or not os.path.isfile(manifest_path)
            or os.path.getsize(manifest_path) > MAX_MANIFEST_BYTES
        ):
            raise SkillValidationError(
                "skill manifest is unavailable"
            )
        try:
            with open(
                manifest_path,
                "r",
                encoding="utf-8",
            ) as manifest_file:
                manifest = json.load(manifest_file)
        except (OSError, ValueError) as error:
            raise SkillValidationError(
                "skill manifest is invalid"
            ) from error
        if not isinstance(manifest, dict):
            raise SkillValidationError(
                "skill manifest must be an object"
            )
        if set(manifest) != MANIFEST_FIELDS:
            raise SkillValidationError(
                "skill manifest fields are invalid"
            )
        if manifest.get("schema_version") != "1.0":
            raise SkillValidationError(
                "skill schema version is unsupported"
            )
        instructions_name = manifest.get("instructions_file")
        if (
            not isinstance(instructions_name, str)
            or not re.match(
                r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$",
                instructions_name,
            )
        ):
            raise SkillValidationError(
                "skill instructions filename is invalid"
            )
        instructions_path = os.path.join(
            directory,
            instructions_name,
        )
        if (
            os.path.islink(instructions_path)
            or not os.path.isfile(instructions_path)
            or os.path.getsize(instructions_path)
            > MAX_INSTRUCTIONS_BYTES
        ):
            raise SkillValidationError(
                "skill instructions are unavailable"
            )
        try:
            with open(
                instructions_path,
                "r",
                encoding="utf-8",
            ) as instructions_file:
                instructions = instructions_file.read()
        except (OSError, UnicodeError) as error:
            raise SkillValidationError(
                "skill instructions are invalid"
            ) from error
        return SkillDefinition(
            name=manifest["name"],
            version=manifest["version"],
            description=manifest["description"],
            triggers=manifest["triggers"],
            required_tools=manifest["required_tools"],
            allowed_risks=manifest["allowed_risks"],
            max_steps=manifest["max_steps"],
            priority=manifest["priority"],
            instructions=instructions,
            instructions_sha256=manifest[
                "instructions_sha256"
            ],
        )

    def select(self, user_message):
        matches = [
            skill
            for skill in self._skills.values()
            if skill.matches(user_message)
        ]
        if not matches:
            return None
        return sorted(
            matches,
            key=lambda skill: (-skill.priority, skill.name),
        )[0]

    def list_public(self):
        return [
            self._skills[name].to_public()
            for name in sorted(self._skills)
        ]

    def get(self, name):
        return self._skills.get(str(name or ""))

    def resolve_pinned(self, payload):
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise SkillValidationError(
                "pinned skill metadata is invalid"
            )
        skill = self.get(payload.get("name"))
        if skill is None:
            raise SkillValidationError(
                "pinned skill is unavailable"
            )
        if (
            payload.get("version") != skill.version
            or payload.get("instructions_sha256")
            != skill.instructions_sha256
        ):
            raise SkillValidationError(
                "pinned skill identity changed"
            )
        return skill

    def validate_tools(self, tool_schemas):
        schemas = {
            schema.get("name"): schema
            for schema in tool_schemas
            if schema.get("name")
        }
        for skill in self._skills.values():
            for tool_name in skill.required_tools:
                schema = schemas.get(tool_name)
                if schema is None:
                    raise SkillValidationError(
                        "skill requires an unknown tool: {0}".format(
                            tool_name
                        )
                    )
                annotations = schema.get("annotations") or {}
                if annotations.get("riskLevel") not in (
                    skill.allowed_risks
                ):
                    raise SkillValidationError(
                        "skill tool risk is not allowed: {0}".format(
                            tool_name
                        )
                    )
