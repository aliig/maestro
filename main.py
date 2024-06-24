import argparse
import os
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
    load_checkpoint,
    parse_sub_agent_result,
    save_checkpoint,
)

console = Console()


def parse_arguments():
    parser = argparse.ArgumentParser(description="AI-Powered Code Review")
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument(
        "--review_depth",
        choices=["minimum", "balanced", "comprehensive"],
        default="balanced",
    )
    parser.add_argument(
        "--config", default="config.yml", help="Path to the configuration file"
    )
    parser.add_argument(
        "--max_file_size",
        type=int,
        default=1024 * 1024,
        help="Maximum file size to review in bytes",
    )
    return parser.parse_args()


def setup_review_environment(
    args: argparse.Namespace,
) -> Tuple[GitHubHandler, PromptManager, AIManager, Dict[str, bool]]:
    config_manager = ConfigManager(args.config)
    try:
        github_handler = GitHubHandler(args.repo_url, config_manager.get_github_token())
    except ValueError as e:
        logger.error(f"Error initializing GitHub handler: {str(e)}")
        raise
    include_patterns, exclude_patterns = load_aireviews(
        os.getcwd()
    )  # Load from current directory
    github_handler.include_patterns = include_patterns
    github_handler.exclude_patterns = exclude_patterns
    github_handler.max_file_size = args.max_file_size

    prompt_manager = PromptManager("prompts.yml")
    ai_manager = AIManager(config_manager, args.review_depth)
    change_types = get_user_preferences()

    return github_handler, prompt_manager, ai_manager, change_types


def perform_code_review(
    github_handler: GitHubHandler,
    prompt_manager: PromptManager,
    ai_manager: AIManager,
    change_types: Dict[str, bool],
    review_depth: str,
) -> Tuple[List[str], List[str]]:
    repo_structure, previous_results = load_checkpoint("review_checkpoint.pkl")
    if repo_structure is None:
        logger.info("Analyzing repository structure...")
        repo_structure = github_handler.get_repo_structure()
        previous_results = []

    original_structure = repo_structure.copy()
    original_readme = github_handler.get_readme_content()
    changes_summary = []

    with Progress() as progress:
        review_task = progress.add_task("[cyan]Performing code review...", total=100)

        while True:
            orchestrator_prompt = prompt_manager.get_orchestrator_prompt(
                repo_structure, review_depth, change_types, "\n".join(previous_results)
            )
            orchestrator_result = ai_manager.call_ai(orchestrator_prompt)

            if "REVIEW_COMPLETE" in orchestrator_result:
                progress.update(review_task, completed=100)
                break

            sub_agent_prompt = prompt_manager.get_sub_agent_prompt(
                orchestrator_result, repo_structure
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
            progress.update(review_task, advance=10)

    return changes_summary, [original_structure, original_readme]


def main():
    args = parse_arguments()
    logger.info(f"Starting AI-Powered Code Review for {args.repo_url}")

    github_handler, prompt_manager, ai_manager, change_types = setup_review_environment(
        args
    )

    try:
        changes_summary, original_data = perform_code_review(
            github_handler, prompt_manager, ai_manager, change_types, args.review_depth
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
        if os.path.exists("review_checkpoint.pkl"):
            os.remove("review_checkpoint.pkl")


if __name__ == "__main__":
    main()
