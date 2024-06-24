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

    (
        preferences,
        review_depth,
        repo_url,
        max_file_size_mb,
        include_patterns,
        exclude_patterns,
    ) = get_user_preferences()

    github_handler = GitHubHandler(repo_url, config_manager.get_github_token())

    max_file_size = int(max_file_size_mb * 1048576)  # Convert megabytes to bytes

    github_handler.include_patterns = include_patterns
    github_handler.exclude_patterns = exclude_patterns
    github_handler.max_file_size = max_file_size

    prompt_manager = PromptManager("prompts.yml")
    ai_manager = AIManager(config_manager, review_depth)

    return github_handler, prompt_manager, ai_manager, preferences, review_depth


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
    change_types: Dict[str, bool],
    review_depth: str,
) -> Tuple[List[str], List[str]]:
    if repo_structure is None:
        logger.info("Analyzing repository structure...")
        repo_structure = github_handler.get_repo_structure()
        previous_results = []

    original_structure = repo_structure.copy()
    original_readme = github_handler.get_readme_content()
    changes_summary = []
    additional_instructions = change_types.get("additional_instructions", "")

    logger.info("Performing code review...")

    while True:
        orchestrator_prompt = prompt_manager.get_orchestrator_prompt(
            repo_structure,
            review_depth,
            change_types,
            "\n".join(previous_results),
            additional_instructions,
        )
        orchestrator_result = ai_manager.call_ai(orchestrator_prompt)
        logger.info(f"Orchestrator prompt: {orchestrator_prompt}")
        logger.info(f"Orchestrator result: {orchestrator_result}")

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
                parsed_result["reasoning"], repo_structure
            )

            logger.info(
                f"Sub-agent prompt: {sub_agent_prompt[:100]}..."
            )  # Log first 100 chars
            sub_agent_result = ai_manager.call_ai(sub_agent_prompt)
            logger.info(
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

                # Update repo_structure with the latest changes
                repo_structure = github_handler.get_repo_structure()
            else:
                logger.info("No changes proposed in this iteration.")

            save_checkpoint("review_checkpoint.pkl", repo_structure, previous_results)

    return changes_summary, [original_structure, original_readme]


def main():
    logger.info("Starting AI-Powered Code Review")

    github_handler, prompt_manager, ai_manager, preferences, review_depth = (
        setup_review_environment()
    )

    try:
        changes_summary, original_data = perform_code_review(
            github_handler, prompt_manager, ai_manager, preferences, review_depth
        )

        logger.info("Code review complete!")

        new_structure = github_handler.get_repo_structure()
        changes_summary_text = "\n".join(changes_summary)
        pr_description, new_readme_content = (
            ai_manager.analyze_changes_and_update_readme(
                original_data[0], new_structure, original_data[1], changes_summary_text
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
        # if os.path.exists("review_checkpoint.pkl"):
        #     os.remove("review_checkpoint.pkl")


if __name__ == "__main__":
    main()
