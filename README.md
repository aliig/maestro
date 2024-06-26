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
- Interactive user input for review configuration
- Improved error handling and logging
- Progress indication during code review process

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
    keys:
    - "your_anthropic_api_key_here"
  - provider: "openai"
    model: "gpt-4"
    keys:
    - "your_openai_api_key_here"
```

Alternatively, you can set the following environment variables:

- `GITHUB_TOKEN`
- `ANTHROPIC_API_KEY` (comma-separated if multiple)
- `OPENAI_API_KEY` (comma-separated if multiple)

## Usage

Run the main script:
```bash
python main.py
```

The script will interactively prompt you for the following information:

1. GitHub repository URL
2. Review depth (minimum, balanced, or comprehensive)
3. Maximum file size to review in megabytes
4. File patterns to include and exclude
5. Additional review instructions (optional)

Follow the prompts to configure your code review process. The tool will display progress information as it performs the review.

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

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is released under the MIT License.