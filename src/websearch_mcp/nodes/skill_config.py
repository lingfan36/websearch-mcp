"""Skill configuration loader — applies YAML config to nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()


class SkillConfig:
    """Configuration for a node skill, loaded from YAML."""

    def __init__(self, name: str, config: dict[str, Any]):
        self.name = name
        self.system_prompt = config.get("system_prompt", "")
        self.capabilities = config.get("capabilities", [])
        self.llm_config = config.get("llm", {})
        self.options = config.get("options", {})

    @classmethod
    def from_yaml(cls, name: str, yaml_path: Path) -> SkillConfig:
        """Load skill config from a YAML file."""
        if not yaml_path.exists():
            logger.warning("skill_yaml_not_found", name=name, path=str(yaml_path))
            return cls(name, {})

        with yaml_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        return cls(name, config)

    @classmethod
    def from_directory(cls, name: str, skills_dir: Path) -> SkillConfig:
        """Load skill from a directory containing skill.yaml or {name}_skill.yaml."""
        # Try {name}_skill.yaml first
        path = skills_dir / f"{name}_skill.yaml"
        if not path.exists():
            path = skills_dir / "skill.yaml"

        return cls.from_yaml(name, path)

    def apply_to_llm_config(self, default_config: dict[str, Any]) -> dict[str, Any]:
        """Merge skill LLM config with defaults."""
        merged = dict(default_config)
        merged.update(self.llm_config)
        return merged


def load_all_skills(skills_dir: Path) -> dict[str, SkillConfig]:
    """Load all skill configs from a directory."""
    configs = {}
    if not skills_dir.exists():
        logger.warning("skills_dir_not_found", path=str(skills_dir))
        return configs

    for yaml_file in skills_dir.glob("*_skill.yaml"):
        name = yaml_file.stem.replace("_skill", "")
        configs[name] = SkillConfig.from_yaml(name, yaml_file)

    # Also check for generic skill.yaml
    generic = skills_dir / "skill.yaml"
    if generic.exists():
        configs["default"] = SkillConfig.from_yaml("default", generic)

    return configs