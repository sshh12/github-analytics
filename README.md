# github-analytics

```python
from github_analytics import analyze

pr_analysis = analyze.PRAnalyzer(
    "organization/repo",
    "organization",
    "team-name",
    github_api_token="github-access-token" # or GITHUB_API_TOKEN
)
pr_analysis.download()
pr_analysis.plot_hours_to_merge_histogram()
```
