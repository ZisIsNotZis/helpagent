Setting up a staging deployment of the mailer with just the host in the settings file,
and sending the test email crashes with "KeyError: 'retries'". The docs say every option
except the host is optional and falls back to a sane default — we shouldn't have to spell
out every key just to send one email. Please make optional settings actually optional.
