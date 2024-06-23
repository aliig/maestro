import os
import shutil
import tempfile
import time

from git import Repo
from github import Github

from logger import logger


class GitHubHandler:
    def __init__(self, repo_url, token, file_types=None, exclude_dirs=None):
        self.g = Github(token)
        self.repo = self.g.get_repo(repo_url)
        self.local_path = None
        self.branch_name = f"ai-code-review-{int(time.time())}"
        self.file_types = file_types or [
            ".py",
            ".js",
            ".java",
            ".cs",
            ".cpp",
            ".h",
            ".rb",
            ".go",
        ]
        self.exclude_dirs = exclude_dirs or []
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

    def get_repo_structure(self):
        structure = {}
        for root, dirs, files in os.walk(self.local_path):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]

            path = root.split(os.sep)
            current_level = structure
            for folder in path[path.index(os.path.basename(self.local_path)) + 1 :]:
                current_level = current_level.setdefault(folder, {})
            for file in files:
                if any(file.endswith(ft) for ft in self.file_types):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r") as f:
                        content = f.read()
                    current_level[file] = content
        return structure

    def commit_changes(self, changes):
        repo = Repo(self.local_path)
        renamed_files = set()

        for operation, details in changes.items():
            if operation == "modify":
                for file_path, content in details.items():
                    self._modify_file(repo, file_path, content)
            elif operation == "delete":
                for file_path in details:
                    if file_path not in renamed_files:
                        self._delete_file(repo, file_path)
            elif operation == "rename":
                for old_path, new_path in details.items():
                    self._rename_file(repo, old_path, new_path)
                    renamed_files.add(old_path)
            elif operation == "mkdir":
                for dir_path in details:
                    self._create_directory(dir_path)

        if repo.index.diff("HEAD"):
            commit_message = "AI code review changes: Complete refactor"
            repo.index.commit(commit_message)
            origin = repo.remote(name="origin")
            origin.push(self.branch_name)
            logger.info(
                f"Committed and pushed refactor changes to branch: {self.branch_name}"
            )
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
