The restock picker crashes with IndexError whenever the warehouse stock is empty —
happens on every fresh install, before the first delivery is scanned. The docs say it
should return the NONE sentinel when there's nothing stocked. Everything else about
picking works.
