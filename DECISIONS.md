# Decisions

Every choice made for this project and why. Newest at the bottom.

## 2026-10-25

**Stack: FastAPI, PostgreSQL and React.**
PostgreSQL because the booking rules need real transactions and row locks. SQLite can't lock individual rows.
Why FastAPI: it checks incoming data for us with Pydantic, so there are fewer forgotten checks, and its free /docs page lets us try every web address before any screen exists. It only does the web part, with SQLAlchemy and Pydantic as separate pieces, so each one is easy to see and explain. Not Flask, which has neither the data checks nor the test page built in. Not Django, whose accounts are built around usernames and emails, and ours have neither. And Python, because it's easy to read and it's the main language for AI work.

**Build a prototype with sample items and sample rules first.**
The real items and rules aren't known yet. Every number that might change is a setting, so switching to the real rules means changing settings and the item list, not code.

**Identity is the MUN ID number, not the MCP number.**
International and out-of-province students don't have an MCP card. An MCP number is a health card number and too sensitive to hold. Accepting only one kind of ID stops one person from having two identities and getting food twice.

**Store only a keyed hash (HMAC) of the ID number.**
Student numbers are 9 digits, so a plain hash could be reversed by hashing all billion possible numbers. A keyed hash can't be reversed without the secret key, which is kept outside the database.

**The most important rules are enforced by the database itself.**
Slot capacity, the daily limit, stock never below zero, and one upcoming booking per person. These hold even if the application code has a bug.

**Always lock the day before the slot.**
A booking updates two counts: the day's and the slot's. Locking them in the same order every time stops two bookings from waiting on each other forever (a deadlock).

**Walk-ins are recorded in the same system.**
Otherwise the 28-day rule can be bypassed by mixing walk-ins and online bookings.

**Up to 13 items per order, not exactly 13.**
Students shouldn't be forced to take food they won't use.

**No-shows don't count toward the pickup gap.**
People miss pickups for many reasons, and a penalty hurts the people who need food most. It's a setting, so the food bank can change it.

**No contact details; reminders come from a calendar file.**
Students still get a reminder, and no email or phone number is stored.

**Items have varieties, and the limit is per item.**
One canned chicken, whatever the variety and however much is in stock. This follows the food bank's rule and stops a student taking several kinds of the same food. Stock is counted per variety because that's what is on the shelf.

**Extras: one of each extra item, chosen at pickup.**
Extras change too often to book online, but they still need a limit so they're shared fairly.

**Students rank up to 3 substitutes when booking.**
If an item has run out, the volunteer swaps in a substitute while packing, so nobody has to choose at the counter. This saves time for both students and volunteers. Three, so a student still goes home with a full order even if a few items are missing.

**Substitutes aren't reserved.**
Reserving them would hold back 3 more items per student that usually aren't needed, and other students couldn't book them. The cost: a substitute may also be gone by packing time.

**Never switch to a different variety unless the student listed it as a substitute.**
A student who picked sunflower oil may be avoiding peanut oil because of an allergy. Only the student knows, so only their own list is used.

**Refill missing items from the substitute list in rank order.**
Any substitute can fill any gap, as long as it's in stock and doesn't give the student a second of the same item. The result doesn't depend on which item went missing first, so it's simple for volunteers and easy to test.

## 2026-10-27

**Students have accounts, created at the counter.**
With only an ID number, anyone who knew a student's number could act as them: book in their name and block them, fill slots with made-up numbers, or find out whether they use the food bank. A password fixes that. Signing up online would still leave holes: someone could register a number before its owner does, made-up numbers could get accounts, and the sign-up page would have to say "this number already has an account", which leaks the same fact. Creating the account at the counter, after a volunteer checks the MUN card, means every account belongs to a real card holder. The student sets their own password on their own phone with a one-time setup code, so the volunteer never sees it. Forgotten passwords are reset the same way, so no email is needed.
The cost: a first-time student can't book online. Their first visit has to be in person.
If the system ever runs on MUN's site, students would log in with their MUN account instead.

**Forgotten passwords are reset only at the counter, with no recovery code.**
A recovery code would save some trips, but it's one more thing for students to keep, and anyone who found it could take over the account. A student who forgets their password can walk in and reset it on the same visit.

**Passwords are stored only as a hash.**
Many students will reuse their MUN password. If our database leaked, plain passwords would expose their MUN accounts too.

**Booking for a pickup day opens at 10 am, 2 days before.**
Monday's slots open Saturday and Thursday's open Tuesday. By Tuesday morning, Monday's pickups, walk-ins, substitutions and no-shows are all done, so the stock students see for Thursday is close to what's on the shelf. All of a day's slots open together, at one time that's easy to tell students.
The cost: with Sunday hours, Monday's booking opens before Sunday's pickup. Booked items are already taken out of stock, so only Sunday's walk-ins and substitutions are missing from the count.

## 2026-10-30

**Each booking is for one person.**
Families and household sizes are left out of the prototype, so every student gets the same item limit. This keeps the first version simple. Families can be added once we know how the food bank serves them.

**Pickups are Monday and Thursday, 3:30–5:30 pm, in 10-minute slots, one student per slot for now.**
These are the real pickup hours. The earlier sample hours (Sunday, and 7–8 pm) were wrong. One student per slot is a starting point. It's a setting, so it can go up to 2 if the slots fill up and the counter has time to spare.

**Booking is open from 5 pm the day before until 12 pm on the pickup day.**
This replaces "opens at 10 am, 2 days before". Opening at 5 pm lets students with daytime classes book. Opening the day before keeps the stock students see close to what's on the shelf. No pickups happen between 5 pm and noon the next day, so staying open overnight costs nothing in stock accuracy and helps students who are busy in the evening. Booking closes at 12 pm so volunteers have every order before they start packing.
The cost: places go to whoever is free at 5 pm. Most of the university is done by then.

**The student picks a slot first, then chooses items.**
The slot is held for them for 10 minutes while they choose, with a countdown on screen, so it can't be taken from under them. If time runs out, the slot is free again straight away and they start over. 10 minutes is enough to choose 13 items and 5 substitutes, but not long enough for an abandoned hold to block a slot for long at 5 pm.

**Items can't be changed after booking.**
Once a booking is made, its list is final, so volunteers pack exactly what was booked.

**Students can cancel until 12 pm on the pickup day.**
Booking is still open until then, so the slot and the items go straight back for someone else. After 12 pm the bags are being packed.
A student who cancels can't book again for that same pickup day. Otherwise cancelling and booking again would be a way to change items, which isn't allowed. They can still book a later pickup day, because cancellations don't count toward the pickup gap.

**Volunteers mark each bag picked up when they hand it over. A booking still not picked up at 6 pm becomes a no-show.**
This replaces "30 minutes after the slot ends", which would fall after closing for the last slots. 6 pm gives volunteers half an hour after closing to finish. The system marks no-shows by itself, so nobody has to remember. The items go back to stock. No-shows still don't count toward the pickup gap, so the student can book again. They're kept separate from cancellations so the food bank can see how many slots are wasted.

**Volunteers pack on the pickup day, from 12 pm to 3 pm.**
Packing starts only after booking closes, when every list is final.

**Up to 5 substitutes.**
More substitutes means fewer students have to choose at the counter. Substitutes aren't reserved, so a longer list doesn't hold back any stock.

**If every substitute is gone, the student chooses at the counter.**
This replaces "the order goes out smaller". It should be rare with 5 substitutes, and the student still gets a full order.

**Swaps are written on a sticky note on the bag.**
The student sees what changed when they collect the bag, so nothing needs to be shown online.

**The pickup gap is counted in calendar days, in Newfoundland time.**
Counting exact hours would refuse a student who picked up at 5 pm and comes back at 3:30 pm four weeks later. It would also shift by an hour when the clocks change.

**Closing a day cancels every booking, even packed ones.**
The students can book again, since cancellations don't count toward the pickup gap. Packed bags are unpacked so the shelf matches the stock count.

**Walk-ins have their own line.**
One set of volunteers hands out booked bags while another serves walk-ins, side by side. Walk-ins don't use slots. Most students are expected to move to booking online over time.

**No daily limit, and no places kept for walk-ins.**
The system only controls online bookings, and the slots already limit those to 12 a day. Walk-ins come as they come. The aim is to move everyone to booking online over time. This also means a booking only locks its slot, so the 25 Oct rule "always lock the day before the slot" is no longer needed.

**No calendar reminder.**
This replaces the calendar file from 25 Oct. Booking happens the evening before or the morning of the pickup, so a reminder isn't needed.

**Walk-ins are recorded on a Walk-in screen.**
The volunteer checks the card as usual, enters the ID number, and selects the items given. This keeps the pickup gap covering everyone (nobody can walk in Monday and book online for Thursday), and keeps the stock count right without anyone recounting. There's no limit on how many walk-ins come.

**A walk-in who already has a booking: the volunteer cancels the booking and serves them now.**
Otherwise they could get food twice: once now, once from the booking.

**Volunteers update stock counts before each booking window opens.**
New donations and corrections then show up before students book. Since walk-ins are recorded, the count stays right between updates.

**"Picked up" is its own step, done by the volunteer.**
We considered making the card check and "picked up" one step, so it can't be forgotten, but kept them separate.
Why: a matching card only proves who the student is. It doesn't mean they left with the bag. The bag may not be on the shelf (it was never packed), or the student may leave without it. If the card check counted as picked up, the record would show a pickup that never happened: the student's 28 days would start, and the items would stay off the stock count. The click happens when the bag actually leaves the counter, so the record matches what really happened. A forgotten click is covered another way: the no-show time is 6 pm, half an hour after closing, and a volunteer can fix a no-show afterwards (B6).

**Volunteers have their own logins, set up with a setup code like students.**
The coordinator creates the account and gives a one-time code, and the volunteer sets their own password, so the coordinator never sees it. Separate logins mean every action is logged under the volunteer who did it.

**Privacy and safety rules.**
The ID number never appears in web addresses, logs or error messages, and a test checks this: FastAPI repeats bad input back in its 422 errors, so a mistyped ID could end up in a log. The secret key is backed up outside the database, because if it's lost no card can be matched to an account again. Totals are shown by week with small numbers as "fewer than 5", so nobody can work out who used the food bank on a quiet day. Accounts with no pickup for a year are deleted, so we don't keep ID hashes of people who have left. The system logs who created accounts, issued setup codes, recorded walk-ins and marked pickups, and a student whose password was reset sees the date, so misuse can be noticed.

**MCP cards stay with the food bank.**
The food bank checks MCP cards its own way, to stop people also using other food banks. Our system doesn't store or check them: not every student has one, and our system can't see other food banks' records anyway.

**The coordinator can move one day's booking times.**
If the website is down on booking night, the coordinator can open booking later or keep it open longer for that day only.

**Only a volunteer's click counts as "picked up", and mistakes can be fixed.**
No-shows don't count toward the pickup gap, so a student would have a reason not to mark their own pickup. If the internet goes down at the counter, every bag handed out would become a no-show at 6 pm, so volunteers can change a no-show to picked up, or back. Every fix is logged with who made it, and should be made before the next booking window opens.

**A student holds one slot at a time, and the rules are checked before the hold.**
Otherwise one student could block several slots at 5 pm by opening tabs. A student who isn't allowed to book (pickup gap, an upcoming booking, or a cancellation that day) finds out before spending time choosing items, and doesn't block a slot for nothing. The rules are checked again at Book in case anything changed.

**Volunteers log in with a username, and keep a separate student account.**
Volunteers aren't logging in as students, so they need their own name for the log. A first name or nickname is enough. A volunteer who also uses the food bank has two accounts, which keeps the roles apart. The first coordinator account comes from a setup script when the system is installed, so there's never a public page for creating a coordinator.

**Privacy review, hosting and accessibility wait until we're close to going live.**
They don't change how the system works, only how and where it runs.

**Some problems are accepted as known issues for now.**
The 5 pm rush, password resets only at the counter, closures that can't reach students, a volunteer being able to use a setup code first, and the internet going down at the counter. Most of them can only be fixed with MUN's help (MUN email or MUN login), or by planning for things we can't predict yet. They're listed in CONSTRAINTS.md.

## 2026-11-01

The six tech choices from tech-and-stack.html, all agreed as suggested.

**TypeScript for the screens, not plain JavaScript.**
Mistakes like a misspelled field name get a red underline in the editor straight away. In plain JavaScript they only show up later, as a blank on the screen.

**Logins use sessions, kept in an HttpOnly, SameSite cookie, not tokens (JWT).**
A password reset at the counter has to log the other person out at once. With sessions that's one deleted row. A JWT keeps working until it runs out, unless the server keeps a list of cancelled tokens, which is a list of sessions again. HttpOnly stops code on the page from reading the cookie, and SameSite stops another website from sending requests as the student. Login services (Auth0, Firebase) would put student data with another company and expect email addresses, which we don't store.

**SQLAlchemy for everyday queries, with the key rules as real database rules and the booking SQL written so it can be seen.**
SQLAlchemy keeps everyday code short and sends values apart from the query, so it's safe from SQL injection. The booking transaction stays visible, so we can see the exact SQL and the row locks. Not SQLModel: locks and partial indexes need SQLAlchemy underneath anyway, and the table and the reply must stay apart so the ID hash is never sent back.

**PostgreSQL from the Windows installer for now, not Docker.**
On Windows 11 Home, Docker needs WSL 2 set up first, which is one more new thing to learn and fix. Docker can come in when we put the system online.

**Tests use pytest against a real PostgreSQL test database.**
The most important test is two students booking the last slot at the same moment. That checks the row lock and the database rules, which SQLite and a pretend database don't have, so the test would pass without testing anything real. The test database is separate, so tests can't touch the working data.

**One repository, with backend/ and frontend/ folders.**
A change that touches the table, the server and the screen goes into one commit. With two repositories the halves can get out of step, and anyone reading the GitHub sees only half the story in each.

**Correction to the 2026-10-25 entry on database rules.**
That entry lists "the daily limit" as one of the rules the database enforces. The daily limit was removed on 2026-10-30 (rule S3, see "No daily limit, and no places kept for walk-ins"), so the database rules are now slot capacity, stock never below zero, and one upcoming booking per person. The old entry is left as it was, so the history stays as it happened.

## 2026-11-02

**PostgreSQL 18, the newest version, installed on the laptop.**
A new project has no old data to keep, so there's no reason to start on an older version. It runs as a Windows service that starts with the laptop, on the usual port 5432.

**The database password lives outside the repository.**
The password for the main `postgres` account is a long random one, kept in PostgreSQL's own password file in the Windows user profile (`%APPDATA%\postgresql\pgpass.conf`). `psql` reads it from there, so it's never typed into the terminal, written in the code, or pushed to GitHub.

## 2026-11-03

Step 1 of the build: the backend/ and frontend/ folders, each saying hello.

**Python 3.14 for the server, in its own virtual environment inside backend/.**
Same reason as PostgreSQL 18: a new project has nothing old to stay compatible with. Python 3.14 gets security fixes until October 2030, while 3.11 stops in October 2027. Every library we plan to use (FastAPI, SQLAlchemy, Alembic, the PostgreSQL driver, password hashing) installed and ran on 3.14 before we switched. The libraries live in `backend/.venv`, not in the laptop's main Python, so this project's versions can't clash with another project's. The venv folder isn't committed. Anyone can rebuild it from `requirements.txt`.

**Exact library versions are written down.**
`requirements.txt` lists each Python library with its exact version (`fastapi==0.162.0`), and `package-lock.json` does the same for the screens. Another laptop or a server later gets the same versions, so nothing breaks because a library changed underneath us. Upgrades happen on purpose, in their own commit.

**Every server address starts with /api, and the React dev server passes those on to FastAPI.**
While we work, the browser only talks to one address, `localhost:5173`. Vite answers for the screens itself and hands anything under `/api` to FastAPI on port 8000. Because the browser sees one site, the SameSite login cookie is sent normally, and we need no CORS rules (the settings that let one site call another). If the screens called `localhost:8000` directly instead, the browser would count two sites, which needs CORS and a looser cookie. How the two halves share one address once the system is online gets decided when we put it online.

**The test client uses httpx2, not httpx.**
FastAPI's test client warned that using httpx with it is deprecated and asked for httpx2. Switching now keeps the test output clean, so a real warning later doesn't get lost.

**The first test runs without the database.**
It checks that `/api/hello` answers. The separate test database comes with the tables in step 2.

**The Vite template's demo page and README were removed.**
The hello page asks the server for its hello and shows the answer, which proves the two halves can talk. The template's README described Vite, not this project.
