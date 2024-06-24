import json

import yaml


class PromptManager:
    def __init__(self, prompt_file):
        with open(prompt_file, "r") as f:
            self.prompts = yaml.safe_load(f)

    def get_orchestrator_prompt(
        self,
        repo_structure,
        review_depth,
        preferences,
        previous_results,
        additional_instructions,
    ):
        base_prompt = self.prompts["orchestrator"]["base"]
        all_areas = set(self.prompts["orchestrator"]["focus_areas"].keys())
        focus_areas = [
            area
            for area in preferences
            if preferences[area] and area != "additional_instructions"
        ]
        ignore_areas = all_areas - set(focus_areas)

        focus_areas_text = ", ".join(
            self.prompts["orchestrator"]["focus_areas"][area] for area in focus_areas
        )

        if ignore_areas:
            ignore_areas_text = self.prompts["orchestrator"]["ignore_message"].format(
                ignore_areas=", ".join(
                    self.prompts["orchestrator"]["focus_areas"][area]
                    for area in ignore_areas
                )
            )
        else:
            ignore_areas_text = ""

        depth_description = self.prompts["orchestrator"]["review_depths"][review_depth]

        return base_prompt.format(
            focus_areas=focus_areas_text,
            ignore_areas=ignore_areas_text,
            review_depth=depth_description,
            repo_structure=json.dumps(repo_structure, indent=2),
            previous_results=previous_results,
            additional_instructions=additional_instructions,
        )

    def get_sub_agent_prompt(self, task, repo_structure):
        base_prompt = self.prompts["sub_agent"]["base"]
        return base_prompt.format(
            task=task, repo_structure=json.dumps(repo_structure, indent=2)
        )
