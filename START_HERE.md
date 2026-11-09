# Start here: S-1 Prospectus Terminal in plain words

This page is for you if you have never installed a program from GitHub. No coding, about ten
minutes the first time, and after that it opens with a double-click.

**What you get:** a dashboard in your web browser that reads a company's IPO prospectus (its S-1
filing at the SEC) and lays out the numbers, the owners, the risks and what changed, every figure
with the page it came from. It runs on your own computer. Nothing you do is sent anywhere.

**Just want to look first?** You do not have to install anything to see what it does: the
screenshots in the [README](README.md) show the real thing.

## Step 1. Get Python (once)

Python is the free engine the program runs on. You install it once, like any other app.

**On a Mac**

1. Open [python.org/downloads](https://www.python.org/downloads/) and press the yellow
   **Download Python** button.
2. Open the file it downloads (in your Downloads folder) and click **Continue** and **Agree**
   until it says the installation was successful. It may ask for your Mac's password.

**On Windows**

1. Open [python.org/downloads](https://www.python.org/downloads/) and press the yellow
   **Download Python** button.
2. Open the file it downloads. **On its first screen, tick "Add python.exe to PATH"** at the
   bottom, then click **Install Now**. That tick box is the one step people miss.

Already have Python 3.10 or newer? Skip this step. Not sure? Skip it too: the starter in step 3
checks, and opens the download page for you if it is missing.

## Step 2. Download the program

1. Open the [latest release](https://github.com/greeksoup/s1-prospectus-terminal/releases/latest)
   and click **Source code (zip)** under Assets.
2. Unzip it: on a Mac, double-click the zip in Downloads; on Windows, right-click it and choose
   **Extract All**.
3. Move the folder somewhere you will find it again, such as Documents.

## Step 3. Double-click the starter

Open the folder and double-click the starter for your computer:

| Your computer | Double-click |
|---|---|
| Mac | `start-mac.command` |
| Windows | `start-windows.bat` |
| Linux | `start-linux.sh` (or run `./start-linux.sh` in a terminal) |

A window with text opens. The first time it sets the program up, which takes about a minute: it
makes the program its own private Python space inside the folder (nothing is installed anywhere
else on your computer), and draws the dashboards. Then your browser opens on the dashboard.

**Keep that text window open while you use it. Close it to stop the program.**

### The first time, your computer will warn you. This is expected.

Mac and Windows warn about any starter downloaded from the internet that does not come from an
app store. To open it anyway, once:

- **Mac:** if it says it cannot check the developer or that the file "cannot be opened", click
  **Done** or **OK**. Then right-click (or Control-click) `start-mac.command`, choose **Open**, and
  click **Open** again. If there is no Open button, go to **System Settings → Privacy & Security**,
  scroll down, and click **Open Anyway** next to the line about `start-mac.command`.
- **Windows:** if a blue box says **Windows protected your PC**, click **More info**, then
  **Run anyway**. If a box asks whether to run the file, click **Run**.

macOS and Windows word these boxes a little differently from version to version; the buttons are
the ones named above. You only do this once per download.

## Every time after that

Double-click the same starter. It checks whether a newer version is out. If one is, it says what
changed and asks once: press **Enter** to update. Your notes, the filings you downloaded and your
AI key stay as they are. Then the dashboard opens.

**Make it feel like an app:**

- **Mac:** drag `start-mac.command` onto the right side of your Dock.
- **Windows:** right-click `start-windows.bat`, choose **Send to → Desktop (create shortcut)**.

## Reading a company

The companies already read (SpaceX, Anthropic, Cerebras, Oura) open from the front page. To read
another one:

1. On the front page, press **+ Add a company**. A list drops down with every company that filed
   an S-1 or F-1 at the SEC in the last three weeks, newest first.
2. Click one, or type a company's name or ticker in the box to find any other.
3. The page shows how far it has got (downloading the filings, reading the pages). In a minute or
   two the company's dashboard opens by itself, and it stays on the front page from then on.

On any dashboard, the **Companies** button at the top switches to another company, and its last
line, **+ Add a company**, brings you back to the list.

Companies marked **blank check** are SPACs: they raise money first and buy a business later, so
their prospectus has no business numbers to read yet.

## Asking questions about a filing

The **Ask** view in the left rail lets you ask in plain English. It needs an AI, and it lists two
ways side by side:

- **You pay for Claude or ChatGPT?** Then you already have what you need: press **Install** next
  to Claude Code (with a Claude plan) or Codex (with a ChatGPT plan), then **Sign in**, which
  finishes in your browser. No key to copy.
- **Free, on your own computer:** install [Ollama](https://ollama.com/download), download a
  model in it, and pick **Ollama on this computer** in the Ask view.

The full guide: [docs/YOUR_AI.md](docs/YOUR_AI.md). Everything else in the dashboard works with
no AI at all.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Python 3.10 or newer is not on this computer" | Do step 1, then double-click the starter again. On Windows, if you just installed Python and still see this, run the Python installer again, choose **Modify**, and make sure **Add Python to environment variables** is ticked. |
| The window opens and closes at once (Windows) | Python is missing or was installed without the PATH tick: see the line above. |
| "The libraries did not install" | The first start needs the internet. Connect and double-click again. |
| "already running ... (opening it)" | It was still open from before; it opens that one. Close the other text window first if you want a fresh start. |
| The browser did not open | Open your browser yourself and go to http://127.0.0.1:8861 |
| Something else | [Open an issue](https://github.com/greeksoup/s1-prospectus-terminal/issues) and paste the text from the window. Nothing private is in it. |

## To remove it

Close the text window and delete the folder. That is all of it: the program never installed
anything outside its own folder. (Python stays, like any other app; remove it the usual way if
you want.)

---

S-1 Prospectus Terminal is free and open source, made by the team behind
[greeksoup.ai](https://greeksoup.ai), a web-based stock research platform. The IPO editions it grew
out of are in our newsletter, [Alpha with AI](https://ai.shikshannivesh.com). Information from
public filings, not investment advice.
