import os
from anthropic import Anthropic
import re
from rich.console import Console
from rich.panel import Panel
from datetime import datetime
import json
from tavily import TavilyClient
from functools import wraps
from anthropic import RateLimitError
import pickle
import time
import argparse
from datetime import datetime, timezone
import math

# Set up the Anthropic API client
client = Anthropic(api_key="temp")

ORCHESTRATOR_MODEL = "claude-3-5-sonnet-20240620"
SUB_AGENT_MODEL = "claude-3-5-sonnet-20240620"
REFINER_MODEL = "claude-3-5-sonnet-20240620"

def save_checkpoint(checkpoint_file, full_structure, processed_structure, review_results):
    with open(checkpoint_file, 'wb') as f:
        pickle.dump((full_structure, processed_structure, review_results), f)
    console.print(f"[bold green]Checkpoint saved to {checkpoint_file}[/bold green]")

def load_checkpoint(checkpoint_file):
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'rb') as f:
            full_structure, processed_structure, review_results = pickle.load(f)
        console.print(f"[bold green]Checkpoint loaded from {checkpoint_file}[/bold green]")
        return full_structure, processed_structure, review_results
    return None

def parse_rfc3339(timestamp: str) -> datetime:
    # Match timestamps with and without fractional seconds
    pattern_with_fraction = re.compile(r"\.\d+Z$")
    if pattern_with_fraction.search(timestamp):
        return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    else:
        return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def retry_on_rate_limit(max_retries=5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:
                    retries += 1
                    if retries == max_retries:
                        raise e

                    response = e.response
                    headers = response.headers

                    # Parse rate limit information from headers
                    requests_remaining = int(headers.get('anthropic-ratelimit-requests-remaining', 0))
                    tokens_remaining = int(headers.get('anthropic-ratelimit-tokens-remaining', 0))
                    requests_reset = parse_rfc3339(headers.get('anthropic-ratelimit-requests-reset', ''))
                    tokens_reset = parse_rfc3339(headers.get('anthropic-ratelimit-tokens-reset', ''))

                    # Calculate wait times
                    now = datetime.now(timezone.utc)
                    requests_wait = max((requests_reset - now).total_seconds(), 0)
                    tokens_wait = max((tokens_reset - now).total_seconds(), 0)

                    # Choose the longer wait time
                    wait_time = max(requests_wait, tokens_wait)

                    # If we have a 'Retry-After' header, use that if it's longer
                    retry_after = float(headers.get('retry-after', 0))
                    wait_time = max(wait_time, retry_after)

                    # Add a small buffer (e.g., 1 second) to ensure we're past the reset
                    wait_time += 1

                    console.print(f"[yellow]Rate limit reached. Retrying in {math.ceil(wait_time)} seconds...[/yellow]")
                    console.print(f"[yellow]Requests remaining: {requests_remaining}, Tokens remaining: {tokens_remaining}[/yellow]")

                    time.sleep(wait_time)

            raise RateLimitError("Max retries reached")
        return wrapper
    return decorator

def parse_arguments():
    parser = argparse.ArgumentParser(description="Agentic Code Review")
    parser.add_argument("input_dir", help="Input directory of the Python project")
    parser.add_argument("-o", "--output_dir", help="Output directory for the improved project (default: './output')")
    parser.add_argument("--ignore", nargs="*", default=[], help="Directories to ignore")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint if available")
    args = parser.parse_args()

    # Set default output directory if not specified
    if not args.output_dir:
        args.output_dir = os.path.join(os.getcwd(), "output")

    return args

args = parse_arguments()

def read_project_structure(input_dir, ignore_dirs):
    full_structure = {}
    processed_structure = {}

    for root, dirs, files in os.walk(input_dir):
        rel_path = os.path.relpath(root, input_dir)
        current_full_level = full_structure
        current_processed_level = processed_structure

        for part in rel_path.split(os.sep):
            if part != '.':
                current_full_level = current_full_level.setdefault(part, {})
                if not any(ignored in root for ignored in ignore_dirs):
                    current_processed_level = current_processed_level.setdefault(part, {})

        for file in files:
            current_full_level[file] = None  # Just marking the file's presence
            if file.endswith('.py') and not any(ignored in root for ignored in ignore_dirs):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    current_processed_level[file] = f.read()

    return full_structure, processed_structure

# Initialize the Rich Console
console = Console()

@retry_on_rate_limit()
def opus_orchestrator(full_structure, processed_structure, previous_results=None):
    console.print(f"\n[bold]Calling Orchestrator for code review[/bold]")
    previous_results_text = "\n".join(previous_results) if previous_results else "None"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Review the following Python project structure and provide the next code review task. Focus on improving code quality, completing unfinished features, and suggesting necessary changes. Be concise and prioritize the most important issues. Avoid generating extensive comments or example usage for methods/functions unless absolutely necessary.\n\nFull project structure:\n{json.dumps(full_structure, indent=2)}\n\nProcessed structure:\n{json.dumps(processed_structure, indent=2)}\n\nPrevious review results:\n{previous_results_text}"}
            ]
        }
    ]

    opus_response = client.messages.create(
        model=ORCHESTRATOR_MODEL,
        max_tokens=4096,
        messages=messages
    )

    response_text = opus_response.content[0].text
    console.print(Panel(response_text, title=f"[bold green]Opus Orchestrator[/bold green]", title_align="left", border_style="green", subtitle="Sending task to Haiku 👇"))
    return response_text

@retry_on_rate_limit()
def haiku_sub_agent(prompt, full_structure, processed_structure, previous_haiku_tasks=None):
    if previous_haiku_tasks is None:
        previous_haiku_tasks = []

    # Create a string representation of previous tasks
    previous_tasks_str = "\n".join(f"Task {i+1}: {task}" for i, task in enumerate(previous_haiku_tasks))
    system_message = f"Previous Haiku tasks:\n{previous_tasks_str}"

    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": f"{prompt}\n\nFull project structure:\n{json.dumps(full_structure, indent=2)}\n\nProcessed structure:\n{json.dumps(processed_structure, indent=2)}\n\nPlease provide a concise response focusing on the most critical changes. Avoid generating extensive comments or example usage for methods/functions unless absolutely necessary."}]
        }
    ]

    haiku_response = client.messages.create(
        model=SUB_AGENT_MODEL,
        max_tokens=4096,
        messages=messages,
        system=system_message
    )

    response_text = haiku_response.content[0].text
    console.print(Panel(response_text, title="[bold blue]Haiku Sub-agent Result[/bold blue]", title_align="left", border_style="blue", subtitle="Task completed, sending result to Opus 👇"))
    return response_text

@retry_on_rate_limit()
def opus_refine(full_structure, processed_structure, review_results):
    print("\nCalling Opus to provide the final improved project structure:")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Based on the following project structures and code review results, provide an improved version of the project. Include necessary changes and improvements, focusing on the most critical issues. Be concise in your modifications and avoid generating extensive comments or example usage for methods/functions unless absolutely necessary.\n\nFull project structure:\n{json.dumps(full_structure, indent=2)}\n\nProcessed structure:\n{json.dumps(processed_structure, indent=2)}\n\nReview results:\n{review_results}\n\nPlease provide the improved project structure as a valid JSON object, where each key represents a folder or file, and nested keys represent subfolders. Use string values for file contents. Ensure the JSON is properly formatted without any syntax errors."}
            ]
        }
    ]

    opus_response = client.messages.create(
        model=REFINER_MODEL,
        max_tokens=4096,
        messages=messages
    )

    response_text = opus_response.content[0].text.strip()
    console.print(Panel(response_text, title="[bold green]Final Improved Project Structure[/bold green]", title_align="left", border_style="green"))
    return json.loads(response_text)

def write_improved_project(output_dir, improved_structure):
    def create_folders_and_files(current_path, structure):
        for key, value in structure.items():
            path = os.path.join(current_path, key)
            if isinstance(value, dict):
                os.makedirs(path, exist_ok=True)
                console.print(f"Created folder: [bold blue]{path}[/bold blue]")
                create_folders_and_files(path, value)
            else:
                with open(path, 'w') as file:
                    file.write(value)
                console.print(f"Created/Updated file: [bold green]{path}[/bold green]")

    create_folders_and_files(output_dir, improved_structure)
    console.print(f"\n[bold]Improved project structure written to: {output_dir}[/bold]")

def create_folder_structure(project_name, folder_structure, code_blocks):
    # Create the project folder
    try:
        os.makedirs(project_name, exist_ok=True)
        console.print(Panel(f"Created project folder: [bold]{project_name}[/bold]", title="[bold green]Project Folder[/bold green]", title_align="left", border_style="green"))
    except OSError as e:
        console.print(Panel(f"Error creating project folder: [bold]{project_name}[/bold]\nError: {e}", title="[bold red]Project Folder Creation Error[/bold red]", title_align="left", border_style="red"))
        return

    # Recursively create the folder structure and files
    create_folders_and_files(project_name, folder_structure, code_blocks)

def create_folders_and_files(current_path, structure, code_blocks):
    for key, value in structure.items():
        path = os.path.join(current_path, key)
        if isinstance(value, dict):
            try:
                os.makedirs(path, exist_ok=True)
                console.print(Panel(f"Created folder: [bold]{path}[/bold]", title="[bold blue]Folder Creation[/bold blue]", title_align="left", border_style="blue"))
                create_folders_and_files(path, value, code_blocks)
            except OSError as e:
                console.print(Panel(f"Error creating folder: [bold]{path}[/bold]\nError: {e}", title="[bold red]Folder Creation Error[/bold red]", title_align="left", border_style="red"))
        else:
            code_content = next((code for file, code in code_blocks if file == key), None)
            if code_content:
                try:
                    with open(path, 'w') as file:
                        file.write(code_content)
                    console.print(Panel(f"Created file: [bold]{path}[/bold]", title="[bold green]File Creation[/bold green]", title_align="left", border_style="green"))
                except IOError as e:
                    console.print(Panel(f"Error creating file: [bold]{path}[/bold]\nError: {e}", title="[bold red]File Creation Error[/bold red]", title_align="left", border_style="red"))
            else:
                console.print(Panel(f"Code content not found for file: [bold]{key}[/bold]", title="[bold yellow]Missing Code Content[/bold yellow]", title_align="left", border_style="yellow"))


def main():
    args = parse_arguments()

    # Ensure the output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    checkpoint_file = os.path.join(args.output_dir, 'review_checkpoint.pkl')

    # Try to load from checkpoint
    checkpoint_data = load_checkpoint(checkpoint_file)
    if checkpoint_data:
        full_structure, processed_structure, review_results = checkpoint_data
    else:
        full_structure, processed_structure = read_project_structure(args.input_dir, args.ignore)
        review_results = []

    try:
        iteration = 0
        while True:
            orchestrator_result = opus_orchestrator(full_structure, processed_structure, review_results)
            if "The review is complete:" in orchestrator_result:
                break
            sub_agent_result = haiku_sub_agent(orchestrator_result, full_structure, processed_structure, review_results)
            review_results.append(sub_agent_result)

            # Save checkpoint every 5 iterations (you can adjust this number)
            iteration += 1
            if iteration % 5 == 0:
                save_checkpoint(checkpoint_file, full_structure, processed_structure, review_results)

        improved_structure = opus_refine(full_structure, processed_structure, "\n".join(review_results))
        write_improved_project(args.output_dir, improved_structure)

        # Clear the checkpoint file as the process is complete
        if os.path.exists(checkpoint_file):
            os.remove(checkpoint_file)

        console.print(f"\n[bold green]Code review and improvements complete. Results written to: {args.output_dir}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]An error occurred: {str(e)}[/bold red]")
        console.print("[yellow]Saving current state to checkpoint...[/yellow]")
        save_checkpoint(checkpoint_file, full_structure, processed_structure, review_results)
        console.print("[green]You can resume the process later by running the script again.[/green]")
        raise

if __name__ == "__main__":
    main()