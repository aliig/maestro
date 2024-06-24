# AI-Powered Code Review

AI-Powered Code Review is an automated tool that leverages artificial intelligence to perform comprehensive code reviews on GitHub repositories. It aims to improve code quality, identify potential issues, and suggest improvements across various file types and programming languages.

## Features

- Automated code review using AI (supports multiple AI platforms)
- GitHub integration for seamless repository analysis and pull request creation
- Customizable file inclusion/exclusion patterns
- Support for multiple programming languages and file types
- Automatic exclusion of binary files
- Resumable reviews with checkpoint system
- Configurable review depth and token budget
- Efficient token estimation and AI platform rotation
- Robust rate limit handling and retry mechanism

## Prerequisites

- Python 3.12 or higher
- Miniconda or Anaconda

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ai-powered-code-review.git
cd ai-powered-code-review
```
2. Create and activate the Conda environment:
```bash
conda env create -f environment.yml
conda activate ai-code-review
```

## Configuration

1. Edit `config.yml` and add your API keys:
```yaml
github_token: "your_github_token_here"

ai_platforms:
  - provider: "anthropic"
    model: "claude-3-5-sonnet-20240620"
    max_tokens: 4096
    keys:
    - "your_anthropic_api_key_1_here"
    - "your_anthropic_api_key_2_here"
  - provider: "openai"
    model: "gpt-4"
    max_tokens: 8192
    keys:
    - "your_openai_api_key_1_here"
    - "your_openai_api_key_2_here"
```

Alternatively, you can set the following environment variables:

- `GITHUB_TOKEN`
- `ANTHROPIC_API_KEY` (comma-separated if multiple)
- `OPENAI_API_KEY` (comma-separated if multiple)

## Usage

Run the main script with the GitHub repository URL you want to review:
```bash
python main.py https://github.com/username/repo-to-review
```

Additional options:

- `--review_depth`: Choose between "minimum", "balanced", or "comprehensive" (default: "balanced")
- `--config`: Specify a custom config file path (default: "config.yml")
- `--max_file_size`: Set maximum file size to review in bytes (default: 1MB)

Example with options:
```bash
python main.py https://github.com/username/repo-to-review --review_depth comprehensive --max_file_size 2097152
```

## Customizing Review Scope

Create a `.aireviews` file in the root of the repository you're reviewing to customize which files are included or excluded:
```
### Include all files by default
*

### Exclude specific directories
node_modules/
vendor/

### Exclude specific file types
*.log
*.tmp

### Include a specific file that would otherwise be excluded
!important_config.log
```

## Performance Considerations

- The tool now uses `tiktoken` for more accurate token estimation, which may affect the total number of API calls made during a review.
- AI platform rotation has been optimized to handle rate limits more efficiently, reducing wait times between calls when possible.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Troubleshooting

If you encounter rate limit issues, the tool will automatically retry with exponential backoff. However, if problems persist, consider:

1. Adding more API keys to the configuration.
2. Adjusting the `max_tokens_per_call` and `token_budget` settings in the `config.yml` file.
3. Using the `--review_depth minimum` option for larger repositories to reduce the number of API calls.

For any other issues, please check the logs or open an issue on the GitHub repository.