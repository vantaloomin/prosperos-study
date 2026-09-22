<p align="center">
  <img src="public/brand/prosperos-study-banner.png" width="100%" alt="Prospero’s Study banner showing a branching manuscript in a candlelit writing room" />
</p>

# Prospero's Study

**Your story. Every possible telling.**

A local workspace for writing fiction with AI. Draft a scene, explore another ending, build a shared world, or step into a character's role. Keep the versions you love and decide what becomes part of the story.

**v0.9.0** · [Download](https://github.com/vantaloomin/prosperos-study/releases/tag/v0.9.0) · [What's new](releases/v0.9.0.md) · [User guide](docs/user-guide.md) · [Windows](#get-started-on-windows) / [macOS](#get-started-on-macos)

New in this release: automatic backups, reviewed project migration, weighted inspiration decks and standalone HTML publishing.

## A writing room for stories that keep growing

| What you want to do | How the Study helps |
| --- | --- |
| Write, direct or roleplay | Draft freely, plan a scene, or participate as a character. Review generated prose and choose what to keep. |
| Try another ending | Branch from earlier passages, compare tellings and keep your favorite versions. |
| Build a shared world | Reuse versioned Characters and Canon across stories, with explicit updates. |
| Keep your voice | Save writing styles, examples and reusable recipes. |
| Keep earlier events within reach | Retrieve relevant prose and review plans with optional long-story memory. |
| Work with a Companion | Brainstorm or revise selected text with the sidebar Collaborator, including a Pop Out window. |
| Find a new direction | Create weighted inspiration decks, inspect the odds and deliberately draw a prompt. |
| Assemble and protect your work | Organize a Book, export DOCX/EPUB/HTML, and save manual or scheduled backups. |

Start with **Write a story**, **Build a scene**, or **Roleplay**. Choose **Skip setup** to begin immediately. Manual writing needs no model, and optional agents and randomness stay under your control.

## Get started on Windows

1. Download and extract the [v0.9.0 source ZIP](https://github.com/vantaloomin/prosperos-study/releases/download/v0.9.0/prosperos-study-v0.9.0-source.zip).
2. Run [install.bat](install.bat) to install dependencies and build the interface.
3. Run [launch.bat](launch.bat). The Study opens at `http://127.0.0.1:8765`.

Requires **Python 3.12+**, **Node.js 22.12+** and internet access for installation. The installer can obtain missing runtimes through WinGet; otherwise install them yourself. Keep the launcher terminal open while writing and press **Ctrl+C** to stop.

## Get started on macOS

Extract the same source ZIP, open Terminal in its folder, and run:

```bash
bash install.sh
bash launch.sh
```

The same runtime requirements apply. The installer can use an existing Homebrew installation for missing runtimes. Native macOS installation and Keychain access still need a smoke test. See [detailed setup and launch options](docs/user-guide.md#get-started-on-macos).

**Updating:** save a workspace backup, stop the app, replace the application source while keeping your `data/` folder, then rerun the installer. Keep a pre-update backup if you may need to downgrade. This is a source release; checksums and a file manifest are on the [release page](https://github.com/vantaloomin/prosperos-study/releases/tag/v0.9.0).

## Bring your own writing partner

Use **Settings > Models** to add a connection, test it and choose a **Primary Writer**. Supported connections include OpenAI, Anthropic, Gemini, OpenRouter, Codex/ChatGPT through the signed-in Codex CLI, LM Studio, Kobold and compatible APIs. Different roles can use different models.

Models and API credits are separate from the app. You can use a local model or write entirely by hand. See [connection requirements and generation settings](docs/user-guide.md#bring-your-own-writing-partner).

## Your work stays yours

Stories and Library material live in the local `data/` folder. Cloud generation sends the required context to your selected provider; API keys are stored separately in the operating system's credential vault.

**Settings > Backups & recovery** offers manual backups, opt-in automatic scheduling and deliberate restore as new Stories. Scheduled copies require the server to be running. Private archives contain your writing and are not encrypted. [Backup and recovery details](docs/user-guide.md#your-work-stays-yours).

## Guides

<a id="keep-the-past-and-what-is-still-to-come"></a>
<a id="write-in-your-own-style"></a>

- [User guide](docs/user-guide.md) — writing, tellings, styles, recipes, Companion, setup and troubleshooting.
- [Story memory and model-call costs](docs/user-guide.md#keep-the-past-and-what-is-still-to-come) · [Writing styles](docs/user-guide.md#write-in-your-own-style) · [Illustrated agent guides](docs/user-guide.md#agents-and-long-memory-illustrated).
- [Import compatibility](migration-compatibility.md) · [Inspiration decks and collections](inspiration-compatibility.md) · [HTML publishing](html-publishing.md).
- [Release notes](releases/v0.9.0.md) · [Changelog](CHANGELOG.md) · [Validation evidence](v090-validation.md).
- [Development setup and checks](docs/development.md).

## Questions

This is an early preview with the core writing workflows implemented. Models can miss instructions or continuity details; review what you keep. For connection issues and common questions, see [troubleshooting](docs/user-guide.md#questions). To report a problem, [open an issue](https://github.com/vantaloomin/prosperos-study/issues) with the steps and error message, leaving out API keys and private story text.

## License

[GNU Affero General Public License v3.0](LICENSE). Bundled fonts retain their respective licenses; see [font notices](public/fonts/NOTICE.md).
