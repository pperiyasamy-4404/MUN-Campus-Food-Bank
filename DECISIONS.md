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
