# utils.py

import difflib
import os
import pickle
import re
from typing import Dict, List, Tuple

from rich.console import Console
from rich.prompt import Confirm, FloatPrompt, Prompt

console = Console()


def get_user_preferences() -> (
    Tuple[Dict[str, bool], str, str, float, List[str], List[str], Dict, List[str]]
):
    console.print("\n[bold cyan]AI-Powered Code Review[/bold cyan]")

    checkpoint_file = "review_checkpoint.pkl"
    if os.path.exists(checkpoint_file):
        resume = Confirm.ask(
            "A previous review checkpoint was found. Do you want to resume?"
        )
        if resume:
            return load_checkpoint(checkpoint_file)

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

    review_depth = Prompt.ask(
        "Enter review depth",
        choices=["minimum", "balanced", "comprehensive"],
        default="balanced",
    )

    repo_url = Prompt.ask("Enter the GitHub repository URL")

    max_file_size_mb = FloatPrompt.ask(
        "Enter maximum file size to review in megabytes", default=1.0
    )

    include_patterns = Prompt.ask(
        "Enter file patterns to include (comma-separated)",
        default="*.py,*.js,*.html,*.css,*.md,*.yml,*.yaml,*.json",
    ).split(",")

    exclude_patterns = Prompt.ask(
        "Enter file patterns to exclude (comma-separated)",
        default=".git/*,node_modules/*,venv/*,*.pyc",
    ).split(",")

    console.print("\n[bold cyan]Additional Review Instructions[/bold cyan]")
    console.print(
        "You can provide additional instructions or context for the AI reviewer."
    )
    additional_instructions = Prompt.ask(
        "Enter additional instructions (press Enter if none)"
    )
    preferences["additional_instructions"] = additional_instructions

    return (
        preferences,
        review_depth,
        repo_url,
        max_file_size_mb,
        include_patterns,
        exclude_patterns,
        None,  # repo_structure
        [],  # previous_results
    )


def load_checkpoint(
    checkpoint_file: str,
) -> Tuple[Dict[str, bool], str, str, Dict, List[str], Dict]:
    with open(checkpoint_file, "rb") as f:
        data = pickle.load(f)
    console.print(f"Checkpoint loaded from {checkpoint_file}")
    return data


def save_checkpoint(
    checkpoint_file: str,
    preferences: Dict[str, bool],
    review_depth: str,
    repo_url: str,
    repo_structure: Dict,
    previous_results: List[str],
    file_state: Dict,
):
    data = (
        preferences,
        review_depth,
        repo_url,
        repo_structure,
        previous_results,
        file_state,
    )
    with open(checkpoint_file, "wb") as f:
        pickle.dump(data, f)
    console.print(f"Checkpoint saved to {checkpoint_file}")


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


def preprocess_ai_response(content: str) -> str:
    # Normalize line endings to LF
    content = content.replace("\r\n", "\n")

    # Remove trailing whitespace from each line
    content = "\n".join(line.rstrip() for line in content.splitlines())

    # Ensure the file ends with a single newline
    content = content.rstrip() + "\n"

    return content


def clean_diff(old_content: str, new_content: str) -> str:
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    differ = difflib.Differ()
    diff = list(differ.compare(old_lines, new_lines))

    cleaned_diff = []
    for line in diff:
        if line.startswith("  "):  # Unchanged line
            continue
        elif line.startswith("- ") or line.startswith("+ "):
            cleaned_diff.append(line)

    return "\n".join(cleaned_diff)
