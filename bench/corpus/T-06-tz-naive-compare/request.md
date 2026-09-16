The job scheduler crashes with "TypeError: can't compare offset-naive and offset-aware
datetimes" whenever it checks whether jobs are due — but only on the code path that uses
its own clock; when we pass the time in explicitly it works fine. Everything in the
scheduler is supposed to be timezone-aware UTC. Please make the default-clock path work.
