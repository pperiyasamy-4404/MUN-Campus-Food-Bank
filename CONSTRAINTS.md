# Constraints

The rules the Campus Food Bank Booking System must follow.

This is a prototype with sample data. The real rules will be agreed with the Campus Food Bank later. There are two kinds of rule:

- **Fixed rules** are built into the code and the database. They don't change.
- **Settings** are numbers the coordinator can change without touching the code. The values below are samples.

## Fixed rules

### Identity and privacy

- **P1** One person has one identity: their MUN ID number. Only one kind of ID is accepted, so no one can have two identities.
- **P2** The ID number itself is never stored. Only a keyed hash (HMAC) is stored, and the secret key is kept outside the database.
- **P3** No names, emails, phone numbers or MCP numbers are stored anywhere, including logs.
- **P4** Volunteers never see the ID number or its hash. They see a booking code and the items.
- **P5** Booking online doesn't prove eligibility. At pickup, the volunteer types the number from the student's MUN card and the system checks that it matches the booking.
- **P6** To view, change or cancel a booking, the student needs their ID number and the booking code.
- **P7** Booking details are deleted after the retention period. Only totals are kept, such as pickups per week and items given out.

### How often

- **F1** A pickup must be at least the pickup gap after the person's last pickup.
- **F2** A person has at most one upcoming booking.
- **F3** Cancellations, whether by the student or the food bank, don't count toward the pickup gap.

### Days and slots

- **S1** Slots exist only during opening hours.
- **S2** A slot never goes over its capacity, even when many people book at once.
- **S3** A day never goes over its daily limit. A booking must fit both the slot and the day.
- **S4** Online bookings stop at the daily limit minus the places kept for walk-ins.
- **S5** Students can book only within the booking window and before the booking cutoff.
- **S6** Students can cancel until the cancel cutoff.
- **S7** The coordinator can close a day for a holiday, bad weather or the Christmas break. Bookings that day are cancelled, and those students can book again.

### Items and stock

- **I1** An item is a kind of food, such as oats, pasta or canned chicken. Each item has one or more varieties, such as quick oats and steel-cut oats. Stock is counted per variety.
- **I2** Every variety has a category and dietary tags (vegetarian, halal, gluten-free, contains nuts).
- **I3** Each order has up to the item limit for the household size, and at most the per-item maximum of each item, counting all its varieties together. For example, one canned chicken, even if there are several kinds and plenty in stock.
- **I4** Stock never goes below zero, even when two students take the last one at the same moment.
- **I5** Items are reserved when the booking is confirmed, not while the student is browsing.
- **I6** Cancelled bookings and no-shows return their items to stock.
- **I7** Students can change their items and substitutes until the booking cutoff and keep their slot.
- **I8** The coordinator updates the items each week. Existing bookings keep the items they booked.

### Extras

- **E1** Extras, such as eggs, bread and chips, don't count toward the item limit and aren't booked online.
- **E2** The app shows today's extras as "may be available". Students ask for them at pickup.
- **E3** A student gets at most one variety of each extra item. For example, one bread, even if there are several kinds.
- **E4** The volunteer records the extras given out. The pickup screen allows only one of each extra item.

### Substitutes

- **U1** Students choose a variety, such as sunflower oil. Any brand or size of sunflower oil counts as sunflower oil. A different variety, such as peanut oil, is never given in its place unless the student listed it as a substitute.
- **U2** Students can list up to the substitute limit, ranked first, second and third. A substitute can be any variety that isn't an extra and isn't already in the order. For example rice, or vegetable oil in case the sunflower oil is gone.
- **U3** Substitutes aren't reserved. Reserving them would hold back more stock per student that usually isn't needed, and other students couldn't book it.
- **U4** When packing, missing varieties are refilled from the substitute list in rank order. A substitute is skipped if it's out of stock or would give the student a second of the same item. Refilling stops when the order is back to its original size.
- **U5** Volunteers never give anything the student didn't choose. This keeps allergens out: a student who picked gluten-free pasta never gets regular pasta.
- **U6** If the substitutes run out too, the order goes out smaller.
- **U7** When a volunteer marks a variety as out of stock, every other booking that reserved it is flagged in the packing queue.

### Walk-ins

- **W1** Walk-ins are recorded in the same system. The volunteer enters the ID number, the system checks the pickup gap, the volunteer records the items, and the pickup is done. Without this, someone could walk in one week and book online the next.
- **W2** Walk-ins count toward the daily limit.

### Booking life

- **B1** A booking goes booked → packed → picked up, or ends as cancelled or no-show.
- **B2** Only those moves are allowed. For example, a cancelled booking can't be marked picked up.
- **B3** A booking that isn't picked up by the no-show time becomes a no-show.
- **B4** Clicking "Book" twice creates only one booking.
- **B5** After booking, the student can download a calendar file as a reminder. No contact details are needed.

### Roles

- **R1** Students have no account. They use their ID number and booking code.
- **R2** Volunteers log in, see the queue for their shift, apply substitutes, record walk-ins and extras given out, and mark bookings packed, picked up or no-show.
- **R3** The coordinator logs in to manage items, stock, settings, closures and volunteer accounts, and sees totals only.

### Time

- **T1** Times are stored in UTC and shown in Newfoundland time (America/St_Johns: UTC−3:30, or UTC−2:30 in summer).

## Settings (sample values)

| Setting | Sample value |
|---|---|
| Pickup gap | 28 days |
| Booking window | 7 days ahead |
| Booking cutoff | 3 hours before the slot |
| Cancel cutoff | 3 hours before the slot |
| Opening hours | Sun 3–5 pm; Mon and Thu 3:30–5:30 pm and 7–8 pm |
| Slot length | 15 minutes |
| Slot capacity | 4 people |
| Daily limit | 40 people |
| Places kept for walk-ins | 10 per day |
| Substitute limit | 3 per booking |
| Extras per student | 1 of each extra item |
| No-show time | 30 minutes after the slot ends |
| No-shows count toward the pickup gap | No |
| Retention period | 90 days |
| Category limits inside the item limit | None |

### Household sizes (placeholder)

| Household | Item limit | Max of each item |
|---|---|---|
| 1 person | 13 | 1 |
| 2–3 people | 18 | 1 |
| 4 or more | 23 | 1 |

Household size is self-reported. No names or details of family members are collected.

**Known gap:** two adults in the same household can each book with their own MUN ID. The system can't detect this without collecting addresses, which would break the privacy rules.

## Not in the prototype

- Reminders by email or text
- Picking up for someone else
- Students from other colleges
- Other campuses
- Other languages
- AI meal suggestions (to decide later)

## To ask the Campus Food Bank

- How do household sizes work? Do families get more items?
- How is the 4-week rule checked today?
- How do you handle two people from the same household?
- Can someone pick up for another person?
- How are students from other colleges served?
