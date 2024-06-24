# utils.py

import os
import pickle
from typing import Dict, List, Tuple

from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()


def get_user_preferences():
    console.print("\n[bold cyan]Code Review Preferences[/bold cyan]")
    console.print(
        "Please specify which areas you'd like the AI to focus on during the review."
    )

    preferences = {}
    areas = {
        "optimization": "Code efficiency and performance improvements",
        "documentation": "Comments, docstrings, and overall code documentation",
        "testing": "Unit tests and test coverage",
        "features": "Potential new features or enhancements",
        "security": "Security vulnerabilities and best practices",
        "code_quality": "Code readability, maintainability, and adherence to PEP 8",
    }

    for area, description in areas.items():
        preferences[area] = Confirm.ask(
            f"Include [bold]{area}[/bold] ({description})?", default=True
        )

    # Additional prompt information
    console.print("\n[bold cyan]Additional Review Instructions[/bold cyan]")
    console.print(
        "You can provide additional instructions or context for the AI reviewer."
    )
    console.print(
        "This could include specific areas of concern, project-specific guidelines, or any other relevant information."
    )

    additional_instructions = Prompt.ask(
        "Enter additional instructions (press Enter if none)"
    )
    preferences["additional_instructions"] = additional_instructions

    return preferences


def save_checkpoint(
    checkpoint_file: str, repo_structure: Dict, previous_results: List[str]
):
    with open(checkpoint_file, "wb") as f:
        pickle.dump((repo_structure, previous_results), f)
    console.print(f"Checkpoint saved to {checkpoint_file}")


def load_checkpoint(checkpoint_file: str) -> Tuple[Dict, List[str]]:
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "rb") as f:
            repo_structure, previous_results = pickle.load(f)
        console.print(f"Checkpoint loaded from {checkpoint_file}")
        return repo_structure, previous_results
    return None, None


def load_aireviews(repo_path: str) -> Tuple[List[str], List[str]]:
    aireviews_path = os.path.join(repo_path, ".aireviews")
    include_patterns = []
    exclude_patterns = []
    if os.path.exists(aireviews_path):
        with open(aireviews_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if line.startswith("!"):
                        include_patterns.append(line[1:])
                    else:
                        exclude_patterns.append(line)
    return include_patterns or ["*"], exclude_patterns


def parse_sub_agent_result(result):
    changes = {"modify": {}, "delete": [], "rename": {}, "mkdir": []}
    current_file = None
    current_content = []
    in_python_code = False

    for line in result.split("\n"):
        if line.startswith("MODIFY:") or line.startswith("CREATE:"):
            if current_file:
                changes["modify"][current_file] = "\n".join(current_content)
            current_file = line.split(":")[1].strip()
            current_content = []
            in_python_code = False
        elif line.strip() == "<PYTHON_CODE>":
            in_python_code = True
        elif line.strip() == "</PYTHON_CODE>":
            in_python_code = False
            changes["modify"][current_file] = "\n".join(current_content)
            current_file = None
            current_content = []
        elif line.startswith("DELETE:"):
            file_to_delete = line.split("DELETE:")[1].strip()
            changes["delete"].append(file_to_delete)
        elif line.startswith("RENAME:"):
            old_path, new_path = line.split("RENAME:")[1].strip().split(" -> ")
            changes["rename"][old_path.strip()] = new_path.strip()
        elif line.startswith("MKDIR:"):
            dir_to_create = line.split("MKDIR:")[1].strip()
            changes["mkdir"].append(dir_to_create)
        elif in_python_code:
            current_content.append(line)

    return {k: v for k, v in changes.items() if v}
