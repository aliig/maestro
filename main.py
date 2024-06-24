import os
import re
from typing import Dict, List, Tuple

from rich.console import Console
from rich.progress import Progress

from ai_manager import AIManager
from config_manager import ConfigManager
from github_handler import GitHubHandler
from logger import logger
from prompt_manager import PromptManager
from utils import (
    get_user_preferences,
    load_aireviews,
    parse_sub_agent_result,
    save_checkpoint,
)

console = Console()


def setup_review_environment():
    config_manager = ConfigManager("config.yml")
    config_manager.validate_config()

    (
        preferences,
        review_depth,
        repo_url,
        max_file_size_mb,
        include_patterns,
        exclude_patterns,
        repo_structure,
        previous_results,
    ) = get_user_preferences()

    github_handler = GitHubHandler(repo_url, config_manager.get_github_token())

    max_file_size = int(max_file_size_mb * 1048576)  # Convert megabytes to bytes

    github_handler.include_patterns = include_patterns
    github_handler.exclude_patterns = exclude_patterns
    github_handler.max_file_size = max_file_size

    prompt_manager = PromptManager("prompts.yml")
    ai_manager = AIManager(config_manager, review_depth)

    if repo_structure is None:
        logger.info("Analyzing repository structure...")
        repo_structure = github_handler.get_repo_structure()

    return (
        github_handler,
        prompt_manager,
        ai_manager,
        preferences,
        review_depth,
        repo_structure,
        previous_results,
    )


def parse_orchestrator_response(response):
    pattern = r"STATUS: (.+)\nNEXT_ACTION: (.+)\nTARGET: (.+)\nREASONING: (.+)"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        return {
            "status": match.group(1).strip(),
            "next_action": match.group(2).strip(),
            "target": match.group(3).strip(),
            "reasoning": match.group(4).strip(),
        }
    return None


def perform_code_review(
    github_handler: GitHubHandler,
    prompt_manager: PromptManager,
    ai_manager: AIManager,
    preferences: Dict[str, bool],
    review_depth: str,
    repo_structure: Dict,
    previous_results: List[str],
) -> Tuple[List[str], List[str]]:

    file_state = {
        path: "original" for path in repo_structure.keys()
    }  # Initialize file state
    original_structure = repo_structure.copy()
    original_readme = github_handler.get_readme_content()
    changes_summary = []
    additional_instructions = preferences.get("additional_instructions", "")

    logger.info("Performing code review...")

    with Progress() as progress:
        review_task = progress.add_task("[cyan]Reviewing code...", total=None)

        while True:

            orchestrator_prompt = prompt_manager.get_orchestrator_prompt(
                repo_structure,
                review_depth,
                preferences,
                "\n".join(previous_results),
                additional_instructions,
                file_state,  # Pass the current file state to the prompt
            )
            orchestrator_result = ai_manager.call_ai(orchestrator_prompt)
            logger.debug(f"Orchestrator prompt: {orchestrator_prompt}")
            logger.debug(f"Orchestrator result: {orchestrator_result}")

            parsed_result = parse_orchestrator_response(orchestrator_result)

            if not parsed_result:
                logger.warning(
                    "Failed to parse orchestrator response. Continuing with next iteration."
                )
                continue

            if parsed_result["status"] == "COMPLETE":
                logger.info(
                    "Review process complete. Reason: " + parsed_result["reasoning"]
                )
                break

            if parsed_result["next_action"] == "REVIEW":
                sub_agent_prompt = prompt_manager.get_sub_agent_prompt(
                    parsed_result["reasoning"],
                    repo_structure,
                    file_state,  # Pass file state here too
                )

                logger.debug(
                    f"Sub-agent prompt: {sub_agent_prompt[:100]}..."
                )  # Log first 100 chars
                sub_agent_result = ai_manager.call_ai(sub_agent_prompt)
                logger.debug(
                    f"Sub-agent result: {sub_agent_result[:100]}..."
                )  # Log first 100 chars

                changes = parse_sub_agent_result(sub_agent_result)
                logger.info(f"Parsed changes: {changes}")

                if changes:
                    github_handler.commit_changes(changes)
                    changes_summary.append(
                        f"- Iteration {len(previous_results) + 1}: {sum(len(details) for details in changes.values())} operation(s) performed"
                    )
                    previous_results.append(sub_agent_result)

                    # Update file_state with the latest changes
                    for operation, details in changes.items():
                        if operation == "modify":
                            for path in details:
                                file_state[path] = "modified"
                        elif operation == "rename":
                            for old_path, new_path in details.items():
                                file_state[new_path] = file_state.pop(
                                    old_path, "renamed"
                                )
                        elif operation == "delete":
                            for path in details:
                                file_state.pop(path, None)
                        elif operation == "mkdir":
                            for path in details:
                                file_state[path] = "new_directory"

                    # Update repo_structure with the latest changes
                    repo_structure = github_handler.get_repo_structure()

                    # Add any new files to file_state
                    for path in repo_structure:
                        if path not in file_state:
                            file_state[path] = "new"
                else:
                    logger.info("No changes proposed in this iteration.")

            save_checkpoint(
                "review_checkpoint.pkl",
                preferences,
                review_depth,
                github_handler.repo.html_url,
                repo_structure,
                previous_results,
                file_state,
            )

            progress.update(review_task, advance=1)

    return changes_summary, [original_structure, original_readme]


def main():
    logger.info("Starting AI-Powered Code Review")

    (
        github_handler,
        prompt_manager,
        ai_manager,
        preferences,
        review_depth,
        repo_structure,
        previous_results,
    ) = setup_review_environment()

    try:
        changes_summary, original_data = perform_code_review(
            github_handler,
            prompt_manager,
            ai_manager,
            preferences,
            review_depth,
            repo_structure,
            previous_results,
        )

        logger.info("Code review complete!")

        new_structure = github_handler.get_repo_structure()
        changes_summary_text = "\n".join(changes_summary)
        pr_description, new_readme_content = (
            ai_manager.analyze_changes_and_update_readme(
                original_data[0],
                new_structure,
                original_data[1],
                changes_summary_text,
                prompt_manager,
            )
        )

        github_handler.update_readme(new_readme_content)

        pr_url = github_handler.create_pull_request(
            "AI Code Review Changes", pr_description
        )
        logger.info(f"Pull request created: {pr_url}")

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        raise
    finally:
        github_handler.cleanup()
        logger.info("Temporary files cleaned up. Review process finished.")
        if os.path.exists("review_checkpoint.pkl"):
            os.remove("review_checkpoint.pkl")


if __name__ == "__main__":
    main()
