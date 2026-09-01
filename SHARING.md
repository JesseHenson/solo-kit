# What to send a prospect

## The link (best)

`claude://` links open Claude Desktop with a prompt already typed in the
composer; they press send. One click, nothing to copy.

    claude://claude.ai/new?q=I%27m%20installing%20a%20time%20tracking%20tool%20called%20time-log.%20It%20runs%20on%20my%20own%20computer%20%E2%80%94%20a%20timer%20and%20timesheets%20kept%20in%20a%20plain%20file%20I%20own%2C%20instead%20of%20a%20monthly%20subscription.%0A%0AWalk%20me%20through%20it%20one%20step%20at%20a%20time%2C%20and%20wait%20for%20me%20after%20each%20step%3A%0A%0A1.%20Give%20me%20this%20download%20link%20and%20tell%20me%20to%20click%20it%3A%20https%3A%2F%2Fgithub.com%2FJesseHenson%2Fsolo-kit%2Freleases%2Flatest%2Fdownload%2Ftime-log.mcpb%0A2.%20Tell%20me%20to%20open%20the%20file%20once%20it%27s%20downloaded.%20Claude%20Desktop%20will%20show%20an%20install%20dialog%20asking%20where%20to%20keep%20my%20time%20log%20%E2%80%94%20tell%20me%20the%20default%20is%20fine%2C%20and%20to%20click%20Install.%0A3.%20Ask%20me%20to%20confirm%20it%27s%20installed%2C%20and%20tell%20me%20to%20quit%20and%20reopen%20Claude%20Desktop%20if%20the%20time-log%20tools%20don%27t%20show%20up.%0A%0AOnce%20the%20time-log%20tools%20are%20connected%2C%20don%27t%20explain%20them%20to%20me.%20Just%20get%20me%20started%3A%20ask%20who%20I%20bill%20and%20whether%20I%20bill%20in%20whole%20increments%20%286%20or%2015%20minutes%29%20or%20in%20exact%20time%2C%20then%20either%20start%20my%20first%20timer%20or%20log%20time%20I%27ve%20already%20worked%20today.%20Keep%20it%20to%20one%20exchange.

Some mail clients strip non-`http` links. Where that happens, send the prompt
below as text instead.

## The prompt (same thing, pasteable)

> I'm installing a time tracking tool called time-log. It runs on my own
> computer — a timer and timesheets kept in a plain file I own, instead of a
> monthly subscription.
>
> Walk me through it one step at a time, and wait for me after each step:
>
> 1. Give me this download link and tell me to click it:
>    https://github.com/JesseHenson/solo-kit/releases/latest/download/time-log.mcpb
> 2. Tell me to open the file once it's downloaded. Claude Desktop will show an
>    install dialog asking where to keep my time log — tell me the default is
>    fine, and to click Install.
> 3. Ask me to confirm it's installed, and tell me to quit and reopen Claude
>    Desktop if the time-log tools don't show up.
>
> Once the time-log tools are connected, don't explain them to me. Just get me
> started: ask who I bill and whether I bill in whole increments (6 or 15
> minutes) or in exact time, then either start my first timer or log time I've
> already worked today. Keep it to one exchange.

## What it does and doesn't do

Claude reads the prompt, hands them the link, waits, and runs the onboarding
once the tools connect. It cannot download or install the file itself — Claude
Desktop has no shell, and installing a bundle goes through the app's own
dialog. That leaves the prospect two clicks: the download, and Install.

The onboarding fires either way. The server checks the log when it connects and
tells Claude when nothing has ever been logged, so someone who installs without
the prompt still gets walked through on their first message.

## Editing it

The prompt lives here and nowhere else. If you change it, regenerate the link:

    uv run python -c "import urllib.parse,sys; print('claude://claude.ai/new?q='+urllib.parse.quote(sys.stdin.read().strip(), safe=''))"
