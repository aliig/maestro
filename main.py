import argparse
import os
import pickle

from rich.console import Console
from rich.progress import Progress
from rich.prompt import Confirm, Prompt

from ai_manager import AIManager
from config_manager import ConfigManager
from github_handler import GitHubHandler
from logger import logger
from prompt_manager import PromptManager

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
    return parser.parse_args()


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

    return preferences


def save_checkpoint(checkpoint_file, repo_structure, previous_results):
    with open(checkpoint_file, "wb") as f:
        pickle.dump((repo_structure, previous_results), f)
    logger.info(f"Checkpoint saved to {checkpoint_file}")


def load_checkpoint(checkpoint_file):
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "rb") as f:
            repo_structure, previous_results = pickle.load(f)
        logger.info(f"Checkpoint loaded from {checkpoint_file}")
        return repo_structure, previous_results
    return None, None


def main():
    args = parse_arguments()

    logger.info(f"Starting AI-Powered Code Review for {args.repo_url}")

    config_manager = ConfigManager(args.config)
    github_handler = GitHubHandler(args.repo_url, config_manager.get_github_token())
    prompt_manager = PromptManager("prompts.yml")
    ai_manager = AIManager(config_manager)

    change_types = get_user_preferences()

    checkpoint_file = "review_checkpoint.pkl"
    repo_structure, previous_results = load_checkpoint(checkpoint_file)

    if repo_structure is None:
        logger.info("Analyzing repository structure...")
        repo_structure = github_handler.get_repo_structure()
        previous_results = []

    review_complete = False

    try:
        with Progress() as progress:
            review_task = progress.add_task(
                "[cyan]Performing code review...", total=100
            )

            while not review_complete:
                orchestrator_prompt = prompt_manager.get_orchestrator_prompt(
                    repo_structure,
                    args.review_depth,
                    change_types,
                    "\n".join(previous_results),
                )
                orchestrator_result = ai_manager.call_ai(orchestrator_prompt)

                if "REVIEW_COMPLETE" in orchestrator_result:
                    review_complete = True
                    progress.update(review_task, completed=100)
                    break

                sub_agent_prompt = prompt_manager.get_sub_agent_prompt(
                    orchestrator_result, repo_structure
                )
                sub_agent_result = ai_manager.call_ai(sub_agent_prompt)

                changes = parse_sub_agent_result(sub_agent_result)

                github_handler.commit_changes(changes)
                previous_results.append(sub_agent_result)

                save_checkpoint(checkpoint_file, repo_structure, previous_results)

                progress.update(review_task, advance=10)

        logger.info("Code review complete!")

        pr_url = github_handler.create_pull_request(
            "AI Code Review Changes",
            "This pull request contains changes suggested by the AI code review.",
        )
        logger.info(f"Pull request created: {pr_url}")

        github_handler.cleanup()
        logger.info("Temporary files cleaned up. Review process finished.")

        # Remove the checkpoint file as the process is complete
        if os.path.exists(checkpoint_file):
            os.remove(checkpoint_file)

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        logger.info("Saving checkpoint before exiting...")
        save_checkpoint(checkpoint_file, repo_structure, previous_results)
        logger.info("You can resume the process later by running the script again.")
        raise


def parse_sub_agent_result(result):
    changes = {}
    current_file = None
    current_content = []

    for line in result.split("\n"):
        if line.startswith("[") and line.endswith("]"):
            if current_file:
                changes[current_file] = (
                    "\n".join(current_content) if current_content else None
                )
            current_file = line[1:-1]
            current_content = []
        elif line.startswith("DELETE:"):
            file_to_delete = line.split("DELETE:")[1].strip()
            changes[file_to_delete] = None
        elif current_file:
            current_content.append(line)

    if current_file:
        changes[current_file] = "\n".join(current_content) if current_content else None

    return changes


if __name__ == "__main__":
    main()
