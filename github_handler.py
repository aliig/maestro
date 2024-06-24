import fnmatch
import os
import shutil
import tempfile
import time
from urllib.parse import urlparse

import chardet
from git import Repo
from github import Github, GithubException
from tenacity import retry, stop_after_attempt, wait_exponential

from logger import logger
from utils import preprocess_ai_response


class GitHubHandler:
    def __init__(self, repo_url, token):
        self.g = Github(token)
        self.token = token
        try:
            parsed_url = urlparse(repo_url)
            path_parts = parsed_url.path.strip("/").split("/")
            if len(path_parts) < 2:
                raise ValueError(f"Invalid repository URL format: {repo_url}")
            owner, repo_name = path_parts[-2:]
            self.repo = self.g.get_repo(f"{owner}/{repo_name}")
        except Exception as e:
            logger.error(f"Error accessing repository: {str(e)}")
            raise ValueError(f"Error accessing repository: {str(e)}")

        self.local_path = None
        self.branch_name = f"ai-code-review-{int(time.time())}"
        self.clone_repo()
        self.create_new_branch()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def clone_repo(self):
        try:
            self.local_path = tempfile.mkdtemp()
            clone_url = self.repo.clone_url.replace(
                "https://", f"https://x-access-token:{self.token}@"
            )
            Repo.clone_from(clone_url, self.local_path)
            logger.info(f"Repository cloned to {self.local_path}")
        except Exception as e:
            logger.error(f"Error cloning repository: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def create_new_branch(self):
        try:
            repo = Repo(self.local_path)
            current = repo.create_head(self.branch_name)
            current.checkout()
            logger.info(f"Created and checked out new branch: {self.branch_name}")
        except Exception as e:
            logger.error(f"Error creating new branch: {str(e)}")
            raise

    def get_file_content(self, file_path):
        full_path = os.path.join(self.local_path, file_path)
        if os.path.exists(full_path) and self.should_include_file(file_path):
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {str(e)}")
                return "Error reading file content"
        return "File not found or not accessible"

    def get_repo_structure(self):
        for root, dirs, files in os.walk(self.local_path):
            if ".git" in dirs:
                dirs.remove(".git")

            for file in files:
                if self.should_include_file(file):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, self.local_path)
                    if os.path.getsize(file_path) <= self.max_file_size and not self.is_binary_file(file_path):
                        yield relative_path, self.lazy_load_file_content(file_path)
                    else:
                        yield relative_path, "<<< File too large or binary >>>"

    def lazy_load_file_content(self, file_path):
        def load_content():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            except UnicodeDecodeError:
                return "<<< Unable to decode file content >>>"
        return load_content

    def should_include_file(self, filename):
        return any(
            self._match_pattern(filename, pattern) for pattern in self.include_patterns
        ) and not any(
            self._match_pattern(filename, pattern) for pattern in self.exclude_patterns
        )

    def _match_pattern(self, filename, pattern):
        return fnmatch.fnmatch(filename, pattern)

    def is_binary_file(self, file_path):
        try:
            with open(file_path, "tr") as check_file:
                check_file.read()
                return False
        except:
            return True

    def get_current_file_path(self, original_path):
        if os.path.exists(os.path.join(self.local_path, original_path)):
            return original_path

        for root, dirs, files in os.walk(self.local_path):
            if os.path.basename(original_path) in files:
                return os.path.relpath(
                    os.path.join(root, os.path.basename(original_path)), self.local_path
                )

        return original_path

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def commit_changes(self, changes):
        repo = Repo(self.local_path)
        try:
            for operation, details in changes.items():
                if operation == "modify":
                    for file_path, content in details.items():
                        new_path = self.get_current_file_path(file_path)
                        full_path = os.path.join(self.local_path, new_path)
                        processed_content = preprocess_ai_response(content)
                        os.makedirs(os.path.dirname(full_path), exist_ok=True)
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(processed_content)
                        repo.index.add([new_path])
                elif operation == "delete":
                    for file_path in details:
                        full_path = os.path.join(self.local_path, file_path)
                        if os.path.exists(full_path):
                            os.remove(full_path)
                            repo.index.remove([file_path])
                elif operation == "rename":
                    for old_path, new_path in details.items():
                        old_full_path = os.path.join(self.local_path, old_path)
                        new_full_path = os.path.join(self.local_path, new_path)
                        os.makedirs(os.path.dirname(new_full_path), exist_ok=True)
                        os.rename(old_full_path, new_full_path)
                        repo.index.move([old_path, new_path])
                elif operation == "mkdir":
                    for dir_path in details:
                        full_path = os.path.join(self.local_path, dir_path)
                        os.makedirs(full_path, exist_ok=True)

            if repo.index.diff("HEAD"):
                commit_message = "AI code review changes"
                repo.git.commit("-m", commit_message)
                origin = repo.remote(name="origin")
                origin.push(self.branch_name)
                logger.info(f"Committed and pushed changes to branch: {self.branch_name}")
            else:
                logger.info("No changes to commit")
        except Exception as e:
            logger.error(f"Error committing changes: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def create_pull_request(self, title, body):
        try:
            pr = self.repo.create_pull(
                title=title,
                body=body,
                head=self.branch_name,
                base=self.repo.default_branch,
            )
            logger.info(f"Created pull request: {pr.html_url}")
            return pr.html_url
        except Exception as e:
            logger.error(f"Error creating pull request: {str(e)}")
            raise

    def cleanup(self):
        if self.local_path and os.path.exists(self.local_path):
            try:
                shutil.rmtree(self.local_path)
                logger.info(f"Cleaned up temporary directory: {self.local_path}")
            except Exception as e:
                logger.warning(
                    f"Error cleaning up temporary directory: {self.local_path}. Error: {str(e)}"
                )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def update_readme(self, new_content):
        try:
            readme_path = os.path.join(self.local_path, "README.md")
            with open(readme_path, "w") as f:
                f.write(new_content)
            repo = Repo(self.local_path)
            repo.index.add(["README.md"])
            repo.index.commit("Update README.md based on AI code review")
            origin = repo.remote(name="origin")
            origin.push(self.branch_name)
            logger.info("Updated README.md based on AI analysis")
        except Exception as e:
            logger.error(f"Error updating README: {str(e)}")
            raise

    def get_readme_content(self):
        try:
            readme_path = os.path.join(self.local_path, "README.md")
            if os.path.exists(readme_path):
                with open(readme_path, "r") as f:
                    return f.read()
            return ""
        except Exception as e:
            logger.error(f"Error reading README content: {str(e)}")
            return ""
