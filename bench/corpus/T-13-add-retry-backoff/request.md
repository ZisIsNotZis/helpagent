The download endpoint intermittently comes back with the backend's transient
marker, and right now we surface that to users as a hard failure — support is
tired of telling people "just try again". The client should ride out those
hiccups itself: retry per the documented backoff schedule before giving up, and
it has to stay testable without actually sleeping. Please finish that.
