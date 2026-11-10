# Start here: S-1 Prospectus Terminal in plain words

This page is for you if you have never installed a program from GitHub. No coding. You paste one
line, and a few minutes later the dashboard opens in your browser.

**What you get:** a dashboard in your web browser that reads a company's IPO prospectus (its S-1
filing at the SEC) and lays out the numbers, the owners, the risks and what changed, every figure
with the page it came from. Code does the reading and all the arithmetic, with no AI. It runs on
your own computer.

**Just want to look first?** The screenshots in the [README](README.md) show the real thing.

## Install with one line

### On a Mac

1. Press `Command` + `Space`, type **Terminal**, and press Enter. A window with text opens.
2. Copy this line, paste it into that window, and press Enter:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/greeksoup/s1-prospectus-terminal/main/install.sh | bash
   ```

3. If your Mac has no Python yet, the line downloads it from python.org, checks it is python.org's
   own file, and asks for your Mac's password once to install it. The letters do not show while
   you type the password; press Enter when done.

### On Windows

1. Press the Start button, type **PowerShell**, and press Enter. A blue or black window opens.
2. Copy this line, paste it into that window (right-click pastes), and press Enter:

   ```powershell
   irm https://raw.githubusercontent.com/greeksoup/s1-prospectus-terminal/main/install.ps1 | iex
   ```

3. If your PC has no Python yet, the line installs it with winget, Windows' own app installer. A
   box may ask you to approve it.

### On Linux

Open a terminal and paste the Mac line. If Python 3.10 or newer is missing, the line tells you the
one command that installs it (for example `sudo apt install python3 python3-venv`).

### What happens next

The line puts the program in a folder called `S1-Prospectus-Terminal` in your home folder, gives it
its own private Python space inside that folder (nothing is installed anywhere else), draws the
dashboards, and opens your browser on the front page. The first time takes a few minutes.

**Keep that text window open while you use it. Close it to stop the program.**

## Every time after that

Paste the same line again, or open the `S1-Prospectus-Terminal` folder and double-click the
starter for your computer:

| Your computer | Double-click |
|---|---|
| Mac | `start-mac.command` |
| Windows | `start-windows.bat` |
| Linux | `start-linux.sh` |

It checks whether a newer version is out. If one is, it says what changed and asks once: press
**Enter** to update. Your notes, the filings you downloaded and your AI key stay as they are.

**Make it feel like an app:**

- **Mac:** drag `start-mac.command` onto the right side of your Dock.
- **Windows:** right-click `start-windows.bat`, choose **Send to → Desktop (create shortcut)**.

## Reading a company

SpaceX, Anthropic, Cerebras and Oura are already read and open from the front page. To read
another one:

1. On the front page, press **+ Add a company**. A list drops down with every company that filed
   an S-1 or F-1 at the SEC in the last three weeks, newest first.
2. Click one, or type a company's name or ticker in the box to find any other.
3. The page shows how far it has got (downloading the filings, reading the pages). A minute or two
   later the company's dashboard opens by itself, and it stays on the front page from then on.

On any dashboard, the **Companies** button at the top switches to another company, and its last
line, **+ Add a company**, brings you back to the list.

Companies marked **blank check** are SPACs: they raise money first and buy a business later, so
their prospectus has no business numbers to read yet.

## The price box

Until a filing prints a price, the price screen shows "Not set". You can type in a market value you
read somewhere else, add where you read it, and the code works out the enterprise value and the
multiples from the filing's own cash, debt, revenue and cash flow. Your number is labelled as an
outside value, so it never gets mixed up with what the filing says. When a later filing prints the
price, the screen fills in by itself.

## Asking questions about a filing

The **Ask** view in the left rail lets you ask in plain English. It needs an AI, and it lists two
ways side by side:

- **You pay for Claude or ChatGPT?** Then you already have what you need: press **Install** next
  to Claude Code (with a Claude plan) or Codex (with a ChatGPT plan), then **Sign in**, which
  finishes in your browser. No key to copy.
- **Free, on your own computer:** install [Ollama](https://ollama.com/download), download a
  model in it, and pick **Ollama on this computer** in the Ask view.

The code sends the AI only the few pages that match your question, and every answer lists those
pages so you can check it. The full guide: [docs/YOUR_AI.md](docs/YOUR_AI.md). Everything else in
the dashboard works with no AI at all.

## Prefer not to paste a line?

You can install it by hand with a download and a double-click instead:

1. Get Python 3.10 or newer from [python.org/downloads](https://www.python.org/downloads/): press
   the yellow **Download Python** button and open the file. On Windows, **tick "Add python.exe to
   PATH"** on the installer's first screen, then click **Install Now**.
2. Open the [latest release](https://github.com/greeksoup/s1-prospectus-terminal/releases/latest)
   and click **Source code (zip)** under Assets. Unzip it (Mac: double-click it; Windows:
   right-click, **Extract All**) and move the folder somewhere you will find it again.
3. Double-click the starter for your computer (the table above).

The first time, your computer will warn you about a starter downloaded from the internet. This is
expected:

- **Mac:** if it says it cannot check the developer or that the file "cannot be opened", click
  **Done** or **OK**. Then right-click (or Control-click) `start-mac.command`, choose **Open**, and
  click **Open** again. If there is no Open button, go to **System Settings → Privacy & Security**,
  scroll down, and click **Open Anyway** next to the line about `start-mac.command`.
- **Windows:** if a blue box says **Windows protected your PC**, click **More info**, then
  **Run anyway**.

The one-line install does not trigger these warnings.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Python 3.10 or newer is needed first" (Linux) | Run the command it shows, then paste the install line again. |
| Windows: "Python ... could not be installed here" | Your browser opens python.org. Install Python with **Add python.exe to PATH** ticked, close PowerShell, open a new one and paste the line again. |
| "... already exists and is not this program" | A folder called `S1-Prospectus-Terminal` is already in your home folder. Move or rename it, then paste the line again. |
| "Could not reach GitHub" or "The download did not finish" | The install needs the internet. Connect and paste the line again. |
| "The libraries did not install" | Same: connect and start it again. |
| "already running ... (opening it)" | It was still open from before; it opens that one. |
| The browser did not open | Open your browser yourself and go to http://127.0.0.1:8861 |
| Something else | [Open an issue](https://github.com/greeksoup/s1-prospectus-terminal/issues) and paste the text from the window. Nothing private is in it. |

## To remove it

Close the text window and delete the `S1-Prospectus-Terminal` folder. That is all of it: the
program never installed anything outside its own folder. (Python stays, like any other app; remove
it the usual way if you want.)

---

S-1 Prospectus Terminal is free and open source, made by the team behind
[greeksoup.ai](https://greeksoup.ai), a web-based stock research platform. The IPO editions it grew
out of are in our newsletter, [Alpha with AI](https://ai.shikshannivesh.com). Information from
public filings, not investment advice.
