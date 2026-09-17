<p align="center">
  <img src="public/brand/app-icon.svg" width="88" alt="A fountain pen inside a theatre arch" />
</p>

# Prospero's Study

**Your story. Every possible telling.**

A local workspace for writing fiction with AI. Draft a scene, explore another ending, build a shared world, or step into a character's role. Keep the versions you love and decide what becomes part of the story.

**v0.5 - early preview** Â· [Windows setup](#get-started-on-windows) / [Mac setup](#get-started-on-macos) Â· [Choose your models](#bring-your-own-writing-partner) Â· [Questions](#questions)

## A writing room for stories that keep growing

The interesting part often comes after the first response: a better line, a different choice, a character who surprises you. Prospero's Study gives those possibilities somewhere to go.

| What you want to do | How the Study helps |
| --- | --- |
| Try the other ending | Branch from an earlier passage, explore alternate responses, and find your way back with a visual branch map. |
| Keep control of the draft | Generated prose arrives separately for review. Accept it, keep an alternative on another branch, or leave it aside. |
| Build a world across several stories | Reuse Characters and Canon collections. Each story keeps its chosen versions until you decide to update it. |
| Talk through an idea | A sidebar collaborator can discuss the story, critique a passage, or help with a prompt without advancing the narrative. |
| Give different jobs to different models | Choose a Primary Writer, override individual steps, and deliberately compare several models on the same inputs. |
| Make room for surprise | Optional narrative tables introduce atmosphere, encounters, complications, and other prompts. Turn individual systems on or off. |

### Write, direct, or roleplay

Start with **Write a story** for prose and author direction, **Build a scene** for a guided planning and revision workflow, or **Roleplay** to participate as a character. Author notes stay distinct from story text, and roleplay preferences let you reserve your character's choices.

Submitting a passage can automatically request the next draft. Prefer to write uninterrupted? Turn off **Continue after sending** and generate when you are ready. Manual writing works without a model connection.

### Explore without losing your favorite version

Edit an earlier passage to create a new branch. Browse alternative responses, return to an accepted telling, and keep different continuations alive. The branch map makes those paths visible; changing your mind does not require replacing the story you already have.

### Give your world a home

The Library holds **Characters** and **Canon collections**: people, places, setting details, rules, and reference material. A collection can belong to several stories, and a story can draw on several collections.

Canon has Markdown working files you can edit with your preferred editor. Import Markdown or Character Card V1/V2/V3 JSON, including supported PNG character cards, and review the converted material before publishing it. Compatibility notes explain imported features that need attention.

Publishing an edit creates a new version. Existing stories keep their selected versions; you can compare changes and apply an update to the stories you choose. Earlier versions remain available.

### Keep a collaborator in the wings

Open the sidebar to brainstorm, ask about a character's motivation, improve your next prompt, or review what you have written. The collaborator can consult story context and retrieve exact passages when needed. It cannot advance the story or apply its suggestions on its own.

For a more structured session, the scene workflow brings together planning, drafting, dialogue, specialist reviews, revisions, and continuity proposals, with decisions left to you along the way.

### Make the room your own

Choose from six palettes, separate interface and reading fonts, independent text sizes, and reduced motion. Reading fonts include Literata, Arimo, Atkinson Hyperlegible, OpenDyslexic, Lora, and Source Serif 4. Fonts are bundled with the app.

Prompts live in secondary editors when you want to customize them. Enable or disable individual agents or whole sections; a mixed section switches back to **Enable all** on the next interaction.

## Coming from SillyTavern or another LLM chat app?

Bring your character cards and preferred model connections, then try a workflow organized around the story you are making:

- Explore alternate scenes through a visual branch map.
- Discuss a draft in the sidebar before deciding how the narrative should continue.
- Share versioned world material across several stories.
- Choose a different writer, reviewer, or collaborator for each job.
- Export a readable Markdown manuscript or a private archive of your work.

Character Card import includes a review step. Compatibility with every third-party extension, macro, or automation is not assumed; unsupported material is preserved with conversion notes.

## Bring your own writing partner

Use **Settings > Models** to save connections. **Test connection** discovers available models where the provider supports it, and the model picker lets you type to filter a long list. Reported limits help fill in your settings; limits a provider does not report remain editable.

| Connection | What you need |
| --- | --- |
| OpenAI | An OpenAI API key |
| Anthropic | An Anthropic API key |
| Google / Gemini | A Gemini API key |
| OpenRouter | An OpenRouter API key |
| Codex / ChatGPT | Codex CLI installed, available on PATH, and already signed in |
| Local / LM Studio | A running local server with an OpenAI-compatible API |
| Kobold | A running server exposing the native Kobold generation API |
| OAI Compatible API | A compatible Chat Completions API address and any required key |

Set one profile as **Primary Writer** to get started. Add role-specific profiles or explicit model comparisons when you need them. Profiles can use different providers; the app does not silently switch providers if a request fails.

Provider usage, pricing, and access depend on your chosen service. Models and API credits are not bundled with the application.

## Get started on Windows

1. **Download and extract the project.** Use GitHub's **Code > Download ZIP**, or clone this repository. Open the extracted folder before running the scripts.
2. **Run [install.bat](install.bat).** It sets up the dependencies and builds the interface. It looks for Python 3.12+ and Node.js 22.12+, and can install missing runtimes through WinGet. An internet connection is needed for downloads.
3. **Run [launch.bat](launch.bat).** Your browser opens the Study at `http://127.0.0.1:8765`. Keep the launcher terminal open while writing; press **Ctrl+C** there to stop the app.
4. **Start a new story.** The guided setup helps you choose how to write, connect a model, describe the story, and attach Library material. You can skip the model and write manually.

A second launch reuses the existing app. To update, stop the app, update the source files while keeping your `data/` folder, rerun `install.bat`, and launch again. Save a workspace backup before updating.

If WinGet is unavailable, install Python and Node.js yourself and rerun the installer.

## Get started on macOS

Download and extract the project, or clone this repository. In Terminal, change to the project folder and run:

```bash
cd "/path/to/prosperos-study"
bash install.sh
bash launch.sh
```

[install.sh](install.sh) creates the local Python environment, installs the pinned dependencies, and builds the interface. It uses an existing Python 3.12+ and Node.js 22.12+ installation when available. If either is missing, it can install it through [Homebrew](https://docs.brew.sh/Installation), using [Python 3.12](https://formulae.brew.sh/formula/python@3.12) and [Node.js 24](https://formulae.brew.sh/formula/node@24). Both standard Apple Silicon and Intel Homebrew locations are checked; Homebrew support depends on your macOS version and hardware. If Homebrew is not installed, the script explains how to install it or supply the runtimes yourself.

[launch.sh](launch.sh) opens `http://127.0.0.1:8765` and runs the app in the same terminal. Keep it open while writing; press **Ctrl+C** to stop. Launching again reuses a healthy running instance. It does not reinstall dependencies or start a hidden server.

Use `bash install.sh --check-only` to check an existing installation, or `bash launch.sh --no-browser --port 8765` to control launch options. After updating, stop the app, save a backup, rerun `bash install.sh`, and launch again. Keep your `data/` folder. If transferring the project between Windows and Mac, create a fresh `.venv` on the destination; Python environments are platform-specific.

The shell workflow has automated tests; installation, browser opening, and Keychain access still need a native macOS smoke test for this preview.


## Your work stays yours

Stories and Library material are stored locally in the project's `data/` folder. Cloud generation sends the context needed for a request to the provider you select; local model connections keep that inference on your own machine. API keys are stored separately in the operating system's credential vault.

- **Export transcript** creates readable Markdown for a selected branch or passage.
- **Private archive & recovery** saves a story with its branches, connected Library versions, and saved workflow records.
- **Settings > Backups** creates a workspace backup or restores a saved archive as new stories.

Readable exports and restorable archives serve different purposes. Private archives contain story material and are not encrypted. Keep downloaded backups somewhere safe; automatic scheduled backups are not included in v0.5.

## Questions

**Can I use it without a cloud subscription?**

Yes. Use a compatible local model server, or write manually. Local generation requires a model and hardware capable of running it. Installation still needs dependency downloads.

**LM Studio is running, but the connection fails.**

Use its API base address, normally `http://127.0.0.1:1234/v1`, including `/v1`. Start the server, make a model available, and use **Test connection**. The app reports connection and endpoint errors with suggested next steps.

**The model finished, but no story appeared.**

A thinking model can spend its output allowance on reasoning before producing prose. Check the reported usage and increase **Generation settings > Maximum output tokens** if it reached the limit. Save the profile and start a new continuation. **Retry original inputs** deliberately keeps the old model settings and limit.

**Do I have to run every agent or random table?**

No. Randomness starts off, individual systems are optional, and prompts/agents can be disabled. Comparisons are deliberate additional requests.

**Can I use a character or Canon collection in more than one story?**

Yes. Stories select versions independently, and publishing an edit does not silently change existing stories.

**Is v0.5 a finished product?**

It is an early preview with the core writing workflows implemented. Expect further polish, compatibility work, and testing. Companion Mode, social feeds, built-in image generation, and automated backups are future ideas, not features of this release.

Found a problem or have a suggestion? [Open an issue](https://github.com/vantaloomin/prosperos-study/issues). Include what you tried, your provider/model, and any error message; leave out API keys and private story content.

<details>
<summary><strong>For developers</strong></summary>

The interface uses React, TypeScript, and Vite. The local backend uses Python, FastAPI, and SQLite.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm.cmd ci
```

For development, run the backend and Vite in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.main:create_app --factory --host 127.0.0.1 --port 8765
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Vite forwards API requests to the local backend. The production launcher serves the built interface and API together on port 8765.

Run the project checks with:

```powershell
powershell -ExecutionPolicy Bypass -File .\check.ps1
```

The checks cover backend tests, frontend model tests, Python/TypeScript linting, and the production build. Both complexity linters enforce a maximum of 10 per function. Tests use isolated data; keep the user's story database out of fixtures. The `ROLEPLAY_DB` environment variable selects an alternate database.

Source lives in `src/`, `server/`, `tests/`, and `scripts/`. Local data, agent files, planning archives, installed dependencies, and generated output are excluded from Git.

</details>

## License

[GNU Affero General Public License v3.0](LICENSE). Bundled fonts retain their respective licenses; see [font notices](public/fonts/NOTICE.md).
