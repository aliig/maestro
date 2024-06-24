import fnmatch
import os
import shutil
import tempfile
import time

import chardet
from git import Repo
from github import Github

from logger import logger


class GitHubHandler:
    def __init__(
        self,
        repo_url,
        token,
        include_patterns=None,
        exclude_patterns=None,
        max_file_size=1024 * 1024,
    ):
        self.g = Github(token)
        self.repo = self.g.get_repo(repo_url)
        self.local_path = None
        self.branch_name = f"ai-code-review-{int(time.time())}"
        self.include_patterns = include_patterns or ["*"]
        self.exclude_patterns = exclude_patterns or []
        self.max_file_size = max_file_size  # Default to 1MB
        self.clone_repo()
        self.create_new_branch()

    def clone_repo(self):
        self.local_path = tempfile.mkdtemp()
        clone_url = self.repo.clone_url.replace(
            "https://",
            f"https://{self.g.get_user().login}:{self.g._Github__requester._Github__auth.token}@",
        )
        Repo.clone_from(clone_url, self.local_path)
        logger.info(f"Repository cloned to {self.local_path}")

    def create_new_branch(self):
        repo = Repo(self.local_path)
        current = repo.create_head(self.branch_name)
        current.checkout()
        logger.info(f"Created and checked out new branch: {self.branch_name}")

    def is_binary_file(self, file_path):
        with open(file_path, "rb") as file:
            chunk = file.read(1024)  # Read first 1024 bytes
            result = chardet.detect(chunk)
            if result["encoding"] is None:
                return True
            return False

    def get_repo_structure(self):
        structure = {}
        for root, dirs, files in os.walk(self.local_path):
            path = root.split(os.sep)
            current_level = structure
            for folder in path[path.index(os.path.basename(self.local_path)) + 1 :]:
                current_level = current_level.setdefault(folder, {})
            for file in files:
                if self.should_include_file(file):
                    file_path = os.path.join(root, file)
                    if os.path.getsize(
                        file_path
                    ) <= self.max_file_size and not self.is_binary_file(file_path):
                        try:
                            with open(file_path, "rb") as f:
                                raw_data = f.read()
                            result = chardet.detect(raw_data)
                            encoding = result["encoding"] or "utf-8"
                            content = raw_data.decode(encoding)
                            current_level[file] = content
                        except UnicodeDecodeError:
                            # If we still can't decode it, skip this file
                            pass
        return structure

    def should_include_file(self, filename):
        return any(
            fnmatch.fnmatch(filename, pattern) for pattern in self.include_patterns
        ) and not any(
            fnmatch.fnmatch(filename, pattern) for pattern in self.exclude_patterns
        )

    def commit_changes(self, changes):
        repo = Repo(self.local_path)
        for operation, details in changes.items():
            if operation == "modify":
                for file_path, content in details.items():
                    full_path = os.path.join(self.local_path, file_path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    repo.index.add([file_path])
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
            repo.index.commit(commit_message)
            origin = repo.remote(name="origin")
            origin.push(self.branch_name)
            logger.info(f"Committed and pushed changes to branch: {self.branch_name}")
        else:
            logger.info("No changes to commit")

    def _modify_file(self, repo, file_path, content):
        full_path = os.path.join(self.local_path, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
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
        pr = self.repo.create_pull(
            title=title, body=body, head=self.branch_name, base=self.repo.default_branch
        )
        logger.info(f"Created pull request: {pr.html_url}")
        return pr.html_url

    def cleanup(self):
        if self.local_path and os.path.exists(self.local_path):
            shutil.rmtree(self.local_path)
            logger.info(f"Cleaned up temporary directory: {self.local_path}")

    def update_readme(self, new_content):
        readme_path = os.path.join(self.local_path, "README.md")
        with open(readme_path, "w") as f:
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
            with open(readme_path, "r") as f:
                return f.read()
        return ""
