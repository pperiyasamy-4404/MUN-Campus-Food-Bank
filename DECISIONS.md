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

Step 2: the tables. The nine choices from tables.html, all agreed as suggested.

**Claude writes the database rules too, not only the tests.**
The plan was that Prakash writes the rules until Claude's tests pass. Prakash chose to have Claude write everything and to learn how it works afterwards. To keep it learnable, every rule has a readable name, a comment saying which rule from CONSTRAINTS.md it guards, and a test that tries to break it.

**Students and staff are two tables, not one accounts table. (A)**
They have different columns: students have an ID hash, staff have a username and a role. A booking can only point to a student, a list of volunteers can never show an ID hash, and deleting accounts after a year only touches students. The cost is that sessions and setup codes have two link columns, with a rule that exactly one is filled.

**Each slot keeps a count of its bookings, and a database rule keeps it within capacity. (B)**
The rule sits on the row a booking locks anyway, so the database itself refuses an extra booking, even when two students press Book at the same moment. A test shows this with two real connections. Counting the bookings each time would work in code, but a database rule can't count rows, so there would be no safety net.

**Holds are their own table, with the student as the primary key. (C)**
A hold has no items, code or status, so it doesn't belong in bookings. The primary key gives "one hold at a time" for free. Holds aren't in the slot's count. The code checks room for a hold with the slot locked, and if that ever had a bug, the worst case is a lost hold, never an overbooked slot.

**Each pickup day is its own row, with its own booking times. (D)**
The times are worked out from the settings when the day is made, then kept. Moving one day's times or closing one day changes one row, and changing the settings never moves a day students can already see.

**Dietary tags are their own table. (E)**
The coordinator can add a tag like vegan without a code change.

**"One booking per student per pickup day" is a database rule. (F)**
Rule S6 exists to stop cancelling and booking again as a way to change items. With a database rule, even buggy code can't allow it. Each booking stores its day as well as its slot, and a link on the pair (slot, day) keeps the two matching.

**The activity log is deleted after the retention period, like booking details. (G)**
Its rows say which student was served on which day, which is a booking detail we promised to delete.

**Only the tables steps 3 to 5 need are built now. (H)**
Packing, the counter and weekly totals get their tables in their own steps, once we know their details.

**Every rule has a test that tries to break it, and checks which rule refused. (I)**
Each rule has a name, like ck_slots_not_over_capacity. A test that only checked "something refused" could pass because some other rule fired, such as a missing value. Two deliberately wrong tests were run once to prove the tests can fail.

**The status of a booking always matches the times saved with it.**
Not in the original plan, added while building. A picked-up booking must have a pickup time and the volunteer who clicked (B3). A cancelled one needs a time and a reason, and a no-show a time. This stops half-finished updates from leaving a booking in a state nobody can explain.

**Names are unique ignoring capitals.**
"Sam" and "sam" would be the same volunteer, and "Oats" and "oats" the same item. Each is a unique index on the lowercase name.

**A raw ID number can never be saved, by a database rule.**
The ID hash must be exactly 64 characters of 0–9 and a–f, which is what an HMAC looks like. If some code ever passed the 9-digit number by mistake, the database refuses it (P2). Session tickets and wrong-password records follow the same rule.

**The app has its own database login, with no admin powers.**
It owns the working database and the test database, and can't create databases or change other people's. Its password is only in backend/.env, which is never committed. The postgres admin account is only used for setting up.

**The test database is emptied and rebuilt from the migrations on every test run.**
That way the tests always check the tables the migration really makes. Another test checks the migrations still match the table classes, and that they can be undone and run again. Each test's changes are undone afterwards, so tests can't affect each other.

**Pickup days and their slots are made by one function, written now.**
It was planned for the jobs script in step 8, but the sample data needs it already. It turns each Newfoundland clock time into an exact moment for that date, so the half hour and summer time are right. Tests check a winter day, a summer day, and the day the clocks go back. Windows has no time-zone list of its own, so the tzdata package provides it.

## 2026-11-04

A read-only page between step 2 and step 3: the pickup days, their slots and the food, straight from the database. The user chose it over going straight to accounts, to see the tables working first. How it works is in database-page.html.

**Two read-only addresses: `/api/pickup-days` and `/api/food`.**
The server sends plain data and React decides how it looks, so the booking screens in step 5 can use the same addresses. `/api/hello` and its test are gone: they only proved the two halves could talk, and these do that now.

**Every answer has a response model, listing exactly what goes out.**
A slot row has six columns, and only its start time and places left reach the browser. From step 3 on, this is what keeps a student's ID hash from ever leaving the server by accident (P10): a field has to be written down on purpose to be sent. Sending whole rows would send every column.

**Routes ask for their database session and the current time, instead of making them.**
`db: DB` and `now: Now` come from app/deps.py. Tests hand the route the test's own session, and can stop the clock at an exact moment, such as 5:00 pm on the Sunday booking opens. Reading the clock inside the route would make those tests depend on when they're run.

**Times go out in Newfoundland time with their offset, and the page shows them in Newfoundland time.**
The server sends `2026-11-09T15:30:00-03:30`, and the page formats it with the America/St_Johns time zone, so a laptop set to another time zone still shows 3:30 p.m. (T1). Dates with no time of day are formatted in UTC: formatted in Newfoundland time, midnight UTC is the evening before, and Monday would show as Sunday.

**"Today" is today in Newfoundland.**
Past pickup days are left out. At 11 pm on Thursday it's already Friday in UTC, so the server turns the moment into a Newfoundland date before comparing. A test checks exactly that.

**The server works out each day's booking status, with a function step 5 will reuse.**
Not open yet, open, over, or day closed. Booking is open from the open time exactly up to, but not including, the close time (S5): 5:00 pm Sunday is open, 12:00 pm Monday is over. The browser's clock can be wrong, and the server is what will refuse late bookings anyway, so one clock decides.

**Extras are sent with no count.**
Rule E2 says extras only show as "may be available", so the server sends `null` instead of the number, and the browser never has it. Hidden varieties are left out, and so is an item or category left with nothing to show. Bookable food with 0 left still shows, as "Out of stock".

**Each list is built from two database questions, not one per row.**
One question for all the varieties (or slots), one for all their tags, then Python groups them. Asking once per variety would be 18 questions for the sample food and grow with every variety added.

**No data-fetching library on the React side yet.**
A small `useServerData` function asks once and says loading, ready or failed. TypeScript only lets the page use the data when it's ready. A library like TanStack Query earns its place once screens change data and need refreshing, not for two read-only lists.

**Open question: exact stock counts or just "available"?**
The rules don't say what students see. This page shows "6 left" because it's for us. Exact counts help students choose but may cause a rush for the last one. A question for the food bank, and a one-line change either way.

## 2026-11-05

Step 3, accounts and login. The server side was started on 5 Nov and finished on 6 Nov, with the pages (see 6 Nov). How it all works is in accounts.html.

**A student stays logged in for 30 days after their last visit. Staff are logged out 12 hours after logging in.** (The user's choice.)
Places go fast at 5 pm, so a student shouldn't have to find their password on booking night. Each visit moves the 30 days on, at most once a day, so not every visit writes to the database. The counter laptop is shared, so a staff login never lasts overnight, however busy the shift.

**Passwords: argon2id, at least 8 characters, and no other rules.**
Rules like "one capital and one symbol" lead to Password1!, which is easy to guess. Length is what counts. A password can't be the student's ID number or the volunteer's username, and it can be at most 128 characters, so nobody can make the server hash a whole book. argon2 rather than bcrypt: it's OWASP's first choice, and it needs 64 MB of memory per guess, which makes guessing on graphics cards expensive. bcrypt also ignores everything after 72 bytes. If we make the settings stronger later, each hash is redone the next time its owner logs in.

**Setup codes look like K7QM-4TXP.**
8 characters from 31 letters and digits, with no 0, O, 1, I or L to misread from a slip of paper. That's about 850 billion codes, so guessing one in its 7 days at 5 tries per 15 minutes is hopeless. Only its keyed hash is saved. Each account has at most one code, and a new one replaces the old. The old password keeps working until the new code is used, so a code given by mistake locks nobody out. Using a code logs the account out everywhere else.

**Wrong tries: 5 every 15 minutes per ID number or username, then "Try again in N minutes". The account is never locked.**
A lock would let anyone lock a student out on purpose (P9). The wait is counted even for numbers with no account, and wrong setup codes count too. Whatever was wrong (no account, no password yet, the wrong password), the answer uses the same words. A wrong number also takes as long to answer as a wrong password, because it's checked against a made-up hash. So nothing tells anyone which numbers have accounts. The count is locked while it's checked, so 10 tries sent at the same moment still get only 5 checks. A test sends them on 10 connections.

**A browser that has logged in to an account before has its wrong tries counted separately (a "trusted device" cookie).**
Without this, anyone who knows a student's ID number could type 5 wrong passwords every 15 minutes and keep the real student waiting on booking night. The cookie is signed with the secret key, so nobody can make one for someone else's account. It lasts a year and doesn't log anyone in. The idea comes from OWASP.

**The sessions table keeps a SHA-256 of the login ticket, not a keyed hash.**
A ticket is 256 random bits. Nobody can list every possible ticket the way they could list every 9-digit ID number, so the key isn't needed.

**Switching off a volunteer keeps their account.**
They're logged out everywhere and their setup code is deleted, but the audit log can still say who did what (R4). There's no way to switch an account back on yet. A volunteer who comes back would need a new username, like "Sam B".

**The first coordinator is made by a script: `python -m app.first_coordinator Alex`.**
Before the first coordinator exists, nobody could be trusted with a web page for it. Run again with the same username, the script gives a new setup code, for a forgotten password. It never makes a second coordinator, and it won't turn a volunteer into one. In the audit log and on setup codes, an empty "who did it" means the setup script did.

**Two more database rules: password hashes must start with `$argon2id$`, and setup code hashes must look like a keyed hash.**
A typed password or a setup code can never be saved as it is, even if some code had a bug (P8). Migration 8be36cf65217 adds them, and lets the audit log name the staff account an action was done to.

## 2026-11-06

**Any staff member can give a student a setup code, the coordinator too.**
R2 lists it for volunteers, and R3 doesn't mention it for the coordinator. Otherwise a coordinator helping at the counter would need a second, volunteer account. Either way, the log says who gave the code. Making it volunteers only is a one-word change, if the food bank prefers that.

**Form errors say only where the problem is and what it is.**
FastAPI's own 422 answer repeats what was typed, so a mistyped ID number would come straight back in the error (P10). A test takes one ID number through every address that touches it, then searches every answer, every log line (SQL included) and every database row for it. Putting FastAPI's own error answer back makes the test fail, so we know it can catch a leak.

**No answer from the server is stored by the browser (`Cache-Control: no-store`).**
A setup code shown on screen must not come back when someone presses Back, or when the next person sits down at the laptop.

**Database errors show the SQL but not the values in it.**
An error that gets printed or logged could otherwise show a password hash or an ID hash (P3, P10).

**Tests pretend to use https.**
Login cookies are Secure, sent over https only, so a test client on plain http would never send them back.

**The pages use React Router.**
Each page gets its own web address: /login, /setup, /staff/login, /staff/setup, /counter and /volunteers. The Back button and links then work as people expect. Many more screens are coming, and React Router is the standard way to do this in React. Writing our own would cover today in 30 lines, but Back-button handling, links and "page not found" add up quickly.

**The page asks the server who is logged in, once, when it opens.**
The login cookie is HttpOnly, so the page can't read it. `GET /api/me` answers with the account or null, and every page shares that answer. Pages for staff send anyone else to the staff login page. That is only for looks: the server checks every request on its own.

**At the counter, the volunteer types the card number twice.**
A typo would make an account for someone else's number, and the student's code wouldn't work with their real one. The number is cleared from the screen as soon as the code is given, and "Done, clear the screen" removes the code before the next person steps up.

**New passwords are typed twice, with a "Show the password" box.**
A typo in a new password would mean another trip to the counter.

**The login and setup pages don't work while someone is logged in on that browser.**
They say "You're logged in" and offer Log out. Otherwise a student who set up their account on the counter laptop would replace the volunteer's login, and stay logged in on a shared laptop for 30 days. The page asks students to use their own phone.

**Open question: a stranger guessing can delay a reset on a new phone.**
Found while checking the pages in a browser. If someone is guessing a student's password, the student's usual phone still gets in, because of its trusted-device cookie. A new phone doesn't have one, so it shares the stranger's count and may wait up to 15 minutes to use a new setup code. It needs a stranger who knows the ID number and keeps guessing, so it should be rare. Counting setup code tries separately from password tries would only move the problem, so it's left as it is for now.

**The user's answers to the three open questions.**
- The coordinator can give students setup codes: yes, as built.
- A volunteer who comes back: better than a new username, see the next entry.
- A stranger delaying a reset on a new phone: left for now. It's listed under Known issues in CONSTRAINTS.md.

**A switched-off volunteer can be switched back on, with a new setup code.**
This replaces the 5 Nov note that a returning volunteer would need a new username. They keep the same account and username, so the log keeps everything they did under one name (R4). Their old password stops working, and they choose a new one with the code. They may have been away for months, and the old password could have been shared or forgotten since. A code handed over in person also shows it really is them. Switching on an account that is already on is refused, so it can never quietly undo a password the volunteer has chosen.

**Left for later steps:**
- The jobs script (step 8) will delete old wrong tries, logins that have run out and unused setup codes. Until then they stay in their tables, ignored.
- The setup script needs the food bank settings in the database, for the setup code lifetime. On a real install the settings have to go in first. For now, only the sample data adds them.

Step 4, items and stock, also on 6 Nov. How it works is in stock.html.

**A count is what's on the shelf. The server takes off what's booked but not packed yet.**
Booked items stay on the shelf until they're packed, but they're already promised. So 8 tins on the shelf with 2 booked leaves 6 to book. Packed items are in bags, not on the shelf, so they're left out either way. This makes a count right even while booking is open, so nobody has to remember when counting is safe. If fewer are on the shelf than were booked, stock stays at 0 (I4) and the volunteer is told how many bags will need a substitute.

**A count locks the variety's row first.**
A student booking the same food at the same moment waits until the count is saved, then takes their one off the new number. Without the lock, the count could overwrite the booking and promise the same tin twice. A test does exactly that on two connections. It fails without the lock (5 left instead of 4) and passes with it. The first version of that test passed both ways, because the count happened to equal the old stock, so it was changed.

**One way to change stock: count the shelf.**
There's no "+12 donated" button. One number to type, the number on the shelf, means the stock can't drift away from what's really there. A donation is shelved, then counted.

**Each variety remembers when it was last counted, and by whom.**
The stock page marks food not counted since the last pickup ended (that day's no-show time, when everything is settled). Volunteers can show only that food, to count what's needed before booking opens (I8). A database rule keeps the time and the person together.

**Any staff member can count, add food, choose tags, and hide or show food. Only the coordinator adds categories and tags, and fixes names.**
Rule I8 says volunteers or the coordinator update the items and stock counts, and donations arrive while volunteers are there. Categories and tags shape what students see and filter by, so one person keeps them tidy (R3). A typo in a name is fixed by the coordinator, and bookings show the new name because they point to the row.

**A new item always comes with its first variety.**
An item with no varieties would show students nothing. If there's only one kind, the variety can share the item's name.

**A count above 999 is refused.**
It catches a typo like 1000 for 10, which would let far too many students book.

**Names are unique ignoring capitals, decided by the database.**
The server tries to save and turns a refused name into "There's already an item called Pasta. Add a variety to it instead." Even two people adding Pasta at the same moment get that answer. A test found a bug here: the new name was set before the savepoint, so a refused rename broke the whole request. The name is now set inside the savepoint.

**Extras with none left aren't shown to students.**
Rule E2 shows today's extras as "may be available". An extra counted at 0 isn't available, so it's left out. On the staff page, extras show "10 left" instead of "can be booked", because they aren't booked online (E1).

**The message type the person sees moved to its own file, app/problems.py.**
Accounts and stock both need "something you can fix", like a taken name. The accounts code keeps its own kinds, like a wrong password, on top of it.

Step 5, slots, holds and booking, also on 6 Nov. How it works is in booking.html.

**Pressing Book is one transaction, as planned in tables.html (part 6).**
Lock the slot, check the hold, check the rules again, check the food, take a place, take the food off stock (lowest id first), save the booking, let go of the hold. If any step refuses, nothing is saved: the place, the food and the hold stay as they were, and the student's list stays on the page.

**Locks are always taken in the same order: the slot, then the student's hold or booking, then the food from the lowest id up.**
Booking, cancelling and holding all follow it, so two of them can never wait for each other forever (a deadlock). Three tests run two connections at the same moment: two students holding the last place, two students booking the last tin, and one student pressing Book twice. The first two were checked to fail with their lock taken out.

**Holds count against the places shown to everyone.**
A time being held by someone choosing food shows as taken, so nobody chooses it and then gets refused. A hold that has run out counts as free straight away, so nothing has to delete it on time.

**Holding the same time again adds no time.**
Otherwise a student could keep a time forever. Holding a different time lets go of the first one, so each student holds one at a time (S8).

**The countdown starts from the server's number of seconds left.**
A phone with its clock wrong would otherwise count down wrong. The server decides anyway: Book after the time is up is refused.

**Booking codes look like K3P: letter, digit, letter.**
No I, L or O, and no 0 or 1, so nothing is misheard at the counter. The pattern can't spell a word. That's 4,232 codes per day, and the database keeps each one unique within its day (P4).

**The pickup gap counts the latest of: the last pickup on the student's account, a picked-up booking, and (if the setting is on) a no-show.**
In calendar days in Newfoundland (F1). The account's date also covers walk-ins, which come in step 7, and outlives booking details deleted after the retention period.

**Every refusal says why, and what to do.**
Like "Booking for Monday, November 9 opens Sunday, November 8 at 5:00 p.m.", "You cancelled your booking for Monday, November 9, so it can't be booked again. You can book a later day." or "Sorry, Chunk chicken has just run out. Choose something else." The rules are checked before the hold and again at Book (S8).

**A held time that's gone answers 410, and a change while choosing answers 409.**
The page goes back to choosing a time on 410, and shows the page as it is now on 409. It decides by the number, not by reading the words, so rewording a message can't break it. Pressing Book twice is a 409 that names the booking's code.

**A student's addresses never take a booking id.**
/api/my-booking, /api/holds and /api/my-booking/cancel always mean the logged-in student's own. Nobody can see or cancel someone else's booking by changing a number in a request.

**The page only offers substitutes that are in stock.**
The server allows any shown food that isn't an extra or already on the list (U2). Offering one at 0 would be a substitute that can't fill a gap.

**Pickup days and food now include their ids.**
The booking page needs to say which time and which food. Ids aren't secret: the server checks every request.

## 2026-11-07

**A page that explains the whole project so far: project-so-far.html.** (The user asked for it.)
Read it first. It explains what we're building, how the pieces fit, what each step added, and links to the step pages.

Step 6, packing and substitutes. How it works is in packing.html.

**The refill rule (U4) is one function with no database: `refill()` in app/services/packing.py.**
It takes the booked food, what's missing and the substitutes, and says what happens to each substitute: use it, or skip it and why. With no database it can be read on its own, and the tests check it against the two examples in how-it-works.html, word for word.

**Nothing is saved until Packed. After each tap, the page asks the server for the plan.**
"None on the shelf" and "Found it" only change the page. After each tap, the page sends what the volunteer has found so far to `/plan`. The server works out the refill and the sticky note and saves nothing. So a wrong tap is undone by tapping again, and the rule lives in one place, on the server. Why not save each tap: undoing a saved "none on the shelf" would need the stock number it replaced, and nobody knows it any more.

**Pressing Packed is one transaction. It locks the booking, then the food from the lowest id up.**
It works the plan out again with the food locked. If the plan no longer matches what the page showed, Packed is refused with 409, and the page shows the new plan. That happens if another bag took the last rice, or someone counted the shelf. Two tests run on two connections at the same moment. In the first, two volunteers want the last rice. Without the food lock, both bags got it. In the second, Packed is pressed twice. Without the booking lock, it went through twice. Both tests fail with their lock taken out and pass with it in.

**"None on the shelf" sets that food's stock to 0 and marks it as ran out until someone counts it.**
The shelf has none, so nobody else can book it. The mark (`varieties.ran_out_at`) flags every bag still to pack that has this food (U7). The stock page also lists the food as needing a count. Counting the shelf clears the mark, because a count is what's really there. Packing doesn't change when the food was last counted.

**The flag reaches the queue within 30 seconds.**
The queue asks the server again every 30 seconds. When a volunteer opens a flagged bag, the food that ran out is already marked missing, so nobody searches the shelf for it again. If there is some after all, they tap Found it.

**Packing is allowed from the booking close time until the no-show time.**
K1 says volunteers pack after booking closes and before pickup starts. Before booking closes, students can still cancel, so the list isn't final, and packing is refused. After pickup starts, packing is still allowed. A bag that's late can then be packed while the student waits, because only a packed bag can be picked up (B2). At the no-show time, the day is over.

**Each substitute fills one gap, and gaps are filled in the order the volunteer found them.**
Any substitute can fill any gap (U4), so the order only decides which line of the sticky note says what. Filling in that order keeps the note's lines the same when another gap is found.

**"A second of the same item" means more of that item than the per-item limit.**
With the sample limit of 1, that's exactly what U4 says. Food that's missing isn't in the bag, so steel-cut oats can replace quick oats. That's the last line of example 2 in how-it-works.html.

**A hidden substitute is skipped, the same as one with none left.**
Hidden means the food bank stopped getting it.

**A substitute is skipped when its stock is 0, even if some are on the shelf.**
Stock counts only what no other bag is waiting for. The last tins on the shelf are promised to bags still to pack, so a substitute can't take them (U3).

**Each bag remembers who packed it, what was missing, and which substitute replaced what.**
Migration c250b0a6f9de adds `bookings.packed_by_staff_id`, `booking_items.missing`, `booking_substitutes.replaces_variety_id` and `varieties.ran_out_at`. It also adds three database rules:
- a packed bag always names who packed it
- `missing` is between 0 and the number booked
- a substitute can only replace food booked in the same booking (a foreign key on the pair)

So the sticky note can be shown again later, and the counter in step 7 can see what a bag is short.

**A gap nothing could fill goes on the note as "Black beans → choose at the counter".**
U6: the student chooses from the shelf at pickup. Step 7 records what they chose.

**Open questions for the user:**
- Packing is allowed until 6 pm, not only until pickup starts at 3:30, so a late bag can still be packed. Is that right?
- A packed bag can't go back to "to pack" (B2 has no such move). If someone presses Packed by mistake, nothing can undo it yet. Should a volunteer be able to undo Packed before pickup?

**Left for later steps:**
- The counter (step 7) shows a packed bag's sticky note, and records what a student chose for a gap (U6).
- A no-show (step 8) or a closed day (step 9) puts a packed bag's food back on the shelf. That means what was really in the bag: the booked food minus what was missing, plus the substitutes that went in.

**The user's answers to the two step 4 questions (7 Nov).**
- Volunteers can add categories and tags, and fix names, the same as the coordinator. This replaces the 6 Nov split. Volunteers are the ones at the shelf when a new kind of food arrives, so they shouldn't have to wait for the coordinator. Every stock address now needs a staff login, not a coordinator one. The stock page asks people to check the list first, so there's only one of each, and the database still refuses a name that's taken (ignoring capitals). R2 in CONSTRAINTS.md now says so.
- An extra with none left isn't shown to students. That's how it was built on 6 Nov, so nothing changes.

**The user's answers to four more questions (7 Nov).**
- **Packing goes on until the no-show time**, as built. K1 now says a bag that isn't packed when pickup starts can still be packed until 6 pm.
- **A volunteer can undo Packed on the wrong bag, until it's handed over.** This adds the move packed → booked to B2. Undo Packed puts the substitutes that went in back on the shelf (their stock goes up by one). The booked food stays promised, so its stock doesn't change. "Ran out" marks stay, because the shelf really had none. The undo is logged with who did it (`undid_packed`), like other fixes (B6). It's refused once the bag is picked up, after the no-show time, and on a bag that isn't packed. The page asks "Undo Packed on bag K3P?" first, because one tap shouldn't undo someone's work. It locks in the same order as Packed: the booking, then the food from the lowest id up.
- **A walk-in who hasn't reached the pickup gap is refused, with no override.** In the user's words, they can take only once in 28 days. W1 now says so, and the question is off the list for the food bank. Step 7 builds it.
- **Students see exact counts, like "6 left".** As built since 4 Nov. The question is off the list for the food bank.

Step 7, the counter, also on 7 Nov. How it works is in counter.html.

**The counter is open on a pickup day from the booking close time until the no-show time, for both lines.**
Bags are packed from 12 pm, and only a packed bag can be handed over, so handing over can't start earlier. Walk-ins take only what nobody booked (stock already leaves out booked food), so they could start any time. They use the same hours so the counter has one rule. At the no-show time the day is over. On any other day the page says when the next pickup day is.

**Handing over a bag: the code first, then the card, typed once.**
The student says their code, the volunteer finds the bag, then types the number on the MUN card. The server checks the card matches the booking (P5), with a constant-time comparison of the keyed hashes. A typo just doesn't match, so typing it once is enough here. The refusal never repeats the number (P10): "That card doesn't match bag K3P. Check the code and the card. Don't hand over the bag until they match."

**A walk-in's card is typed twice.**
There's no booking to compare it with, so a typo would record the walk-in under someone else's number and block them for 28 days. It's the same reason as at account setup.

**A first-time walk-in gets an account made for their card.**
CONSTRAINTS.md says a new student can take food as a walk-in on their first visit. The pickup gap needs an account to count from. The page suggests giving them a setup code if they want to book online.

**A walk-in who booked for today is sent to their bag instead.**
"They booked for today: bag K3P, at 3:40 p.m. Hand over that bag instead." Their food is already packed for them.

**W4: a walk-in with a booking for a later day is served only once the volunteer confirms the booking is cancelled.**
The page shows the booking and a checkbox, and Record stays greyed out until it's ticked. The booking's place and food go back for someone else, and its cancel reason is `walk_in`.

**When a bag is short, the student chooses from the shelf, up to the number of gaps, within the same limits.**
U6. The per-item limit counts what's already in the bag, so a student whose bag has quick oats can't choose steel-cut oats as well. They may choose fewer, or nothing.

**Extras are one of each extra item, and the database keeps this too.**
As planned in tables.html. The new `counter_items` table copies the item and is_extra onto each row, and two links on pairs, (variety, item) and (item, is_extra), make sure the copies are right. Then a unique rule on (booking, item) where is_extra holds "one bread" even if the code had a bug. Two new unique rules on varieties and items let those links exist.

**One table for everything handed over that wasn't in a packed bag: `counter_items`.**
Extras, a student's choice for a gap, and everything a walk-in takes. Each row belongs to one booking or one walk-in (a CHECK, like sessions). Why not three tables: they'd be the same columns three times. Walk-ins get their own table, `walk_ins`, because they have no slot and no code. A booking would need half its rules switched off to hold one.

**Locks now start with the student: the student, then the slot, then the hold or booking, then the food.**
A walk-in and an online booking for the same student at the same moment could both pass the pickup gap, because each reads the other's change only after it's saved. Book now locks the student first, as the counter does, so they take turns. A test runs them on two connections with different food, so only the student's lock can make Book wait. With the lock taken out, the booking went through and the test fails.

**A picked-up bag shows what was given at the counter too.**
Found in the browser check: after the handover, the bag listed only what was packed, not the rice chosen for the gap or the bread.

**The setup code page moved to /counter/setup-code.** /counter is now "Hand over a bag", and a small menu links the three counter pages.

**Left for later steps:**
- Fixing a mistake afterwards (B6: no-show ↔ picked up) comes with no-shows in step 8.
- Old walk-ins and counter items are deleted after the retention period with the bookings (P7, step 8).

**Open question for the user:** the counter is open 12 pm to 6 pm on pickup days, walk-ins included. Should walk-ins only be served during pickup hours, 3:30 to 5:30?

**Food is shown as cards, each with a photo of the item.** (The user's request, 7 Nov.)
One photo per item, shared by all its varieties: one photo of oats for quick oats and steel-cut oats. Students see the cards on the home page and when choosing food, and the counter's shelf uses the same cards. An item with no photo shows a simple drawing of a bowl.

**Photos are kept in the database, in their own table, `item_photos`.**
Any staff member can add, change or remove one on the Stock page, so the food bank can use its own photos. Why the database and not files on the server: one place to back up, and nothing extra to set up when it's hosted. Why a table of its own: reading the food list never loads the pictures. Database rules keep the type to JPEG, PNG or WebP and the size to 2 MB.

**A photo is checked by its first bytes, not by what the browser says it is.**
Only real JPEG, PNG and WebP pictures are kept. An SVG "picture" is refused, because it can carry a script.

**The browser shrinks a photo before sending it.**
Phone photos are often 3 to 5 MB. The Stock page redraws it at most 800 pixels wide as a JPEG. That also drops the hidden details phones add to photos, like where the photo was taken.

**A photo's address carries the time it was saved, like `/api/items/3/photo?v=1762700000`.**
So browsers may keep a photo for a year, and still fetch a new one the moment it changes. Every other `/api` answer is still never kept (`no-store`).

**The sample food has free photos.**
Found through Openverse and Wikimedia Commons, cropped to 640×480 and about 40 KB each. Who took each one is in `backend/app/sample_photos/CREDITS.md`. `python -m app.add_sample_photos` gives an older database its sample photos, without replacing any photo already chosen.

**Better photos for seven items, and canned food shows a can.** (The user's request, 7 Nov.)
New photos for oats (a pile of rolled oats), peanut butter (an open jar), cooking oil (bottles of oil), pasta (dry penne), rice (a bowl of dry rice), canned tuna (a can of chunk light tuna in water) and canned chicken. The first set was all public domain, and that set had no cans at all. So now some photos are CC BY: free to use as long as the photographer is credited, which `CREDITS.md` does. There is no free photo of a can of chicken anywhere we looked (Openverse, Wikimedia Commons), so canned chicken shows a plain can with its label out of view. A volunteer can take a photo of the real can and put it in on the Stock page.

## 2026-11-09

**Walk-ins are served only during pickup hours, 3:30 to 5:30 pm with the sample hours.** (The user's answer to the step 7 question.)
W3 in CONSTRAINTS.md now says so. Walk-ins start the moment pickup starts and stop the moment it ends, like booking opening and closing on the dot. Handing over a booked bag keeps its hours, 12 pm to 6 pm: a student who comes late, at 5:45, still gets their bag, because a booking waits until the no-show time. The Walk-in page says when walk-ins are served, and its Check button stays greyed out outside those hours.

**Each pickup day keeps its own pickup hours: `pickup_starts_at` and `pickup_ends_at` on `pickup_days`.**
They're copied from the weekly hours when the day is made, like the day's booking and no-show times. Why: changing the weekly hours never moves a day that's already made, with its slots. Why not read the weekly hours each time: the walk-in hours of a day already made would change, but its slots wouldn't. The migration gave the four days already in the working database the hours of their weekday.

**The database keeps a day's times in order: booking closes, pickup starts, pickup ends, no-shows.**
Three new rules. Booking must close before pickup starts, because bags are packed in between (K1). No-shows come after pickup ends, otherwise the last slots would be no-shows before their time came. The old rule "no-show after booking closes" follows from the new three, so it could never be the only rule broken, and it was dropped. For step 9: the coordinator's settings page has to check these too. If the settings and the weekly hours don't fit together, making a new day is refused.

**Step 8, the jobs: one script, every 15 minutes, that does whatever is due.** (Explained in jobs.html.)
`backend/app/jobs.py`, run with `python -m app.jobs`, or by Windows Task Scheduler through `backend/run_jobs.cmd`. In order: make pickup days, no-shows, delete old booking details after saving their totals, delete the old activity log, delete quiet accounts, tidy up. Each job looks at what's due now, not at when it last ran, so a missed run is caught up by the next one and a second run does nothing. Only one run at a time, kept by a PostgreSQL advisory lock. Each no-show, each day's deletion and each account deletion is its own short transaction, so nobody booking waits long. A failing job doesn't stop the others, and the script then ends with an error. It prints only numbers, and a database error is printed without its detail lines, which can show a row's values (P10).

**No-shows give back what was really in the bag.**
A bag never packed gives back what was booked. A packed bag gives back the booked food that was on the shelf plus the substitutes that went in. The no-show time saved is the day's, even if the job runs late. A closed day has no no-shows (B3 updated): closing a day will cancel its bookings in step 9. The job locks the student, then the booking, then the food, like the counter. A test runs Hand over at 5:59 against the job at 6:00 on two connections. With the booking lock taken out, the job tried to make a picked-up bag a no-show and the test failed.

**B6 fixes are their own page: Counter → Fix a pickup.**
It lists the days that are over and still have bags on record, with each day's no-shows and picked-up bags. Fixes start at the no-show time (B6 updated). To picked up: the bag's food comes off the stock count again (stopping at 0), the pickup gap counts from that day, and it's recorded as picked up by whoever fixed it, at the time of the fix. A bag never packed can't be fixed to picked up. To no-show: the bag's food goes back, and so does anything given with it at the counter, whose rows are deleted because it didn't happen. The pickup gap then counts from the last real pickup still on record. Both are logged (`fixed_no_show_to_picked_up`, `fixed_picked_up_to_no_show`). The page says when booking opens for the next pickup day, the time to fix by. Found in the browser check: after a fix, the "Are you sure?" box stayed open and asked the opposite question. Fixed.

**After the retention period, a day's totals are saved, then its details deleted, in one transaction (P7 updated).**
Two new tables, `weekly_totals` (picked up, walk-ins, no-shows, cancelled) and `weekly_item_totals` (how many of each item went out), by week starting on Monday. Why save them just before deleting, not every evening: until then they can be worked out from the details, and a B6 fix changes them by itself. Each day is either in the details or in the totals, never both, so step 9 can add the two together. Why by week: the coordinator sees weeks (P12). Why by item, not variety: what a food bank orders by. The day's row is locked first, so two runs can't count a day twice. Deleted: bookings with their food, substitutes and counter food, and walk-ins with theirs. Kept: the pickup day and its slots, which say nothing about anyone. Details are deleted once 90 days have passed in St. John's: Monday 9 November 2026's on Monday 8 February 2027. The activity log goes after the same 90 days (choice G).

**P13: an account with no pickup for a year is deleted, with its logins and setup codes (P13 updated).**
A year is 365 days, counted from the last pickup, or from when the account was made (in Newfoundland time) if it never had one. Kept while it has a booking or walk-in on record, or a setup code that hasn't run out: someone is using it. Each account is locked and checked again just before it's deleted, so a student pressing Book at that moment keeps their account. Log lines about them stay until the log's own 90 days, without saying who.

**Tidying up deletes what ran out:** logins, setup codes, wrong tries older than the 15-minute window, and holds once their pickup day is over (not as soon as they run out, so a student is still told "your time ran out").

**Pickup days are made two weeks ahead, from tomorrow.** A day already made is never touched, even a closed one, and today is never made because its booking would already have opened. Why two weeks: settings changes reach new days within two weeks, and the coordinator can close a day up to two weeks ahead. The first run on the working database made Thursday 19 and Monday 23 November.

**A known limit, listed in CONSTRAINTS.md:** a fix to no-show sets the pickup gap from the last pickup still on record. If the only earlier pickup is older than 90 days, the year rule counts from when the account was made, so the account can be deleted early. Rare.

**Open questions for the user:**
- Run the jobs every 15 minutes on the laptop with Windows Task Scheduler, against the working database?
- Two weeks ahead for pickup days, as built?

## 2026-11-10

**Step 9, the coordinator: four pages under one Coordinator menu.** (Explained in coordinator.html.)
Pickup days (`/coordinator`), Weekly totals, Settings, and Volunteers, which moved to `/coordinator/volunteers` (the old address sends you on). Only the coordinator can use them (R3), and the server checks every request. Every change is logged with who made it: `closed_day`, `reopened_day`, `moved_booking_times`, `changed_settings`. The activity log got a `pickup_day_id` column to say which day (migration d19b90ad39dc, applied to the working database).

**Closing a day (S7) cancels every booking still to come, packed or not, and puts back what was really in each bag.**
The same `packing.bag_contents()` as no-shows and walk-ins: a packed bag gives back the booked food that was on the shelf plus the substitutes that went in. Each place in its slot goes back. The reason is required, up to 200 characters, because students see it. Bags already handed over and walk-ins already served stay. A day can be closed until its no-show time. Why cancel packed bags: nobody can collect them, and cancelled, their food is counted for the next day. Why cancelled and not no-show: nobody failed to show, and a no-show can count toward the pickup gap.

**Closing locks the day, then all its slots, then its bookings, then the food.**
Book locks the slot before it looks at the day, so a student pressing Book while the day closes either finishes first, and is cancelled with the others, or waits and then sees the day is closed. Both cases are tests on two connections. With the slot lock taken out of closing, both failed (a booking stayed "booked" on a closed day). Book and Hold now read the day again after locking the slot (`_day_as_it_is_now`), so they never use an old copy. Why lock the slots and not make Book lock the day: Book already locks the slot, and every booking would pay for a lock needed a few times a year.

**A closed day can be opened again only if closing it cancelled no bookings, and it isn't over.** (Decision made by Claude, flagged to the user.)
A student can't book the same day twice (the one-booking-per-student-per-day rule, S6). Opened again, the students whose bookings were cancelled couldn't book it, while everyone else could take their places. Why not bring the bookings back: their food and times may be gone. Instead, the Close button says how many bookings it will cancel before anything happens.

**A date further ahead, up to a year, can be closed before its day is made**, like the Christmas break. The day is made from today's settings, then closed. The jobs never touch a made day, so it stays closed. A non-pickup weekday, today or the past is refused.

**Moving one day's booking times (S9) is allowed only until booking closes.**
After that, volunteers are packing, and opening booking again would let students cancel packed bags, which cancelling was never built for. The new close time must still be to come, and no later than the pickup start (K1). The page's date-and-time boxes send St. John's time with no time zone, and the server reads them that way (T1).

**The settings page saves everything at once, and checks the rules between settings with a sentence for each.**
Each box on its own: a whole number in a range, with its own message ("Enter a whole number from 5 to 120."); the top of each range catches slips like 2800 for 28. Between boxes: most of one item ≤ the item limit; details kept at least as long as the pickup gap; same-day booking opens before it closes; booking opens at most 13 days before (days are made 14 days ahead, so a day must exist before its booking opens); at least one pickup weekday; for every pickup weekday, booking closes by the time pickup starts, pickup ends by the no-show time, and the hours hold at least one slot. Why save at once: the rules are between settings, so changing two related boxes one at a time would be refused halfway. Day-making settings reach only days made from now on, as decided in step 8; the page lists the days already made.

**Weekly totals: the saved weeks plus the days still on record, newest first, with any number under 5 sent as "fewer than 5" (P12).**
A day counts once it's over, at its no-show time. Each day is in either the saved totals or its details, never both (step 8), so the two add up. Hidden on the server, so the real number never reaches the browser. 0 is hidden too: P12 says any number under 5, and showing 0 would make "fewer than 5" mean 1 to 4. Food is listed biggest first, then the small ones A to Z, so their order says nothing. Weeks with no bookings and no walk-ins aren't listed. Cancellations include those from closed days.

**Students whose day was closed are told on their booking page**, with the reason, until that day is over (`closed_day` in `/api/my-booking`). We still can't contact them any other way (known issue).

**Found by the tests and the browser check:** two settings messages ended in "p.m.." (fixed); after closing a day, its Close form stayed open (fixed: a form closes itself once its change is saved); the pickup hours boxes spread across a wide screen (fixed). 493 tests pass.

**Open questions for the user:**
- "Students per slot" and other day-making settings reach only new days, up to two weeks later. Fine, or should a change also reach days whose booking hasn't opened?
- A closed day that cancelled bookings stays closed. Agree?
- 0 shows as "fewer than 5". Agree?
- Still open from step 8: Windows Task Scheduler every 15 minutes, and two weeks ahead.

**Later on 10 November, the user's answers to the open questions:**
- **A closed day that cancelled bookings stays closed** (as built).
- **0 shows as 0 on Weekly totals; 1 to 4 show as "fewer than 5"** (P12 updated). Nobody can be picked out of nobody, and "0 no-shows" is useful to know. Built: `shown()` in routes/totals.py, with a test for 0, 1, 4, 5 and 12.
- **The jobs are run by hand.** No Windows Task Scheduler task.
- **Pickup days are made one week ahead, not two** (`DAYS_AHEAD` is 7). So settings changes reach new days within a week. Booking can open at most 6 days before a pickup day, so a day is always made before its booking opens. Dates further ahead can still be closed from the Pickup days page, which makes them first. Days already made in the working database (up to Monday 23 November) stay as they are.
- **Students per slot also changes on days already made, until their booking opens** (the user's answer to the last question). It's raised in a rush, when many students need food, and a week is too long to wait. Only days whose booking hasn't opened: on an open day, students may be holding or booking a time right then. A time never gets fewer places than are already booked in it (possible on a day whose opening was moved later, S9), so the database's "not over capacity" rule never refuses the save. The Settings page lists the days that changed. The other day-making settings still reach only new days. 497 tests pass.

**Accessibility check (10 November), the first item of "Before going live".**
How: axe (an automatic checker for WCAG 2.1 A and AA, the usual accessibility standard) ran on every page and stage, as a visitor, two students, a volunteer and the coordinator, in light and dark. A keyboard-only run booked a pickup from login to "Your booking" with Tab and Enter. Every page was loaded at 320 pixels wide (the same as 400% zoom on a laptop).
Found and fixed:
- **Text too faint (colour contrast)**, 8 kinds. Dark mode's muted grey is a little lighter (#a7b3c4), so it reads on grey chips too. The selected menu item uses a darker blue in light mode (`--blue-on-bg`). Food that's out of stock no longer fades its whole row with opacity: only its name goes grey, so "Out of stock" and the tags stay readable.
- **The booking countdown was a live region** (`role="status"`), so a screen reader would read out the time every second. Now the clock is quiet, and a hidden line speaks only at the start and at 5, 2 and 1 minutes left.
- **A screen reader wasn't told when a page opened, and every tab was called "Campus Food Bank".** New `PageHeading.tsx`: each page's heading names the tab ("Pickup days · Campus Food Bank") and takes the focus when the page or a booking stage opens, but only when nothing else has the focus, so it never jumps out of a box someone is typing in.
- **The Stock page scrolled sideways on a small phone.** The hidden photo pickers were full width: the rule for all boxes (width 100%) beat the "visually hidden" rule. That rule now always wins.
Not done: a real screen reader (NVDA) and real users. Automatic checks find only part of what matters.

**A one-command demo (10 November), for showing the project to someone.**
`backend/app/demo.py`, run with `python -m app.demo` from `backend/`, then open http://localhost:8000. It shows every page with something on it, without anyone having to book, pack and hand over first.
- **It uses the test database, never the working one.** The tests empty the test database on every run anyway, so nothing is lost, and no new database (which needs the PostgreSQL admin password) has to be made. It refuses to start if the two addresses are the same.
- **Its clock is set to the coming Thursday at 4 pm and runs on from there**, the same way the tests stop the clock (`get_now`). At 4 pm packing, the counter and walk-ins are all open. The story is made through the real rules (book, pack, hand over, no-show, move booking times), not by writing rows straight into tables, so the demo can't show a state the system itself could never reach.
- **Made-up students only**: ID numbers 202300001 to 202300006, one shared password, printed at the start. Alex is the coordinator, Sam a volunteer.
- **It serves the built website itself** (`frontend/dist`, made by `npm run build`), so one command is enough. Only the demo does this: where the real site is hosted isn't decided yet.
- Nothing runs the jobs script in the demo, so the 6 pm no-shows aren't marked unless it's run by hand.
Also: `app.sample_data` now makes the same week of pickup days the jobs script makes (it made 4 days, from before the "one week ahead" answer), and its filling part is shared with the demo.

## 2026-11-11

Found while walking through the system from an empty start (Alex, Sam and one student, Wednesday 4 pm to Thursday 6 pm). The two ideas below are Prakash's, from packing bag G6M.

**Each line on the packing page has a "Picked" button, and Packed waits until every line is Picked or Out of stock.**
The volunteer taps Picked as each thing goes in the bag, and the line turns green ("In the bag"). A substitute the plan puts in gets one too. Until every line is ticked, the bottom of the page says "2 lines still to tick, then press Packed" and Packed can't be pressed. If a substitute was Picked and the plan then stops needing it (the booked food turned up after all), its line says "Not needed now: take it out of the bag" with a Taken out button, and Packed waits for that too. Picked is only on the page and is never sent to the server, like the Out of stock taps before Packed.
Why: with only an Out of stock button, the page showed what was missing but not what was already in, so a volunteer packing several bags had to remember. Why Packed waits: the point is that nothing gets forgotten, and one tap per line is cheap next to a student going home without their rice. Why not saved on the server: it changes no stock and no record, so there is nothing to save or undo. (Claude chose "Packed waits"; Prakash can change it to just a reminder.)

**"None on the shelf" is now "Out of stock" on every page volunteers see.**
Also "Wasn't on the shelf" on a packed bag, the hint on a flagged bag ("A volunteer marked this out of stock at 12:26 p.m.") and the Stock page's ran-out line. Why: the shorter, everyday words. Only the words changed: the database and the addresses still say `not_on_shelf`, `missing` and `ran_out_at`, and the server's one message about it now says "out of stock". Older sections of this file keep the old words.

**Running the jobs on a timer is the hosting team's job, not the app's or the coordinator's.**
From what-could-go-wrong.html, problem 1: if nobody runs `python -m app.jobs`, no new pickup days are made, uncollected bags never become no-shows, and old data isn't deleted. Claude suggested a red "the jobs last ran 3 days ago" warning on the coordinator's page. Prakash said no: servers come with schedulers (cron, or a hosting service's scheduled jobs), and whoever runs the server schedules it and watches it. The coordinator runs the food bank, not the server. So the app's part is to make the jobs easy to schedule, which they already are (step 8): one command, safe to run twice at once, catches up after a missed run, error code 1 on failure. The handover notes (README) will say "run it every 15 minutes". The demo on Prakash's laptop keeps running it by hand (decided 10 November).

**Backups come from the cloud it will run on. No backup script of our own.**
From what-could-go-wrong.html, problem 2: nothing copies the database today. Prakash plans to run the system on a cloud, not on a laptop, and cloud databases make backups themselves, so a script of our own would be thrown away. The one thing their database backups don't cover is the secret key (`SECRET_KEY`): it isn't in the database. On the cloud it goes in the provider's secrets setting, kept apart from the database and its backups, because the key and the database together let someone work out the ID numbers. The demo has made-up data only, so it needs no backup.
