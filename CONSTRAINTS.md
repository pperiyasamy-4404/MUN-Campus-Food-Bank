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
- **P5** Booking online doesn't prove eligibility. At pickup, the volunteer types the number from the student's MUN card and the system checks that it matches the booking.
- **P6** To book, view or cancel, the student logs in with their ID number and password.
- **P7** Booking details are deleted after the retention period. Only totals are kept, such as pickups per week and items given out.
- **P8** Passwords are stored only as a hash, never as text. The setup page asks students not to reuse their MUN password.
- **P9** Wrong passwords are limited per ID number, so nobody can guess a password by trying many. It slows tries down instead of locking the account, so nobody can lock a student out on purpose.
- **P10** The ID number never appears in web addresses, logs or error messages. A test checks this.
- **P11** The secret key is backed up somewhere safe, outside the database. Without it, no card can be matched to an account.
- **P12** The coordinator sees totals by week, and any number under 5 shows as "fewer than 5".
- **P13** Accounts with no pickup for a year are deleted.

### How often

- **F1** A pickup must be at least the pickup gap after the person's last pickup. Days are counted as calendar days in Newfoundland time, from the date of the last pickup to the date of the new slot. For example, after a pickup on Thursday 1 October at 5 pm, a slot on Thursday 29 October at 3:30 pm is allowed.
- **F2** A person has at most one upcoming booking.
- **F3** Cancellations, whether by the student or the food bank, don't count toward the pickup gap.

### Days and slots

- **S1** Slots exist only during pickup hours.
- **S2** A slot never goes over its capacity, even when many people book at once.
- **S5** Booking for a pickup day opens at the booking open time and closes at the booking close time. All of a day's slots open together. With the sample settings, Monday's slots can be booked from Sunday 5 pm until Monday 12 pm, and Thursday's from Wednesday 5 pm until Thursday 12 pm.
- **S6** Students can cancel until the booking close time. The cancelled slot can be booked by someone else straight away. A student who cancels can't book again for that same pickup day.
- **S7** The coordinator can close a day for a holiday, bad weather or the Christmas break. Every booking that day is cancelled, even if it's already packed, and those students can book again. Packed bags are unpacked so the shelf matches the stock count.
- **S8** The student picks a slot first and then chooses items. The slot is held for them for the slot hold time, with a countdown on screen. If they don't book in that time, the slot is free again straight away and they start over. A student can hold only one slot at a time. Before holding, the system checks the pickup gap, that they have no other upcoming booking, and that they didn't cancel for this day. It checks again when they press Book.
- **S9** The coordinator can move one day's booking open and close times, for example if the website was down, without changing the settings for other days.

### Items and stock

- **I1** An item is a kind of food, such as oats, pasta or canned chicken. Each item has one or more varieties, such as quick oats and steel-cut oats. Stock is counted per variety.
- **I2** Every variety has a category and dietary tags (vegetarian, halal, gluten-free, contains nuts).
- **I3** Each booking is for one person. It has up to the item limit, and at most the per-item maximum of each item, counting all its varieties together. For example, one canned chicken, even if there are several kinds and plenty in stock.
- **I4** Stock never goes below zero, even when two students take the last one at the same moment.
- **I5** Items are reserved when the booking is confirmed, not while the student is choosing.
- **I6** Cancelled bookings and no-shows return their items to stock.
- **I7** Once a booking is made, its items and substitutes can't be changed.
- **I8** Volunteers or the coordinator update the items and stock counts before each booking window opens, for example to add new donations. Existing bookings keep the items they booked.

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
- **U7** When a volunteer marks a variety as out of stock, every other booking that reserved it is flagged in the packing queue.
- **U8** Every swap is written on a sticky note on the bag, for example "Sunflower oil → rice".

### Packing

- **K1** Volunteers pack on the pickup day, after booking closes and before pickup starts. With the sample settings, between 12 pm and 3 pm.

### Walk-ins

- **W1** Walk-ins are recorded in the same system. The volunteer checks the student's card and enters the ID number, the system checks the pickup gap, the volunteer selects the items given on the Walk-in screen, and the pickup is done. This keeps the pickup gap fair (nobody can walk in one week and book online the next) and keeps the stock count right without recounting.
- **W3** Walk-ins are served in their own line, by their own volunteers, side by side with online pickups. They don't use slots.
- **W4** If a walk-in already has an upcoming booking, the volunteer cancels the booking and serves them now.

### Booking life

- **B1** A booking goes booked → packed → picked up, or ends as cancelled or no-show.
- **B2** Only these moves are allowed: booked → packed, packed → picked up, booked or packed → cancelled, booked or packed → no-show, and a fix between no-show and picked up (B6). For example, a cancelled booking can't be marked picked up.
- **B3** Volunteers mark a booking picked up when they hand over the bag. Only a volunteer's click counts: students can't mark their own pickup. A booking that isn't picked up by the no-show time becomes a no-show. The system does this by itself.
- **B4** Clicking "Book" twice creates only one booking.
- **B6** A volunteer can fix a mistake afterwards: change a no-show to picked up, or back. Every fix is logged with who made it. Fixes should be made before the next booking window opens, so the pickup gap and the stock count are right in time.

### Roles

- **R1** Students have an account, created at the counter. The volunteer checks the student's MUN card and the system gives a one-time setup code. On their own phone, right there or later, the student enters their ID number and the setup code and chooses a password. The volunteer never sees the password. A student who forgets their password gets a new setup code the same way. A setup code works once and expires after the setup code lifetime.
- **R2** Volunteers log in, see the packing queue for their shift, pack bags and apply substitutes, hand out booked bags, serve walk-ins, record extras given out, update stock counts, create student accounts and issue setup codes, and mark bookings packed or picked up.
- **R3** The coordinator logs in to manage items, stock, settings, closures and volunteer accounts, and sees totals only. The coordinator creates each volunteer account and gives a one-time setup code. The volunteer sets their own password with it, the same way students do. Volunteers log in with a username the coordinator gives them. A volunteer who also uses the food bank has a separate student account. The first coordinator account is created once, by a setup script, when the system is installed.
- **R4** Every volunteer and the coordinator has their own login. The system logs who created an account, issued a setup code, recorded a walk-in or marked a pickup. A student whose password was reset sees "password reset on DATE".

### Time

- **T1** Times are stored in UTC and shown in Newfoundland time (America/St_Johns: UTC−3:30, or UTC−2:30 in summer).

## Settings (sample values)

| Setting | Sample value |
|---|---|
| Pickup gap | 28 days |
| Pickup days and hours | Monday and Thursday, 3:30–5:30 pm |
| Booking opens | 5 pm the day before the pickup day |
| Booking closes (and cancelling) | 12 pm on the pickup day |
| Slot length | 10 minutes |
| Slot capacity | 1 student |
| Slot hold time | 10 minutes |
| Item limit | 13 per booking |
| Max of each item | 1 |
| Substitute limit | 5 per booking |
| Extras per student | 1 of each extra item |
| No-show time | 6 pm on the pickup day |
| No-shows count toward the pickup gap | No |
| Retention period | 90 days |
| Category limits inside the item limit | None |
| Setup code lifetime | 7 days |
| Wrong password tries | 5 per 15 minutes per ID number |

## Known issues

Problems we know about and accept for now.

- **The 5 pm rush.** Slots go to whoever is free when booking opens. Most of the university is done by 5 pm. We'll look again if MUN gets involved.
- **Password resets only at the counter.** A student who forgets their password on booking night can't book until they reach the counter. They can walk in and reset it there. A MUN-email reset would fix this if MUN ever gives access.
- **Closures can't reach students.** We have no contact details, so we can't tell students their day was closed. MUN email might fix this if MUN approves the project.
- **A volunteer could use a setup code first.** The volunteer sees the ID number and the setup code. We trust volunteers for now.
- **Internet down at the counter.** Volunteers can't check cards or the pickup gap. We'll plan for this later.
- **First visit in person.** A new student can't book online until they've been to the counter for an account. They can take food as a walk-in on that visit.

## Before going live

- A privacy review, and deciding where the system is hosted (where the data actually lives).
- Accessibility (screen readers, large text), and students without smartphones.

## Not in the prototype

- Checking MCP cards: the food bank does this its own way, to stop people also using other food banks
- Families: every booking is for one person
- Reminders of any kind (email, text or calendar)
- Picking up for someone else
- Students from other colleges
- Other campuses
- Other languages
- AI meal suggestions (to decide later)

## To ask the Campus Food Bank

- How is the 4-week rule checked today?
- We think nobody can pick up for someone else, and only MUN students are served. Is that right?
- When does new stock arrive each week?
- When do volunteers pack on pickup days? We assume 12–3 pm.
- How many students can the counter serve in 10 minutes?
- If a walk-in hasn't reached 28 days but needs food urgently, do you ever make an exception? If so, the Walk-in screen needs a logged override.
- When booking, should students see exact counts ("6 left") or only "available" and "out of stock"?
