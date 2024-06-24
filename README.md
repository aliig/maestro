Since there are no changes to the project structure or functionality, the existing README.md content remains accurate and does not require any updates. However, we can make some minor improvements to enhance clarity and provide more detailed information. Here's a slightly updated version of the README:

```markdown
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
       - "your_anthropic_api_key_here"
     - provider: "openai"
       model: "gpt-4"
       max_tokens: 8192
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
3. Maximum file size to review in bytes

Follow the prompts to configure your code review process.

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

## Project Structure

The project consists of the following main components:

- `ai_manager.py`: Handles AI-related operations
- `config_manager.py`: Manages configuration settings
- `github_handler.py`: Interfaces with GitHub API
- `main.py`: Entry point of the application
- `prompt_manager.py`: Manages AI prompts
- `utils.py`: Contains utility functions

Configuration files:
- `config.yml`: Main configuration file
- `prompts.yml`: Contains AI prompts
- `environment.yml`: Conda environment specification

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

[Add your chosen license here]

## Support

If you encounter any issues or have questions, please open an issue on the GitHub repository.
```

This updated README provides a bit more detail on the project structure and contribution process, which can be helpful for potential contributors and users of the project.