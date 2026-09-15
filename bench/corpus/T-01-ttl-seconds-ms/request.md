Sessions in the API expire after 60 seconds instead of 1 hour — users are getting logged
out constantly since last week's auth refactor. My guess is a seconds/milliseconds mixup
when the session TTL was moved into config, but I can't spot it. Whatever it is, sessions
need to live a full hour again, and don't touch the public API while fixing it.
