import hashlib
import json
import os
import tempfile
import unittest

from packages.harness.skills import (
    SkillDefinition,
    SkillRegistry,
    SkillValidationError,
)


def make_skill(
    name="vision.investigate_removed_item",
    required_tools=None,
    allowed_risks=None,
):
    instructions = "Call the bounded event query and report only facts."
    return SkillDefinition(
        name=name,
        version="1.2.3",
        description="Investigate a bounded removal event.",
        triggers=["who took", "what was removed"],
        required_tools=required_tools or ["event.query"],
        allowed_risks=allowed_risks or ["L0"],
        max_steps=3,
        priority=100,
        instructions=instructions,
        instructions_sha256=hashlib.sha256(
            instructions.encode("utf-8")
        ).hexdigest(),
    )


class SkillRegistryTests(unittest.TestCase):
    def test_selects_highest_priority_matching_skill(self):
        lower = make_skill(name="vision.lower_priority")
        lower.priority = 10
        higher = make_skill(name="vision.higher_priority")
        higher.priority = 20
        registry = SkillRegistry([lower, higher])

        selected = registry.select("Who took the bottle?")

        self.assertEqual(selected.name, "vision.higher_priority")
        self.assertIsNone(registry.select("current people count"))

    def test_public_metadata_excludes_triggers_and_instructions(self):
        payload = make_skill().to_public()

        self.assertNotIn("triggers", payload)
        self.assertNotIn("instructions", payload)
        self.assertEqual(payload["allowed_risks"], ["L0"])

    def test_context_contains_integrity_pinned_instructions(self):
        skill = make_skill()

        payload = skill.to_context()

        self.assertEqual(payload["instructions"], skill.instructions)
        self.assertEqual(
            payload["instructions_sha256"],
            skill.instructions_sha256,
        )

    def test_rejects_changed_pinned_skill(self):
        skill = make_skill()
        registry = SkillRegistry([skill])
        pinned = skill.to_public()
        pinned["instructions_sha256"] = "0" * 64

        with self.assertRaises(SkillValidationError):
            registry.resolve_pinned(pinned)

    def test_validates_required_tool_and_risk(self):
        registry = SkillRegistry([make_skill()])
        registry.validate_tools(
            [
                {
                    "name": "event.query",
                    "annotations": {"riskLevel": "L0"},
                }
            ]
        )

        with self.assertRaises(SkillValidationError):
            registry.validate_tools([])
        with self.assertRaises(SkillValidationError):
            registry.validate_tools(
                [
                    {
                        "name": "event.query",
                        "annotations": {"riskLevel": "L1"},
                    }
                ]
            )

    def test_loads_strict_manifest_and_checks_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            skill_dir = os.path.join(
                directory,
                "investigate-removed-item",
            )
            os.makedirs(skill_dir)
            instructions = "Use event.query only."
            digest = hashlib.sha256(
                instructions.encode("utf-8")
            ).hexdigest()
            manifest = {
                "schema_version": "1.0",
                "name": "vision.investigate_removed_item",
                "version": "1.0.0",
                "description": "Investigate one bounded removal.",
                "triggers": ["who took"],
                "required_tools": ["event.query"],
                "allowed_risks": ["L0"],
                "max_steps": 2,
                "priority": 100,
                "instructions_file": "SKILL.md",
                "instructions_sha256": digest,
            }
            with open(
                os.path.join(skill_dir, "SKILL.md"),
                "w",
                encoding="utf-8",
            ) as output_file:
                output_file.write(instructions)
            with open(
                os.path.join(skill_dir, "skill.json"),
                "w",
                encoding="utf-8",
            ) as output_file:
                json.dump(manifest, output_file)

            registry = SkillRegistry.load(directory)

            self.assertEqual(
                registry.get(
                    "vision.investigate_removed_item"
                ).instructions,
                instructions,
            )
            manifest["instructions_sha256"] = "f" * 64
            with open(
                os.path.join(skill_dir, "skill.json"),
                "w",
                encoding="utf-8",
            ) as output_file:
                json.dump(manifest, output_file)
            with self.assertRaises(SkillValidationError):
                SkillRegistry.load(directory)

    def test_project_skill_is_valid_and_selectable(self):
        project_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                os.pardir,
                os.pardir,
            )
        )
        registry = SkillRegistry.load(
            os.path.join(project_dir, "skills")
        )

        skill = registry.select("Who took the bottle?")

        self.assertIsNotNone(skill)
        self.assertEqual(
            skill.name,
            "vision.investigate_removed_item",
        )
        self.assertEqual(skill.allowed_risks, ("L0",))


if __name__ == "__main__":
    unittest.main()
