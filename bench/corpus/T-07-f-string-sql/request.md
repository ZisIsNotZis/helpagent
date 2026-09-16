The address book crashes whenever someone adds a contact whose name has an apostrophe
in it — think Irish names like O'Brien. It throws a database error straight out of
sqlite. Names without special characters work fine. Please make the store handle any
name we throw at it.
