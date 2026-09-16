Ops wants to get paged when a client starts getting throttled. The limiter already
accepts an on_limit callback — please make it fire exactly once when a key first
crosses the threshold. Repeated blocked hits must not re-fire it, and if no callback
is registered nothing should change. Our pager can't handle one alert per request.
