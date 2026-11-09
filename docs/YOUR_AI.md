# Your AI

The dashboard reads the prospectus with code, no AI. The Ask view is the one place an AI comes
in: when you ask a question the code did not answer. It goes through the AI you choose, in one
of two ways, and the first needs no key at all.

Open any company, press **Ask** in the left rail, and scroll to **Your AI · two ways, pick one**.

## 1. An app you already pay for (recommended, no key)

If you pay for Claude or ChatGPT, you already have what you need:

| You pay for | The app that comes with it | Install line (from the maker's page, read 8 November 2026) |
|---|---|---|
| Claude Pro, Max, Team or Enterprise | Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash` (Windows: `irm https://claude.ai/install.ps1 \| iex`) |
| ChatGPT Plus, Pro, Business or Enterprise | Codex | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh` (Windows: `irm https://chatgpt.com/codex/install.ps1 \| iex`) |
| An xAI account | Grok Build | `curl -fsSL https://x.ai/cli/install.sh \| bash` (Windows: `irm https://x.ai/cli/install.ps1 \| iex`) |
| A Kimi account | Kimi Code | `curl -fsSL https://code.kimi.com/kimi-code/install.sh \| bash` |
| A Qwen account | Qwen Code | the standalone installer on [github.com/QwenLM/qwen-code](https://github.com/QwenLM/qwen-code) |
| A Cursor plan | Cursor (its command is `agent`) | `curl https://cursor.com/install -fsS \| bash` |
| Google Code Assist, or a Gemini key | Gemini CLI | `npm install -g @google/gemini-cli` (needs Node.js) |

You do not need to type any of this. The Ask view lists all seven apps whether or not they are on
your computer, and each row has the button you need next:

- **Install** opens a terminal window that runs the maker's own install line, the one above. The row shows the line before you press it. Most makers publish their installer as a line that downloads a script and runs it; if you would rather read it first, use **Maker's page** instead, where each maker also offers a download or a package manager (Homebrew, npm, winget).
- **Sign in** opens a terminal window running the app, whose sign-in continues in your browser.
  When it says you are in, close the window and press **Check again**.
- **Use it** makes that app the one that answers. The picker under the question box, **Who answers**,
  says the same thing and can be changed for any question.

A note on Gemini: Google's page says that since 18 June 2026 free personal accounts and Google AI
Pro or Ultra plans use a different app, Antigravity CLI, and that Gemini CLI is for Code Assist
plans and Gemini keys. A Google AI plan is better used through a key (way 2) for now.

### Is this allowed, and is my account safe

This program never sees a password, a key or a sign-in token. It runs the maker's own app on your
computer the way you would at a terminal, hands it your question on standard input and reads the
answer: Claude Code's print mode (`claude -p`), `codex exec`, Gemini CLI's `-p`, and the same flag
on Grok Build, Kimi Code, Qwen Code and Cursor. Each maker documents running its app this way.
Questions count against your own plan's usage. If a maker changes its rules, its rules win: switch
to way 2 and nothing else changes.

The brief each app gets says: answer from the record and the pages, run no commands, edit no
files, search nothing.

## 2. Your own key, or a free model on this computer

Pick a provider, paste a key, check the model name, press **Save**, then **Check**, which sends one
short line and shows what came back. Fourteen presets, the same as the GreekSoup desk:

Anthropic · OpenAI · Google (Gemini) · DeepSeek · Kimi (Moonshot) · MiniMax · Z.ai (GLM) ·
Alibaba (Qwen) · xAI (Grok) · Mistral · OpenRouter (many models, one key) · Ollama on this
computer · LM Studio on this computer · Any other endpoint.

Each preset links to the page where that provider hands out keys. Usage is billed by the
provider to your account. **Any other endpoint** takes the address, how it is spoken to (the
common way most labs and every local model speak, or Anthropic's own) and the model name, so a
provider not on the list still works.

### A free model on this computer

Ollama and LM Studio need no key and no internet: a question to them never leaves your computer.

1. Get Ollama from [ollama.com/download](https://ollama.com/download) and open it.
2. Download a model from [ollama.com/search](https://ollama.com/search): in a terminal,
   `ollama pull <model name>`.
3. In the Ask view pick **Ollama on this computer (free)**. The models already on your computer
   are listed under the model box; pick one, **Save**, **Check**.

Each question carries the dashboard's whole reading of the filing plus the matching pages, about
17,000 tokens. The program asks Ollama for a 32,768-token window so nothing is cut. A small model
on a small computer can be slow with that much text; a larger model reads it better.

## Where the key lives

In one file on your computer, `.ai.json` in the program folder. On a Mac or Linux it is readable by you only; on Windows it is as private as the folder you keep the program in (your Documents folder is private to your account). It is
listed in `.gitignore`, so it never goes into git. It is never written into `library/`, never put
into the page (the page only sees "saved, ends 1a2b"), never printed or logged, and goes only to
the provider you picked. **Remove the key** deletes it from the file. Switching to another
provider drops the old key.

The local server listens on this computer only (127.0.0.1), and it refuses a request from any
other website open in your browser, so no page elsewhere can save a key, open a terminal or spend
your plan.

## When the Ask view does not answer

- **"not installed"** next to an app: press Install, then Sign in.
- **"sign in first"**: press Sign in. If the app opens without a sign-in, type the line the
  window shows (`/login` in Claude Code, `/auth` in Gemini CLI and Qwen Code).
- **A key that fails Check**: the provider's own words come back (a wrong key, a model name it does
  not offer, an account with no credit). Fix the one it names.
- **Ollama or LM Studio "not answering"**: the app must be open with a model downloaded.
- **"Whichever is ready first"** tries the apps that say they are signed in, then your key, then
  any other app installed, and tells you each one's answer if none works.

Every answer carries its printed page. An AI can misread a figure: the Financials view holds what
the code read, and the page link opens the filing itself.
