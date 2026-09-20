> “Workers shall not be discriminated against in employment, regardless of their ethnicity, race, gender, or religious belief.” — Employment Promotion Law of the People's Republic of China, Article 3

<h1 align="center">Hiring Agent CN</h1>

<p align="center">An evidence-first, human-reviewed resume and job matching tool for mainland China.</p>

Hiring Agent CN is a deep fork of [interviewstreet/hiring-agent](https://github.com/interviewstreet/hiring-agent). It replaces a GitHub-heavy resume score with a safer workflow: sanitize candidate-controlled documents, remove identity attributes before matching, require a recruiter to confirm the job profile, cite every conclusion, generate verification questions, and keep the final decision with a human.

## Security first

The parser quarantines low-contrast text, low-opacity text, invisible PDF rendering modes, micro text, off-page text, later-covered text, Unicode controls, and Chinese or English prompt-injection instructions. Candidate-provided GitHub, Gitee, and GitCode descriptions pass through the same instruction filter. Suspicious text never enters matching or optional model input.

See the Chinese [README](README.md), [security model](docs/security-model.md), [architecture](docs/architecture.md), and [compliance boundary](docs/compliance.md) for the complete design.

## Quick start

```bash
git clone https://github.com/TongyiDai/hiring-agent-cn.git
cd hiring-agent-cn
uv sync --extra dev --frozen
uv run hiring-agent-cn review examples/resume-synthetic.txt \
  --job examples/job-backend.md \
  --title "Backend Engineer" \
  --confirm-job-profile \
  --output review-report.html
```

The deterministic workflow does not require a model or API key. Run `uv run hiring-agent-cn serve` for the local UI. This project deliberately exposes no automatic reject or hiring endpoint.

## Validation

```bash
uv run ruff check hiring_agent_cn tests
uv run ruff format --check hiring_agent_cn tests
uv run mypy hiring_agent_cn
uv run pytest
```

All public fixtures are synthetic. Do not upload real resumes or personal data to issues or pull requests. This software is not legal advice and does not by itself make a deployment compliant.

## License and attribution

MIT. This fork retains the original HackerRank copyright and Git history.
