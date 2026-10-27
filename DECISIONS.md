# Decisions

Every choice made for this project and why. Newest at the bottom.

## 2026-10-25

**Stack: FastAPI, PostgreSQL and React.**
PostgreSQL because the booking rules need real transactions and row locks. SQLite can't lock individual rows.
Why FastAPI: _(add your reason)_

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
