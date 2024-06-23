import os
import shutil
import tempfile
import time

from git import Repo
from github import Github

from logger import logger


class GitHubHandler:
    def __init__(self, repo_url, token):
        self.g = Github(token)
        self.repo = self.g.get_repo(repo_url)
        self.local_path = None
        self.branch_name = f"ai-code-review-{int(time.time())}"
        self.clone_repo()
        self.create_new_branch()

    def clone_repo(self):
        self.local_path = tempfile.mkdtemp()
        clone_url = self.repo.clone_url.replace(
            "https://",
            f"https://{self.g.get_user().login}:{self.g._Github__requester._Github__auth.token}@",
        )
        Repo.clone_from(clone_url, self.local_path)
        print(f"Repository cloned to {self.local_path}")

    def create_new_branch(self):
        repo = Repo(self.local_path)
        current = repo.create_head(self.branch_name)
        current.checkout()
        print(f"Created and checked out new branch: {self.branch_name}")

    def get_repo_structure(self):
        structure = {}
        for root, dirs, files in os.walk(self.local_path):
            path = root.split(os.sep)
            current_level = structure
            for folder in path[path.index(os.path.basename(self.local_path)) + 1 :]:
                current_level = current_level.setdefault(folder, {})
            for file in files:
                if file.endswith(".py"):  # Only include Python files
                    file_path = os.path.join(root, file)
                    with open(file_path, "r") as f:
                        content = f.read()
                    current_level[file] = content
        return structure

    def commit_changes(self, changes):
        repo = Repo(self.local_path)
        for file_path, content in changes.items():
            full_path = os.path.join(self.local_path, file_path)

            if content is None:
                # Delete file
                if os.path.exists(full_path):
                    os.remove(full_path)
                    repo.index.remove([file_path])
                    logger.info(f"Deleted file: {file_path}")
            else:
                # Create or update file
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w") as f:
                    f.write(content)
                repo.index.add([file_path])
                action = "Created" if not os.path.exists(full_path) else "Updated"
                logger.info(f"{action} file: {file_path}")

        if repo.index.diff("HEAD"):
            commit_message = "AI code review changes"
            repo.index.commit(commit_message)
            origin = repo.remote(name="origin")
            origin.push(self.branch_name)
            logger.info(f"Committed and pushed changes to branch: {self.branch_name}")
        else:
            logger.info("No changes to commit")

    def create_pull_request(self, title, body):
        pr = self.repo.create_pull(
            title=title, body=body, head=self.branch_name, base=self.repo.default_branch
        )
        print(f"Created pull request: {pr.html_url}")
        return pr.html_url

    def cleanup(self):
        if self.local_path and os.path.exists(self.local_path):
            shutil.rmtree(self.local_path)
            print(f"Cleaned up temporary directory: {self.local_path}")
