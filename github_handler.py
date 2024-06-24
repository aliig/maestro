import fnmatch
import os
import shutil
import tempfile
import time
from urllib.parse import urlparse

import chardet
from git import Repo
from github import Github, GithubException

from logger import logger


class GitHubHandler:
    def __init__(self, repo_url, token, include_patterns=None, exclude_patterns=None, max_file_size=1000000):
        self.g = Github(token)
        self.token = token
        self.include_patterns = include_patterns or ['*']
        self.exclude_patterns = exclude_patterns or []
        self.max_file_size = max_file_size

        try:
            parsed_url = urlparse(repo_url)
            path_parts = parsed_url.path.strip("/").split("/")
            if len(path_parts) < 2:
                raise ValueError(f"Invalid repository URL format: {repo_url}")
            owner, repo_name = path_parts[-2:]
            self.repo = self.g.get_repo(f"{owner}/{repo_name}")
        except Exception as e:
            raise ValueError(f"Error accessing repository: {str(e)}")

        self.local_path = None
        self.branch_name = f"ai-code-review-{int(time.time())}"
        self.clone_repo()
        self.create_new_branch()

    def clone_repo(self):
        self.local_path = tempfile.mkdtemp()
        clone_url = self.repo.clone_url.replace(
            "https://", f"https://x-access-token:{self.token}@"
        )
        Repo.clone_from(clone_url, self.local_path)
        logger.info(f"Repository cloned to {self.local_path}")

    def create_new_branch(self):
        repo = Repo(self.local_path)
        current = repo.create_head(self.branch_name)
        current.checkout()
        logger.info(f"Created and checked out new branch: {self.branch_name}")

    def get_file_content(self, file_path):
        full_path = os.path.join(self.local_path, file_path)
        if os.path.exists(full_path) and self.should_include_file(file_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    return f.read()
            except UnicodeDecodeError:
                logger.warning(f"Failed to read {file_path} as UTF-8. It might be a binary file.")
                return None
        return None

    def get_repo_structure(self):
        structure = {}
        for root, dirs, files in os.walk(self.local_path):
            if ".git" in dirs:
                dirs.remove(".git")

            path = root.split(os.sep)
            current_level = structure
            for folder in path[path.index(os.path.basename(self.local_path)) + 1:]:
                current_level = current_level.setdefault(folder, {})

            for file in files:
                if self.should_include_file(file):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, self.local_path)
                    if os.path.getsize(file_path) <= self.max_file_size and not self.is_binary_file(file_path):
                        try:
                            with open(file_path, "rb") as f:
                                raw_data = f.read()
                            result = chardet.detect(raw_data)
                            encoding = result["encoding"] or "utf-8"
                            content = raw_data.decode(encoding)
                            current_level[relative_path] = f"<<< File content ({len(content)} characters) >>>"
                        except UnicodeDecodeError:
                            current_level[relative_path] = "<<< Unable to decode file content >>>"
                    else:
                        current_level[relative_path] = "<<< File too large or binary >>>"
        return structure

    def should_include_file(self, filename):
        return any(fnmatch.fnmatch(filename, pattern) for pattern in self.include_patterns) and \
               not any(fnmatch.fnmatch(filename, pattern) for pattern in self.exclude_patterns)

    def is_binary_file(self, file_path):
        try:
            with open(file_path, "tr") as check_file:
                check_file.read()
                return False
        except:
            return True

    def commit_changes(self, changes):
        repo = Repo(self.local_path)
        for operation, details in changes.items():
            if operation == "modify":
                for file_path, content in details.items():
                    self._modify_file(repo, file_path, content)
            elif operation == "delete":
                for file_path in details:
                    self._delete_file(repo, file_path)
            elif operation == "rename":
                for old_path, new_path in details.items():
                    self._rename_file(repo, old_path, new_path)
            elif operation == "mkdir":
                for dir_path in details:
                    self._create_directory(dir_path)

        if repo.index.diff("HEAD"):
            commit_message = "AI code review changes"
            repo.index.commit(commit_message)
            origin = repo.remote(name="origin")
            origin.push(self.branch_name)
            logger.info(f"Committed and pushed changes to branch: {self.branch_name}")
        else:
            logger.info("No changes to commit")

    def _modify_file(self, repo, file_path, content):
        full_path = os.path.join(self.local_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        repo.index.add([file_path])
        action = "Created" if not os.path.exists(full_path) else "Updated"
        logger.info(f"{action} file: {file_path}")

    def _delete_file(self, repo, file_path):
        full_path = os.path.join(self.local_path, file_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            repo.index.remove([file_path])
            logger.info(f"Deleted file: {file_path}")

    def _rename_file(self, repo, old_path, new_path):
        old_full_path = os.path.join(self.local_path, old_path)
        new_full_path = os.path.join(self.local_path, new_path)
        os.makedirs(os.path.dirname(new_full_path), exist_ok=True)
        shutil.move(old_full_path, new_full_path)
        repo.index.remove([old_path])
        repo.index.add([new_path])
        logger.info(f"Renamed file: {old_path} -> {new_path}")

    def _create_directory(self, dir_path):
        full_path = os.path.join(self.local_path, dir_path)
        os.makedirs(full_path, exist_ok=True)
        logger.info(f"Created directory: {dir_path}")

    def create_pull_request(self, title, body):
        try:
            pr = self.repo.create_pull(
                title=title, body=body, head=self.branch_name, base=self.repo.default_branch
            )
            logger.info(f"Created pull request: {pr.html_url}")
            return pr.html_url
        except GithubException as e:
            logger.error(f"Failed to create pull request: {str(e)}")
            return None

    def cleanup(self):
        if self.local_path and os.path.exists(self.local_path):
            try:
                shutil.rmtree(self.local_path)
                logger.info(f"Cleaned up temporary directory: {self.local_path}")
            except Exception as e:
                logger.warning(f"Error cleaning up temporary directory: {self.local_path}. Error: {str(e)}")

    def update_readme(self, new_content):
        readme_path = os.path.join(self.local_path, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        repo = Repo(self.local_path)
        repo.index.add(["README.md"])
        repo.index.commit("Update README.md based on AI code review")
        origin = repo.remote(name="origin")
        origin.push(self.branch_name)
        logger.info("Updated README.md based on AI analysis")

    def get_readme_content(self):
        readme_path = os.path.join(self.local_path, "README.md")
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""