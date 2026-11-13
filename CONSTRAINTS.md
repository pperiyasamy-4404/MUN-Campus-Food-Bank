# Constraints

The rules the Campus Food Bank Booking System must follow.

This is a prototype with sample data. The real rules will be agreed with the Campus Food Bank later. There are two kinds of rule:

- **Fixed rules** are built into the code and the database. They don't change.
- **Settings** are numbers the coordinator can change without touching the code. The values below are samples.

Rules marked **(under review)** are waiting on a decision. See questions-and-issues.html. Rule numbers stay the same when a rule is removed, so some numbers are skipped.

## Fixed rules

### Identity and privacy

- **P1** One person has one identity: their MUN ID number. Only one kind of ID is accepted, so no one can have two identities.
- **P2** The ID number itself is never stored. Only a keyed hash (HMAC) is stored, and the secret key is kept outside the database.
- **P3** No student names, emails, phone numbers or MCP numbers are stored anywhere, including logs. Volunteers have a username, which can be a first name or a nickname.
- **P4** Volunteers never see the ID number or its hash. They see a booking code and the items.
- **P5** Booking online doesn't prove eligibility. At pickup, the volunteer types the number from the student's MUN card and the system checks that it matches the booking. A student without their code (a dead phone, say) can be found by the card number instead (decided 12 November).
- **P6** To book, view or cancel, the student logs in with their ID number and password.
- **P7** Booking details are deleted after the retention period. Only totals are kept, such as pickups per week and items given out. Each day's totals are saved just before its details are deleted.
- **P8** Passwords are stored only as a hash, never as text. The setup page asks students not to reuse their MUN password.
- **P9** Wrong passwords are limited per ID number, so nobody can guess a password by trying many. It slows tries down instead of locking the account, so nobody can lock a student out on purpose.
- **P10** The ID number never appears in web addresses, logs or error messages. A test checks this.
- **P11** The secret key is backed up somewhere safe, outside the database. Without it, no card can be matched to an account.
- **P12** The coordinator sees totals by week, and any number from 1 to 4 shows as "fewer than 5". 0 shows as 0. The server hides the small numbers, so the real number never reaches the browser.
- **P13** Accounts with no pickup for a year are deleted. An account that never had a pickup counts from when it was made. An account is kept while it has a booking or walk-in on record, or a setup code that hasn't run out.

### How often

- **F1** A pickup must be at least the pickup gap after the person's last pickup. Days are counted as calendar days in Newfoundland time, from the date of the last pickup to the date of the new slot. For example, with a 30-day gap, after a pickup on Thursday 1 October at 5 pm the gap ends on Saturday 31 October, so the first slot they can book is on Monday 2 November. With pickups on Mondays and Thursdays, that makes 31 or 32 days in practice. A pickup in the food bank's old system counts too: when giving a setup code or serving a walk-in, the volunteer must give its date from the old records, or tick "No pickup in the old system" (decided 12 November, for the first month after switching over). A no-show fixed to picked up cancels a later booking that is then too soon.
- **F2** A person has at most one upcoming booking.
- **F3** Cancellations, whether by the student or the food bank, don't count toward the pickup gap.

### Days and slots

- **S1** Slots exist only during pickup hours.
- **S2** A slot never goes over its capacity, even when many people book at once.
- **S5** Booking for a pickup day opens at the booking open time and closes at the booking close time. All of a day's slots open together. With the sample settings, Monday's slots can be booked from Sunday 5 pm until Monday 12 pm, and Thursday's from Wednesday 5 pm until Thursday 12 pm.
- **S6** Students can cancel until the booking close time. The cancelled slot can be booked by someone else straight away. A student who cancels can't book again for that same pickup day.
- **S7** The coordinator can close a day for a holiday, bad weather or the Christmas break, with a reason students see. Every booking that day is cancelled, even if it's already packed, and those students can book again. Packed bags are unpacked so the shelf matches the stock count. Bags already handed over and walk-ins already served stay recorded. A day can be closed until its no-show time, and a date up to a year ahead can be closed before its day is made. A closed day can be opened again only if closing it cancelled no bookings, because those students couldn't book that day again. Several days can be closed at once, from a first date to a last, with one reason, like "Christmas break, back on 7 January". Days already closed or over are left as they are (decided 12 November).
- **S8** The student picks a slot first and then chooses items. The slot is held for them for the slot hold time, with a countdown on screen. If they don't book in that time, the slot is free again straight away and they start over. A student can hold only one slot at a time. Before holding, the system checks the pickup gap, that they have no other upcoming booking, and that they didn't cancel for this day. It checks again when they press Book.
- **S9** The coordinator can move one day's booking open and close times, for example if the website was down, without changing the settings for other days. Only until booking closes, because packing starts then. Booking must still close by the time pickup starts.

### Items and stock

- **I1** An item is a kind of food, such as oats, pasta or canned chicken. Each item has one or more varieties, such as quick oats and steel-cut oats. Stock is kept per variety. The number is optional: most food has none and is just "In stock" or "Few left" (any volunteer can mark it). Only food worth sharing out exactly, like 6 jars from one donation, is counted. Food with no number can be booked by any number of students, and nothing is taken off or put back for it. When a packer taps Out of stock, it becomes 0 until someone checks the shelf (decided 12 November).
- **I2** Every variety has a category and dietary tags (vegetarian, halal, gluten-free, contains nuts).
- **I3** Each booking is for one person. It has up to the item limit, and at most the per-item maximum of each item, counting all its varieties together. For example, one canned chicken, even if there are several kinds and plenty in stock.
- **I4** Stock never goes below zero, even when two students take the last one at the same moment.
- **I5** Items are reserved when the booking is confirmed, not while the student is choosing.
- **I6** Cancelled bookings and no-shows return their items to stock. Food with no number has nothing to return.
- **I7** Once a booking is made, its items and substitutes can't be changed.
- **I8** Volunteers or the coordinator check the food before each booking window opens, for example to add new donations: food marked out of stock while packing, and food with a number that was counted before the last pickup. Existing bookings keep the items they booked.

### Extras

- **E1** Extras, such as eggs, bread and chips, don't count toward the item limit and aren't booked online.
- **E2** The app shows today's extras as "may be available". Students ask for them at pickup.
- **E3** A student gets at most one variety of each extra item. For example, one bread, even if there are several kinds.
- **E4** The volunteer records the extras given out. The pickup screen allows only one of each extra item.

### Substitutes

- **U1** Students choose a variety, such as sunflower oil. Any brand or size of sunflower oil counts as sunflower oil. A different variety, such as peanut oil, is never given in its place unless the student listed it as a substitute.
- **U2** Students can list up to the substitute limit, ranked in order. A substitute can be any variety that isn't an extra and isn't already in the order. For example rice, or vegetable oil in case the sunflower oil is gone.
- **U3** Substitutes aren't reserved. Reserving them would hold back more stock per student that usually isn't needed, and other students couldn't book it.
- **U4** When packing, missing varieties are refilled from the substitute list in rank order. A substitute is skipped if it's out of stock or would give the student a second of the same item. Refilling stops when the order is back to its original size.
- **U5** Volunteers never give anything the student didn't choose. This keeps allergens out: a student who picked gluten-free pasta never gets regular pasta.
- **U6** If the substitutes run out too, the volunteer asks the student at the counter to choose from what's on the shelf, within the same limits, and records what was given.
- **U7** When a volunteer marks a variety as out of stock, every other booking that reserved it is flagged in the packing queue. Each of those bags opens with it marked out of stock, but the volunteer still has to look once and tap "Still out of stock" or "Found it" before Packed, so one wrong tap doesn't spread to every bag (decided 12 November).
- **U8** Every swap is written on a sticky note on the bag, for example "Sunflower oil → rice".

### Packing

- **K1** Volunteers pack on the pickup day, after booking closes and before pickup starts. With the sample settings, between 12 pm and 3 pm. A bag that isn't packed by then can still be packed until the no-show time, while the student waits.
- **K2** When a volunteer opens a bag to pack it, the packing queue says "Sam is packing". Anyone else who opens it is warned first, and can still pack it anyway (Sam went home, say). Packed, or undoing Packed, clears it (decided 12 November).

### Walk-ins

- **W1** Walk-ins are recorded in the same system. The volunteer checks the student's card and enters the ID number, the system checks the pickup gap, the volunteer selects the items given on the Walk-in screen, and the pickup is done. A walk-in who hasn't reached the pickup gap is refused. There's no override. This keeps the pickup gap fair (nobody can walk in one week and book online the next) and keeps any stock number right without recounting.
- **W3** Walk-ins are served in their own line, by their own volunteers, side by side with online pickups. They don't use slots. They are served only during pickup hours (3:30 to 7:30 pm, the food bank's hours). A student with a booking can still collect their bag until the no-show time.
- **W4** If a walk-in already has an upcoming booking, the volunteer cancels the booking and serves them now.

### Booking life

- **B1** A booking goes booked → packed → picked up, or ends as cancelled or no-show.
- **B2** Only these moves are allowed: booked → packed, packed → booked (a volunteer undoing Packed on the wrong bag, before it's handed over, logged), packed → picked up, booked or packed → cancelled, booked or packed → no-show, and a fix between no-show and picked up (B6). For example, a cancelled booking can't be marked picked up.
- **B3** Volunteers mark a booking picked up when they hand over the bag. Only a volunteer's click counts: students can't mark their own pickup. A booking that isn't picked up by the no-show time becomes a no-show. The system does this by itself. A closed day has no no-shows.
- **B4** Clicking "Book" twice creates only one booking.
- **B6** A volunteer can fix a mistake afterwards: change a no-show to picked up, or back. Every fix is logged with who made it. Fixes should be made before the next booking window opens, so the pickup gap and the stock count are right in time. Fixes start once the day is over, at the no-show time. A bag that was never packed can't be fixed to picked up.

### Roles

- **R1** Students have an account, created at the counter. The volunteer checks the student's MUN card and the system gives a one-time setup code. On their own phone, right there or later, the student enters their ID number and the setup code and chooses a password. The volunteer never sees the password. A student who forgets their password gets a new setup code the same way. A setup code works once and expires after the setup code lifetime.
- **R2** Volunteers log in, see the packing queue for their shift, pack bags and apply substitutes, hand out booked bags, serve walk-ins, record extras given out, update stock counts, add and rename food, categories and tags, create student accounts and issue setup codes, and mark bookings packed or picked up.
- **R3** The coordinator logs in to manage items, stock, settings, closures and volunteer accounts, and sees totals only. The coordinator creates each volunteer account and gives a one-time setup code. The volunteer sets their own password with it, the same way students do. Volunteers log in with a username the coordinator gives them. A volunteer who also uses the food bank has a separate student account. The first coordinator account is created once, by a setup script, when the system is installed. There can be several coordinators: a coordinator makes a volunteer a coordinator, or a coordinator a volunteer, on the Staff page, and can give any other staff account a setup code or switch it off or on. Nobody can change their own account there, so there is always at least one coordinator (11 November).
- **R4** Every volunteer and coordinator has their own login. The system logs who created an account, issued a setup code, recorded a walk-in or marked a pickup. A student whose password was reset sees "password reset on DATE".

### Time

- **T1** Times are stored in UTC and shown in Newfoundland time (America/St_Johns: UTC−3:30, or UTC−2:30 in summer).

## Settings (sample values)

| Setting | Sample value |
|---|---|
| Pickup gap | 30 days |
| Pickup days and hours | Monday and Thursday, 3:30–7:30 pm (the food bank's real hours, 13 November) |
| Booking opens | 5 pm the day before the pickup day |
| Booking closes (and cancelling) | 12 pm on the pickup day |
| Slot length | 10 minutes |
| Slot capacity | 1 student |
| Slot hold time | 10 minutes |
| Item limit | 13 per booking |
| Max of each item | 1 |
| Substitute limit | 5 per booking |
| Extras per student | 1 of each extra item |
| No-show time | 8 pm on the pickup day (half an hour after pickup ends) |
| No-shows count toward the pickup gap | No |
| Retention period | 90 days |
| Category limits inside the item limit | None |
| Setup code lifetime | 7 days |
| Wrong password tries | 5 per 15 minutes per ID number |

Pickup days are made a week ahead, and each keeps the times it was made with. So a change to the booking times, pickup hours, slot length or no-show time reaches days made after it. Students per slot is the exception: it also changes on days already made, until their booking opens.

## Known issues

Problems we know about and accept for now.

- **The 5 pm rush.** Slots go to whoever is free when booking opens. Most of the university is done by 5 pm. We'll look again if MUN gets involved.
- **Password resets only at the counter.** A student who forgets their password on booking night can't book until they reach the counter. They can walk in and reset it there. A MUN-email reset would fix this if MUN ever gives access.
- **Closures can't reach students.** We have no contact details, so we can't tell students their day was closed. MUN email might fix this if MUN approves the project.
- **A volunteer could use a setup code first.** The volunteer sees the ID number and the setup code. We trust volunteers for now.
- **Internet down at the counter.** Volunteers can't check cards or the pickup gap. No paper plan: Prakash decided it isn't needed (13 November).
- **First visit in person.** A new student can't book online until they've been to the counter for an account. They can take food as a walk-in on that visit.
- **A stranger guessing can delay a reset on a new phone.** If someone keeps guessing a student's password, the student's usual phone still gets in. A phone that has never logged in to the account shares the stranger's wrong-try count, so it may wait up to 15 minutes to use a new setup code. It needs someone who knows the ID number and keeps guessing.
- **Food with a number can still be counted twice.** If a volunteer counts it after the no-show time (8 pm), before the jobs mark a bag as a no-show, the no-show adds the bag's food back on top of the count. Only food with a number, which is now a few foods at a time, and only in the minutes before the jobs run (they run every 15 minutes). Food with no number can't be counted twice (decided 12 November).
- **Still logged in on a shared computer.** A student login lasts 30 days. On a shared computer, the next person could see their booking if they don't press Log out. Left as it is: university computers log everyone out at the end of a session anyway (decided 12 November).
- **No "Delete my account" button.** A student account is deleted after a year with no pickup (P13), and not sooner. Left as it is: few students would ask (decided 12 November).
- **A fix to no-show can shorten the year rule.** Fixing a bag to no-show sets the pickup gap from the last pickup still on record. If the only earlier pickup is older than the retention period, its record is gone, and the year rule (P13) counts from when the account was made. Rare: the student would get a new account at the counter.

## Before going live

- Deciding where the system is hosted (where the data actually lives). Privacy rule (decided 12 November): only the coordinator sees sensitive data; volunteers see bag codes and food, never ID numbers (P4). Checked on 12 November: no volunteer page shows an ID number, a name, or a list of students.
- Whoever hosts it runs `python -m app.jobs` every 15 minutes with the server's own scheduler (like cron). It's safe to run twice at once, catches up after a missed run, and ends with error code 1 when a job fails, so their monitoring can alert them. This is the hosting team's job, not the coordinator's (decided 11 November).
- It will run on a cloud. The cloud's database backups are used, not our own backup script. The secret key (`SECRET_KEY`, now in `backend/.env`) isn't in the database, so it goes in the cloud's secrets setting, kept apart from the database and its backups. Losing it means no card matches any account; stealing it with the database means ID numbers can be worked out (decided 11 November).
- Accessibility: automatic checks (axe, WCAG 2.1 AA) pass on every page (light colours only since the MUN theme, 12 November), booking works with the keyboard only, and every page fits a 320-pixel screen (10 November). A real screen reader test was dropped (decided 12 November).

## Not in the prototype

- Booking for a student at the counter: a student without a smartphone books on any computer, or comes as a walk-in (decided 12 November)
- A student who lost their MUN card: no card, no food. They get a new card first (decided 12 November)
- Checking MCP cards: the food bank does this its own way, to stop people also using other food banks
- Families: every booking is for one person
- Reminders of any kind (email, text or calendar)
- Picking up for someone else
- Students from other colleges
- Other campuses
- Other languages
- AI meal suggestions (to decide later)

## To ask the Campus Food Bank

- How is the 30-day rule checked today?
- We think nobody can pick up for someone else, and only MUN students are served. Is that right?
- When does new stock arrive each week?
- When do volunteers pack on pickup days? We assume 12–3 pm.
- How many students can the counter serve in 10 minutes?
