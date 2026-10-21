# mail/ — the shape of a message here

One file per message, flat, dated in the name: `YYYY-MM-DD-<slug>.md`. Four header lines,
then the body, then the effort. The reader must know what it is and what answering costs
without opening a second file.

```
kind:    resource | cost | direction | contract
from:    <who wrote it>
to:      <who it is for>
spend:   <the class answering this costs: tokens, person_time, machine_time, money>
id:      <what it answers or what it is; a path when it answers a message>

<the question or the order, in the body, one statement per line>

<effort: what answering costs, and what the writer will do if no answer comes>
```

`kind` sets the route and is not a tone: `direction` needs the person's taste, `cost` needs
somebody to bear a commitment, `resource` needs a budget holder, `contract` means the message
above could not be read and the layer that wrote it rewrites it.

A message is deleted once it is read and landed — the fact into the document that owns it, the
order carried out, an unanswerable one forwarded into the parent's `inbox/` carrying its `id`.
Deleting is tidying and is not a reply. `.gitkeep` holds the empty directory, since git prunes
directories with no tracked file.
